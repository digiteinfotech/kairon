from enum import Enum
from typing import Optional

from mongoengine import Document

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import HttpActionConfig, KaironTwoStageFallbackAction, EmailActionConfig, \
    ZendeskAction, JiraAction, FormValidationAction, SlotSetAction, GoogleSearchAction, PipedriveLeadsAction, \
    PromptAction, WebSearchAction, RazorpayAction, PyscriptActionConfig, DatabaseAction, LiveAgentActionConfig, \
    CallbackActionConfig, ScheduleAction, Actions, ParallelActionConfig
from kairon.shared.actions.models import ActionType
from kairon.shared.callback.data_objects import CallbackConfig
from kairon.shared.data.data_models import HttpActionConfigRequest, TwoStageFallbackConfigRequest, EmailActionRequest, \
    JiraActionRequest, ZendeskActionRequest, SlotSetActionRequest, GoogleSearchActionRequest, PipedriveActionRequest, \
    RazorpayActionRequest, PyscriptActionRequest, DatabaseActionRequest, \
    LiveAgentActionRequest, CallbackActionConfigRequest, ScheduleActionRequest, WebSearchActionRequest, \
    CallbackConfigRequest, PromptActionConfigUploadValidation, ParallelActionRequest
from kairon.shared.data.data_objects import Forms
from kairon.shared.data.data_validation import DataValidation
from pydantic import ValidationError as PValidationError


class ReconfigarableProperty(Enum):
    bot = "bot"
    user = "user"
    status = "status"


