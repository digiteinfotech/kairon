import ujson as json
import logging
from typing import (
    List,
    Text,
    Optional,
    Dict,
    Any,
    TYPE_CHECKING,
    cast,
)

import aiohttp
import rasa.core
import rasa.shared.utils.io
from rasa.core.actions.constants import DEFAULT_SELECTIVE_DOMAIN, SELECTIVE_DOMAIN
from rasa.core.constants import (
    DEFAULT_REQUEST_TIMEOUT,
    COMPRESS_ACTION_SERVER_REQUEST_ENV_NAME,
    DEFAULT_COMPRESS_ACTION_SERVER_REQUEST,
)
from rasa.plugin import plugin_manager
from rasa.shared.constants import (
    DOCS_BASE_URL,
)
from rasa.shared.core import events
from rasa.shared.core.domain import Domain
from rasa.shared.core.events import (
    Event,
    BotUttered,
)
from rasa.shared.core.trackers import DialogueStateTracker
from rasa.shared.exceptions import RasaException
from rasa.shared.utils.schemas.events import EVENTS_SCHEMA
from rasa.utils.common import get_bool_env_variable
from rasa.utils.endpoints import EndpointConfig, ClientResponseError
from rasa.core.actions.action import Action, ActionExecutionRejection, create_bot_utterance

if TYPE_CHECKING:
    from rasa.core.nlg import NaturalLanguageGenerator
    from rasa.core.channels.channel import OutputChannel

logger = logging.getLogger(__name__)


class KRemoteAction(Action):
    def __init__(self, name: Text, action_endpoint: Optional[EndpointConfig]) -> None:

        self._name = name
        self.action_endpoint = action_endpoint

    def _action_call_format(
            self,
            tracker: "DialogueStateTracker",
            domain: "Domain",
    ) -> Dict[Text, Any]:
        """Create the request json send to the action server."""
        from rasa.shared.core.trackers import EventVerbosity

        tracker_state = tracker.current_state(EventVerbosity.ALL)

        result = {
            "next_action": self._name,
            "sender_id": tracker.sender_id,
            "tracker": tracker_state,
            "version": rasa.__version__,
        }

        if (
                not self._is_selective_domain_enabled()
                or domain.does_custom_action_explicitly_need_domain(self.name())
        ):
            result["domain"] = domain.as_dict()

        return result

    def _is_selective_domain_enabled(self) -> bool:
        if self.action_endpoint is None:
            return False
        return bool(
            self.action_endpoint.kwargs.get(SELECTIVE_DOMAIN, DEFAULT_SELECTIVE_DOMAIN)
        )

    @staticmethod
    def action_response_format_spec() -> Dict[Text, Any]:
        """Expected response schema for an Action endpoint.

        Used for validation of the response returned from the
        Action endpoint.
        """
        schema = {
            "type": "object",
            "properties": {
                "events": EVENTS_SCHEMA,
                "responses": {"type": "array", "items": {"type": "object"}},
            },
        }
        return schema

    def _validate_action_result(self, result: Dict[Text, Any]) -> bool:
        from jsonschema import validate
        from jsonschema import ValidationError

        try:
            validate(result, self.action_response_format_spec())
            return True
        except ValidationError as e:
            e.message += (
                f". Failed to validate Action server response from API, "
                f"make sure your response from the Action endpoint is valid. "
                f"For more information about the format visit "
                f"{DOCS_BASE_URL}/custom-actions"
            )
            raise e

    @staticmethod
    async def _utter_responses(
            responses: List[Dict[Text, Any]],
            output_channel: "OutputChannel",
            nlg: "NaturalLanguageGenerator",
            tracker: "DialogueStateTracker",
            action_name: Text
    ) -> List[BotUttered]:
        """Use the responses generated by the action endpoint and utter them."""
        bot_messages = []
        for response in responses:
            generated_response = response.pop("response", None)
            if generated_response:
                draft = await nlg.generate(
                    generated_response, tracker, output_channel.name(), **response
                )
                if not draft:
                    continue
                draft["utter_action"] = generated_response
            else:
                draft = {'utter_action': action_name}

            buttons = response.pop("buttons", []) or []
            if buttons:
                draft.setdefault("buttons", [])
                draft["buttons"].extend(buttons)

            # Avoid overwriting `draft` values with empty values
            response = {k: v for k, v in response.items() if v}
            draft.update(response)
            bot_messages.append(create_bot_utterance(draft))

        return bot_messages

    async def run(
            self,
            output_channel: "OutputChannel",
            nlg: "NaturalLanguageGenerator",
            tracker: "DialogueStateTracker",
            domain: "Domain",
    ) -> List[Event]:
        """Runs action. Please see parent class for the full docstring."""
        json_body = self._action_call_format(tracker, domain)
        if not self.action_endpoint:
            raise RasaException(
                f"Failed to execute custom action '{self.name()}' "
                f"because no endpoint is configured to run this "
                f"custom action. Please take a look at "
                f"the docs and set an endpoint configuration via the "
                f"--endpoints flag. "
                f"{DOCS_BASE_URL}/custom-actions"
            )

        try:
            logger.debug(
                "Calling action endpoint to run action '{}'.".format(self.name())
            )

            should_compress = get_bool_env_variable(
                COMPRESS_ACTION_SERVER_REQUEST_ENV_NAME,
                DEFAULT_COMPRESS_ACTION_SERVER_REQUEST,
            )

            modified_json = plugin_manager().hook.prefix_stripping_for_custom_actions(
                json_body=json_body
            )
            response: Any = await self.action_endpoint.request(
                json=modified_json if modified_json else json_body,
                method="post",
                timeout=DEFAULT_REQUEST_TIMEOUT,
                compress=should_compress,
            )
            if modified_json:
                plugin_manager().hook.prefixing_custom_actions_response(
                    json_body=json_body, response=response
                )
            self._validate_action_result(response)

            events_json = response.get("events", [])
            responses = response.get("responses", [])
            bot_messages = await self._utter_responses(
                responses, output_channel, nlg, tracker, self._name
            )

            evts = events.deserialise_events(events_json)
            return cast(List[Event], bot_messages) + evts

        except ClientResponseError as e:
            if e.status == 400:
                response_data = json.loads(e.text)
                exception = ActionExecutionRejection(
                    response_data["action_name"], response_data.get("error")
                )
                logger.error(exception.message)
                raise exception
            else:
                raise RasaException(
                    f"Failed to execute custom action '{self.name()}'"
                ) from e

        except aiohttp.ClientConnectionError as e:
            logger.error(
                f"Failed to run custom action '{self.name()}'. Couldn't connect "
                f"to the server at '{self.action_endpoint.url}'. "
                f"Is the server running? "
                f"Error: {e}"
            )
            raise RasaException(
                f"Failed to execute custom action '{self.name()}'. Couldn't connect "
                f"to the server at '{self.action_endpoint.url}."
            )

        except aiohttp.ClientError as e:
            # not all errors have a status attribute, but
            # helpful to log if they got it

            # noinspection PyUnresolvedReferences
            status = getattr(e, "status", None)
            raise RasaException(
                "Failed to run custom action '{}'. Action server "
                "responded with a non 200 status code of {}. "
                "Make sure your action server properly runs actions "
                "and returns a 200 once the action is executed. "
                "Error: {}".format(self.name(), status, e)
            )

    def name(self) -> Text:
        return self._name
