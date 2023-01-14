from enum import Enum

from kairon.shared.data.constant import ACCESS_ROLES

DEFAULT_INTENTS = {'restart', 'back', 'out_of_scope', 'session_start', 'nlu_fallback'}

DEFAULT_ACTIONS = {'action_listen', 'action_restart', 'action_session_start', 'action_default_fallback',
                   'action_deactivate_loop', 'action_revert_fallback_events', 'action_default_ask_affirmation',
                   'action_default_ask_rephrase', 'action_two_stage_fallback', 'action_back', '...'}

SYSTEM_TRIGGERED_UTTERANCES = {'utter_default', 'utter_please_rephrase'}

OWNER_ACCESS = [ACCESS_ROLES.OWNER.value]

ADMIN_ACCESS = [ACCESS_ROLES.OWNER.value, ACCESS_ROLES.ADMIN.value]

DESIGNER_ACCESS = [ACCESS_ROLES.OWNER.value, ACCESS_ROLES.ADMIN.value, ACCESS_ROLES.DESIGNER.value]

TESTER_ACCESS = [ACCESS_ROLES.OWNER.value, ACCESS_ROLES.ADMIN.value, ACCESS_ROLES.DESIGNER.value, ACCESS_ROLES.TESTER.value]

CHAT_ACCESS = [ACCESS_ROLES.OWNER.value, ACCESS_ROLES.ADMIN.value, ACCESS_ROLES.DESIGNER.value, ACCESS_ROLES.TESTER.value, ACCESS_ROLES.CHAT.value]

KAIRON_USER_MSG_ENTITY = "kairon_user_msg"


class SLOT_SET_TYPE(str, Enum):
    FROM_VALUE = "from_value"
    RESET_SLOT = "reset_slot"


class SSO_TYPES(str, Enum):
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    GOOGLE = "google"


class UserActivityType(str, Enum):
    reset_password = "reset_password"
    reset_password_request = "reset_password_request"
    delete_user = "delete_user"
    delete_bot = "delete_bot"
    delete_account = "delete_account"
    transfer_ownership = "transfer_ownership"
    add_asset = "add_asset"
    delete_asset = "delete_asset"
    link_usage = "link_usage"


class EventClass(str, Enum):
    model_training = "model_training"
    model_testing = "model_testing"
    data_importer = "data_importer"
    delete_history = "delete_history"
    multilingual = "multilingual"
    data_generator = "data_generator"
    faq_importer = "faq_importer"


class DataGeneratorCliTypes(str, Enum):
    from_website = '--from-website'
    from_document = '--from-document'


class EventExecutor(str, Enum):
    aws_lambda = "aws_lambda"
    dramatiq = "dramatiq"
    standalone = "standalone"


class MaskingStrategy(str, Enum):
    from_right = "from_right"
    from_left = "from_left"


class PluginTypes(str, Enum):
    ip_info = "ip_info"
    gpt = "gpt"


class ChannelTypes(str, Enum):
    MSTEAMS = "msteams"
    WHATSAPP = "whatsapp"