class ActionSerializer:
    """
    action_lookup: dict = {
        export_name_str : {
            "db_model": Document,
            "validation_model": Document,
            "custom_validation": Optional[list[function]] = [], // [(bot: str, data: dict) -> list[str]]
            "modify": Optional[function] = None, // (bot: str, data: dict) -> dict
            "single_instance": Optional[bool] = False
            "group": Optional[str] = 'action' // action -> action.yml, anything_else -> other_collections.yml
            "reconfigure": Optional[list[ReconfigarableProperty]] = default_reconfigurable
        }
    """
    action_lookup = {
        ActionType.http_action.value: {
            "db_model": HttpActionConfig,
            "validation_model": HttpActionConfigRequest,
            "custom_validation": [DataValidation.validate_http_action],
        },
        ActionType.two_stage_fallback.value: {
            "db_model": KaironTwoStageFallbackAction,
            "validation_model": TwoStageFallbackConfigRequest,
            "single_instance": True,
        },
        ActionType.email_action.value: {
            "db_model": EmailActionConfig,
            "validation_model": EmailActionRequest,
        },
        ActionType.zendesk_action.value: {
            "db_model": ZendeskAction,
            "validation_model": ZendeskActionRequest,
        },
        ActionType.jira_action.value: {
            "db_model": JiraAction,
            "validation_model": JiraActionRequest,
        },
        ActionType.form_validation_action.value: {
            "db_model": FormValidationAction,
            "validation_model": None,
            "custom_validation": [DataValidation.validate_form_validation_action],
        },
        ActionType.slot_set_action.value: {
            "db_model": SlotSetAction,
            "validation_model": SlotSetActionRequest,
        },
        ActionType.google_search_action.value: {
            "db_model": GoogleSearchAction,
            "validation_model": GoogleSearchActionRequest,
        },
        ActionType.pipedrive_leads_action.value: {
            "db_model": PipedriveLeadsAction,
            "validation_model": PipedriveActionRequest,
        },
        ActionType.prompt_action.value: {
            "db_model": PromptAction,
            "validation_model": PromptActionConfigUploadValidation,
            "custom_validation": [DataValidation.validate_prompt_action],
        },
        ActionType.web_search_action.value: {
            "db_model": WebSearchAction,
            "validation_model": WebSearchActionRequest
        },
        ActionType.razorpay_action.value: {
            "db_model": RazorpayAction,
            "validation_model": RazorpayActionRequest,
        },
        ActionType.pyscript_action.value: {
            "db_model": PyscriptActionConfig,
            "validation_model": PyscriptActionRequest,
            "custom_validation": [DataValidation.validate_pyscript_action],
        },
        ActionType.database_action.value: {
            "db_model": DatabaseAction,
            "validation_model": DatabaseActionRequest,
            "custom_validation": [DataValidation.validate_database_action],
        },
        ActionType.live_agent_action.value: {
            "db_model": LiveAgentActionConfig,
            "validation_model": LiveAgentActionRequest,
            "single_instance": True,
        },
        ActionType.callback_action.value: {
            "db_model": CallbackActionConfig,
            "validation_model": CallbackActionConfigRequest,
            "entry_check": "callback",
        },
        ActionType.schedule_action.value: {
            "db_model": ScheduleAction,
            "validation_model": ScheduleActionRequest,
        },
        ActionType.parallel_action.value:{
            "db_model": ParallelActionConfig,
            "validation_model": ParallelActionRequest,
        },
        str(CallbackConfig.__name__).lower(): {
            "db_model": CallbackConfig,
            "validation_model": CallbackConfigRequest,
            "group": "callback",
            "custom_validation": [DataValidation.validate_callback_config],
            "modify": DataValidation.modify_callback_config,
            "reconfigure": [ReconfigarableProperty.bot.value]
        }

    }

    default_reconfigurable = [ReconfigarableProperty.bot.value,
                              ReconfigarableProperty.user.value,
                              ReconfigarableProperty.status.value]

    @staticmethod
    def get_item_name(data: dict, raise_exception: bool = True):
        """
        Gets the name of the action
        :param data: action data
        :param raise_exception: bool
        :return: action name
        """
        action_name = data.get("action_name") or data.get("name")
        if Utility.check_empty_string(action_name):
            if raise_exception:
                raise AppException("Action name cannot be empty or blank spaces!")
            action_name = None
        return action_name

    @staticmethod
    def validate(bot: str, actions: dict, other_collections: dict):
        """
        Validates the action configuration data, first return parameter is true if validation is successful
        :param bot: bot id
        :param actions: action configuration data
        :param other_collections: other collection configuration data
        :return: is_data_valid: bool, error_summary: dict, component_count: dict
        """
        is_data_invalid = False
        component_count = dict.fromkeys(ActionSerializer.action_lookup.keys(), 0)
        error_summary = {key: [] for key in ActionSerializer.action_lookup.keys()}
        encountered_action_names = set()
        if not actions:
            return True, error_summary, component_count
        if not isinstance(actions, dict):
            error_summary = {'action.yml':  ['Expected dictionary with action types as keys']}
            return True, error_summary, component_count

        for action_type, actions_list in actions.items():
            if action_type not in ActionSerializer.action_lookup:
                error_summary[action_type] = [f"Invalid action type: {action_type}."]
                is_data_invalid = True
                continue

            if not isinstance(actions_list, list):
                error_summary[action_type] = [f"Expected list of actions for {action_type}."]
                is_data_invalid = True
                continue

            component_count[action_type] = len(actions_list)

            if error_list := ActionSerializer.collection_config_validation(bot, action_type, actions_list, encountered_action_names):
                error_summary[action_type].extend(error_list)
                is_data_invalid = True
                continue

        if other_collections:
            for collection_name, collection_data in other_collections.items():
                if collection_name not in ActionSerializer.action_lookup:
                    error_summary[collection_name] = [f"Invalid collection type: {collection_name}."]
                    is_data_invalid = True
                    continue
                if not isinstance(collection_data, list):
                    error_summary[collection_name] = [f"Expected list of data for {collection_name}."]
                    is_data_invalid = True
                    continue

                component_count[collection_name] = len(collection_data)

                if error_list := ActionSerializer.collection_config_validation(bot, collection_name, collection_data, set()):
                    error_summary[collection_name].extend(error_list)
                    is_data_invalid = True

        return not is_data_invalid, error_summary, component_count

    @staticmethod
    def collection_config_validation(bot: str, action_type: str, actions_list: list[dict], encountered_action_names: set):
        """
        Validates the action configuration data for an action type
        :param bot: bot id
        :param action_type: action type
        :param actions_list: list of action configuration data
        :param encountered_action_names: set of action names encountered
        :return: error_summary: list
        """
        action_info = ActionSerializer.action_lookup.get(action_type)
        if not action_info:
            return [f"Action type not found: {action_type}."]
        validation_model = action_info.get("validation_model")  # pydantic model
        collection_model = action_info.get("db_model")  # mongoengine model

        err_summary = []
        custom_validation = action_info.get("custom_validation")
        required_fields = {k for k, v in collection_model._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}

        for action in actions_list:
            if not isinstance(action, dict):
                err_summary.append(f"Expected dictionary for [{action_type}] ")
                continue
            action_name = ActionSerializer.get_item_name(action, raise_exception=False)
            if not action_name:
                err_summary.append(f"No name found for  [{action_type}].")
                continue
            if action_name in encountered_action_names:
                if action_type != ActionType.form_validation_action.value and not action_name.startswith("utter_"):
                    err_summary.append({action_name: "Duplicate Name found for other action."})
                    continue
            encountered_action_names.add(action_name)
            if not action:
                err_summary.append("Action configuration cannot be empty.")
                continue
            not_present_fields = required_fields.difference(set(action.keys()))
            if len(not_present_fields) > 0:
                err_summary.append({
                    action_name: f' Required fields {not_present_fields} not found.'
                })
                continue
            if custom_validation:
                for cv in custom_validation:
                    if validation_result := cv(bot, action):
                        err_summary.extend(validation_result)
                if err_summary:
                    continue
            try:
                if validation_model:
                    validation_model(**action)
            except PValidationError as pe:
                err_summary.append({action_name: f"{str(pe)}"})
            except Exception as e:
                err_summary.append({action_name: f"{str(e)}"})

        return err_summary

    @staticmethod
    def get_collection_infos():
        """
        Get action and other collection information as seperate dicts
        :return: actions_collections: dict, other_collections: dict
        """
        actions_collections = {k: v for k, v in ActionSerializer.action_lookup.items()
                               if not v.get("group") or v.get("group") == "action"}
        other_collections = {k: v for k, v in ActionSerializer.action_lookup.items()
                             if v.get("group") and v.get("group") != "action"}

        return actions_collections, other_collections

    @staticmethod
    def serialize(bot: str):
        """
        Serialize / export all the actions and configuration collection data
        :param bot: bot id
        :return: action_config: dict, other_config: dict
        """
        action_config = {}
        other_config = {}

        actions_collections, other_collections = ActionSerializer.get_collection_infos()

        for action_type, action_info in actions_collections.items():
            action_model = action_info.get("db_model")
            actions = ActionSerializer.get_action_config_data_list(bot, action_model, query={'status': True})
            if actions:
                action_config[action_type] = actions

        for other_type, other_info in other_collections.items():
            other_model = other_info.get("db_model")
            other_collections = ActionSerializer.get_action_config_data_list(bot, other_model)
            if other_collections:
                other_config[other_type] = other_collections
        return action_config, other_config

    @staticmethod
    def deserialize(bot: str, user: str, actions: Optional[dict] = None, other_collections_data: Optional[dict] = None, overwrite: bool = False):
        """
        Deserialize / import the actions and configuration collection data
        :param bot: bot id
        :param user: user id
        :param actions: action configuration data
        :param other_collections_data: other collection configuration data
        :param overwrite: bool
        """
        actions_collections, _ = ActionSerializer.get_collection_infos()

        if overwrite:
            for _, info in ActionSerializer.action_lookup.items():
                model = info.get("db_model")
                if model:
                    model.objects(bot=bot).delete()

        saved_actions = set(
            Actions.objects(bot=bot, status=True, type__ne=None).values_list("name")
        )
        form_names = set(
            Forms.objects(bot=bot, status=True).values_list("name")
        )

        filtered_actions = {}
        if actions:
            for action_type, action_info in actions_collections.items():
                if action_type in actions:
                    # Skip if no actions are present
                    if len(actions[action_type]) == 0:
                        continue

                    if action_type == ActionType.form_validation_action.value:
                        filtered_actions[action_type] = actions[action_type]
                    elif action_info.get('single_instance'):
                        if overwrite:
                            filtered_actions[action_type] = actions[action_type]
                        else:
                            existing_action = action_info.get("db_model").objects(bot=bot).first()
                            if not existing_action:
                                filtered_actions[action_type] = actions[action_type]
                    else:
                        new_actions = []
                        action_names = []
                        for a in actions[action_type]:
                            action_name = ActionSerializer.get_item_name(a)
                            if action_name in form_names:
                                raise AppException(f"Form with name {action_name} already exists!")
                            if (action_name not in saved_actions
                                    and not action_name.startswith("utter_")
                                    and action_name not in action_names):
                                action_names.append(action_name)
                                new_actions.append(a)
                        filtered_actions[action_type] = new_actions

            for action_type, data in filtered_actions.items():
                if data:
                    ActionSerializer.save_collection_data_list(action_type, bot, user, data)
        if other_collections_data:
            ActionSerializer.save_other_collections(other_collections_data, bot, user, overwrite)

    @staticmethod
    def get_action_config_data_list(bot: str, action_model: Document, with_doc_id: bool = False, query: dict = {}) -> list[dict]:
        """
        Get the action configuration data list
        :param bot: bot id
        :param action_model: mongoengine model
        :param with_doc_id: bool
        :param query: dict
        :return: list[dict]
        """
        query['bot'] = bot
        key_to_remove = {"_id", "user", "bot", "status", "timestamp"}
        query_result = action_model.objects(**query).as_pymongo()
        actions = []
        if query_result:
            actions = [
                {
                    **({"_id": str(action["_id"])} if with_doc_id else {}),
                    **{k: v for k, v in action.items() if k not in key_to_remove}
                }
                for action in query_result
            ]
        return actions


    @staticmethod
    def is_action(action_type: str):
        if not action_type or action_type not in ActionSerializer.action_lookup:
            return False
        return not ActionSerializer.action_lookup[action_type].get("group") or ActionSerializer.action_lookup[action_type].get("group") == "action"

    @staticmethod
    def save_collection_data_list(action_type: str, bot: str, user: str, configs: list[dict]):
        """
        Save the collection data list for action or any collection. Mongoengine model must be available in the lookup
        """
        if not configs:  # Early exit if no configs are present
            return

        model = ActionSerializer.action_lookup.get(action_type, {}).get("db_model")
        modify = ActionSerializer.action_lookup.get(action_type, {}).get("modify")
        is_action = ActionSerializer.is_action(action_type)
        if not model:
            raise AppException(f"Action type not found: [{action_type}]!")

        try:
            model_entries = []
            action_entries = []
            action_names = set()
            reconfig_props = (ActionSerializer.action_lookup.get(action_type, {})
                              .get("reconfigure", ActionSerializer.default_reconfigurable))
            for config in configs:
                if ReconfigarableProperty.bot.value in reconfig_props:
                    config["bot"] = bot
                if ReconfigarableProperty.user.value in reconfig_props:
                    config["user"] = user
                if ReconfigarableProperty.status.value in reconfig_props:
                    config["status"] = True
                if modify:
                    config = modify(bot, config)
                model_entries.append(model(**config))
                action_name = ActionSerializer.get_item_name(config)

                if is_action and action_name not in action_names:
                    action_entries.append(Actions(
                        name=action_name,
                        type=action_type,
                        bot=bot,
                        user=user,
                        status=True
                    ))
                action_names.add(action_name)
            if action_entries:
                Actions.objects.insert(action_entries)
            if model_entries:
                model.objects.insert(model_entries)
        except Exception as e:
            raise AppException(f"Error saving action config data: {str(e)}") from e

    @staticmethod
    def save_other_collections(other_collections_data: dict, bot: str, user: str, overwrite: bool = False):
        _, other_collections = ActionSerializer.get_collection_infos()
        for collection_name, collection_info in other_collections.items():
            collection_data = other_collections_data.get(collection_name)
            if overwrite:
                collection_info.get("db_model").objects(bot=bot).delete()
            else:
                prev_data = collection_info.get("db_model").objects(bot=bot)
                names = set(prev_data.values_list("name"))
                collection_data = [data for data in collection_data if data.get("name") not in names]

            if collection_name and collection_data:
                collection_model = collection_info.get("db_model")
                if collection_model:
                    ActionSerializer.save_collection_data_list(collection_name, bot, user, collection_data)
                else:
                    raise AppException(f"Collection model not found for [{collection_name}]!")
