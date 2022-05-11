from typing import Dict, Text, List, Any

from mongoengine import DoesNotExist
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.forms import REQUESTED_SLOT
from rasa_sdk.interfaces import Tracker

from ...shared.actions.models import KAIRON_ACTION_RESPONSE_SLOT, ActionType
from ...shared.actions.data_objects import ActionServerLogs
from ...shared.actions.exception import ActionFailure
from ...shared.actions.utils import ActionUtility, ExpressionEvaluator
from loguru import logger

from ...shared.constants import SLOT_SET_TYPE
from ...shared.utils import Utility


class ActionProcessor:

    @staticmethod
    async def process_action(dispatcher: CollectingDispatcher,
                             tracker: Tracker,
                             domain: Dict[Text, Any], action: Text) -> List[Dict[Text, Any]]:
        return await ActionProcessor.__process_action(dispatcher, tracker, domain, action)

    @staticmethod
    async def __process_action(dispatcher: CollectingDispatcher,
                               tracker: Tracker,
                               domain: Dict[Text, Any], action) -> List[Dict[Text, Any]]:
        slots = {}
        action_type = None
        try:
            logger.info(tracker.current_slot_values())
            intent = tracker.get_intent_of_latest_message()
            logger.info("intent: " + str(intent))
            logger.info("tracker.latest_message: " + str(tracker.latest_message))
            bot_id = tracker.get_slot("bot")
            if ActionUtility.is_empty(bot_id) or ActionUtility.is_empty(action):
                raise ActionFailure("Bot id and action name not found in slot")

            action_config, action_type = ActionUtility.get_action_config(bot=bot_id, name=action)
            if action_type == ActionType.http_action.value:
                slots = await ActionProcessor.__process_http_action(tracker, action_config)
                dispatcher.utter_message(slots.get(KAIRON_ACTION_RESPONSE_SLOT))
            elif action_type == ActionType.slot_set_action.value:
                slots = await ActionProcessor.__process_slot_set_action(tracker, action_config)
            elif action_type == ActionType.form_validation_action.value:
                slots = await ActionProcessor.__process_form_validation_action(dispatcher, tracker, action_config)
            elif action_type == ActionType.email_action.value:
                slots = await ActionProcessor.__process_email_action(dispatcher, tracker, action_config)
            elif action_type == ActionType.google_search_action.value:
                slots = await ActionProcessor.__process_google_search_action(dispatcher, tracker, action_config)
            elif action_type == ActionType.jira_action.value:
                slots = await ActionProcessor.__process_jira_action(dispatcher, tracker, action_config)
            elif action_type == ActionType.zendesk_action.value:
                slots = await ActionProcessor.__process_zendesk_action(dispatcher, tracker, action_config)
            elif action_type == ActionType.pipedrive_leads_action.value:
                slots = await ActionProcessor.__process_pipedrive_leads_action(dispatcher, tracker, action_config)
            return [SlotSet(slot, value) for slot, value in slots.items()]
        except Exception as e:
            logger.exception(e)
            ActionServerLogs(
                type=action_type,
                intent=tracker.get_intent_of_latest_message(),
                action=action,
                sender=tracker.sender_id,
                exception=str(e),
                bot=tracker.get_slot("bot"),
                status="FAILURE"
            ).save()

    @staticmethod
    async def __process_http_action(tracker: Tracker, http_action_config: dict):
        bot_response = None
        http_response = None
        exception = None
        request_body = None
        status = "SUCCESS"
        http_url = None
        request_method = None
        headers = None
        try:
            headers = ActionUtility.prepare_request(tracker, http_action_config.get('headers'))
            request_body = ActionUtility.prepare_request(tracker, http_action_config['params_list'])
            logger.info("request_body: " + str(request_body))
            request_method = http_action_config['request_method']
            http_url = ActionUtility.prepare_url(request_method=request_method,
                                                 http_url=http_action_config['http_url'],
                                                 request_body=request_body)
            http_response = ActionUtility.execute_http_request(headers=headers,
                                                               http_url=http_url,
                                                               request_method=request_method,
                                                               request_body=request_body)
            logger.info("http response: " + str(http_response))
            bot_response = ActionUtility.prepare_response(http_action_config['response'], http_response)
            logger.info("response: " + str(bot_response))
        except ActionFailure as e:
            exception = str(e)
            logger.exception(e)
            status = "FAILURE"
            bot_response = "I have failed to process your request"
        except Exception as e:
            exception = str(e)
            logger.exception(e)
            status = "FAILURE"
            bot_response = "I have failed to process your request"
        finally:
            ActionServerLogs(
                type=ActionType.http_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=http_action_config['action_name'],
                sender=tracker.sender_id,
                headers=headers,
                url=http_url,
                request_params=None if request_method and request_method.lower() == "get" else request_body,
                api_response=str(http_response) if http_response else None,
                bot_response=str(bot_response) if bot_response else None,
                exception=exception,
                bot=tracker.get_slot("bot"),
                status=status
            ).save()
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}

    @staticmethod
    async def __process_slot_set_action(tracker: Tracker, action_config: dict):
        message = []
        reset_slots = {}
        status = 'SUCCESS'
        for slots_to_reset in action_config['set_slots']:
            if slots_to_reset['type'] == SLOT_SET_TYPE.FROM_VALUE.value:
                reset_slots[slots_to_reset['name']] = slots_to_reset['value']
                message.append(f"Setting slot '{slots_to_reset['name']}' to '{slots_to_reset['value']}'.")
            else:
                reset_slots[slots_to_reset['name']] = None
                message.append(f"Resetting slot '{slots_to_reset['name']}' value to None.")

        ActionServerLogs(
            type=ActionType.slot_set_action.value,
            intent=tracker.get_intent_of_latest_message(),
            action=action_config['name'],
            sender=tracker.sender_id,
            messages=message,
            bot=tracker.get_slot("bot"),
            status=status
        ).save()
        return reset_slots

    @staticmethod
    async def __process_form_validation_action(dispatcher: CollectingDispatcher, tracker: Tracker, form_validations):
        slot = tracker.get_slot(REQUESTED_SLOT)
        slot_value = tracker.get_slot(slot)
        msg = [f'slot: {slot} | slot_value: {slot_value}']
        status = "FAILURE"
        if ActionUtility.is_empty(slot):
            return {}
        try:
            validation = form_validations.get(slot=slot)
            slot_type = ActionUtility.get_slot_type(validation.bot, slot)
            msg.append(f'slot_type: {slot_type}')
            semantic = validation.validation_semantic
            msg.append(f'validation: {semantic}')
            utter_msg_on_valid = validation.valid_response
            utter_msg_on_invalid = validation.invalid_response
            msg.append(f'utter_msg_on_valid: {utter_msg_on_valid}')
            msg.append(f'utter_msg_on_valid: {utter_msg_on_invalid}')
            expr_as_str, is_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value, semantic)
            msg.append(f'Expression: {expr_as_str}')
            msg.append(f'is_valid: {is_valid}')

            if is_valid:
                status = "SUCCESS"
                if not ActionUtility.is_empty(utter_msg_on_valid):
                    dispatcher.utter_message(text=utter_msg_on_valid)

            if not is_valid:
                slot_value = None
                if not ActionUtility.is_empty(utter_msg_on_invalid):
                    dispatcher.utter_message(utter_msg_on_invalid)
        except DoesNotExist as e:
            logger.exception(e)
            msg.append(f'Skipping validation as no validation config found for slot: {slot}')
            logger.debug(e)
        finally:
            ActionServerLogs(
                type=ActionType.form_validation_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=tracker.followup_action,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                messages=msg,
                status=status
            ).save()

        return {slot: slot_value}

    @staticmethod
    async def __process_email_action(dispatcher: CollectingDispatcher, tracker: Tracker, action_config: dict):
        status = "SUCCESS"
        exception = None
        bot_response = action_config.get("response")
        to_email = action_config['to_email']
        try:
            for mail in to_email:
                body = ActionUtility.prepare_email_body(tracker.events, action_config['subject'], mail)
                await Utility.trigger_email(email=[mail],
                                            subject=f"{tracker.sender_id} {action_config['subject']}",
                                            body=body,
                                            smtp_url=action_config['smtp_url'],
                                            smtp_port=action_config['smtp_port'],
                                            sender_email=action_config['from_email'],
                                            smtp_password=action_config['smtp_password'],
                                            smtp_userid=action_config.get("smtp_userid"),
                                            tls=action_config['tls'],
                                            )

        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            bot_response = "I have failed to process your request"
            status = "FAILURE"
        finally:
            ActionServerLogs(
                type=ActionType.email_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=action_config['action_name'],
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                bot_response=bot_response,
                status=status
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}

    @staticmethod
    async def __process_google_search_action(dispatcher: CollectingDispatcher, tracker: Tracker, action_config: dict):
        exception = None
        status = "SUCCESS"
        latest_msg = tracker.latest_message.get('text')
        bot_response = action_config.get("failure_response")
        try:
            if not ActionUtility.is_empty(latest_msg):
                results = ActionUtility.perform_google_search(
                    action_config['api_key'], action_config['search_engine_id'], latest_msg,
                    num=action_config.get("num_results")
                )
                if results:
                    bot_response = ActionUtility.format_search_result(results)
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            status = "FAILURE"
        finally:
            ActionServerLogs(
                type=ActionType.google_search_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=action_config['name'],
                bot_response=bot_response,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                status=status
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}

    @staticmethod
    async def __process_jira_action(dispatcher: CollectingDispatcher, tracker: Tracker, action_config: dict):
        status = "SUCCESS"
        exception = None
        bot_response = action_config.get("response")
        summary = f"{tracker.sender_id} {action_config['summary']}"
        try:
            _, msgtrail = ActionUtility.prepare_message_trail_as_str(tracker.events)
            ActionUtility.create_jira_issue(
                url=action_config['url'],
                username=action_config['user_name'],
                api_token=action_config['api_token'],
                project_key=action_config['project_key'],
                issue_type=action_config['issue_type'],
                summary=summary,
                description=msgtrail,
                parent_key=action_config.get('parent_key')
            )
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
            bot_response = "I have failed to create issue for you"
        finally:
            ActionServerLogs(
                type=ActionType.jira_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=action_config['name'],
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                bot_response=bot_response,
                status=status
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}

    @staticmethod
    async def __process_zendesk_action(dispatcher: CollectingDispatcher, tracker: Tracker, action_config: dict):
        status = "SUCCESS"
        exception = None
        bot_response = action_config.get("response")
        subject = f"{tracker.sender_id} {action_config['subject']}"
        try:
            comment = ActionUtility.prepare_email_body(tracker.events, action_config['subject'])
            ActionUtility.create_zendesk_ticket(
                subdomain=action_config['subdomain'],
                user_name=action_config['user_name'],
                api_token=action_config['api_token'],
                subject=subject,
                comment=comment,
                tags=action_config.get('tags')
            )
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
            bot_response = "I have failed to create issue for you"
        finally:
            ActionServerLogs(
                type=ActionType.zendesk_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=action_config['name'],
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                bot_response=bot_response,
                status=status
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}

    @staticmethod
    async def __process_pipedrive_leads_action(dispatcher: CollectingDispatcher, tracker: Tracker, action_config: dict):
        status = "SUCCESS"
        exception = None
        bot_response = action_config.get("response")
        title = f"{tracker.sender_id} {action_config['title']}"
        try:
            _, conversation_as_str = ActionUtility.prepare_message_trail_as_str(tracker.events)
            metadata = ActionUtility.prepare_pipedrive_metadata(tracker, action_config)
            ActionUtility.create_pipedrive_lead(
                domain=action_config['domain'],
                api_token=action_config['api_token'],
                title=title,
                conversation=conversation_as_str,
                **metadata
            )
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
            bot_response = "I have failed to create lead for you"
        finally:
            ActionServerLogs(
                type=ActionType.pipedrive_leads_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=action_config['name'],
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                bot_response=bot_response,
                status=status
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}
