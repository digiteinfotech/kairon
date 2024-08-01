from typing import Text

from kairon.actions.definitions.callback_action import ActionCallback
from kairon.actions.definitions.bot_response import ActionKaironBotResponse
from kairon.actions.definitions.email import ActionEmail
from kairon.actions.definitions.form_validation import ActionFormValidation
from kairon.actions.definitions.google import ActionGoogleSearch
from kairon.actions.definitions.http import ActionHTTP
from kairon.actions.definitions.hubspot import ActionHubspotForms
from kairon.actions.definitions.jira import ActionJiraTicket
from kairon.actions.definitions.live_agent import ActionLiveAgent
from kairon.actions.definitions.pipedrive import ActionPipedriveLeads
from kairon.actions.definitions.prompt import ActionPrompt
from kairon.actions.definitions.pyscript import ActionPyscript
from kairon.actions.definitions.razorpay import ActionRazorpay
from kairon.actions.definitions.set_slot import ActionSetSlot
from kairon.actions.definitions.two_stage_fallback import ActionTwoStageFallback
from kairon.actions.definitions.database import ActionDatabase
from kairon.actions.definitions.web_search import ActionWebSearch
from kairon.actions.definitions.zendesk import ActionZendeskTicket
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility


class ActionFactory:

    __implementations = {
        ActionType.http_action.value: ActionHTTP,
        ActionType.google_search_action.value: ActionGoogleSearch,
        ActionType.slot_set_action.value: ActionSetSlot,
        ActionType.email_action.value: ActionEmail,
        ActionType.form_validation_action.value: ActionFormValidation,
        ActionType.jira_action.value: ActionJiraTicket,
        ActionType.zendesk_action.value: ActionZendeskTicket,
        ActionType.pipedrive_leads_action.value: ActionPipedriveLeads,
        ActionType.hubspot_forms_action.value: ActionHubspotForms,
        ActionType.two_stage_fallback.value: ActionTwoStageFallback,
        ActionType.kairon_bot_response.value: ActionKaironBotResponse,
        ActionType.razorpay_action.value: ActionRazorpay,
        ActionType.prompt_action.value: ActionPrompt,
        ActionType.pyscript_action.value: ActionPyscript,
        ActionType.database_action.value: ActionDatabase,
        ActionType.web_search_action.value: ActionWebSearch,
        ActionType.live_agent_action.value: ActionLiveAgent,
        ActionType.callback_action.value: ActionCallback
    }

    @staticmethod
    def get_instance(bot_id: Text, action_name: Text):
        action_type = ActionUtility.get_action_type(bot=bot_id, name=action_name)
        if not ActionFactory.__implementations.get(action_type):
            raise ActionFailure(f'{action_type} type action is not supported with action server')
        return ActionFactory.__implementations[action_type](bot_id, action_name)
