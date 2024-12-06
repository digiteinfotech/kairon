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

VIEW_ACCESS = [ACCESS_ROLES.OWNER.value, ACCESS_ROLES.ADMIN.value, ACCESS_ROLES.DESIGNER.value, ACCESS_ROLES.TESTER.value, ACCESS_ROLES.CHAT.value, ACCESS_ROLES.VIEW.value]

AGENT_ACCESS = [ACCESS_ROLES.OWNER.value, ACCESS_ROLES.ADMIN.value, ACCESS_ROLES.DESIGNER.value, ACCESS_ROLES.TESTER.value, ACCESS_ROLES.CHAT.value, ACCESS_ROLES.VIEW.value, ACCESS_ROLES.AGENT.value]


KAIRON_USER_MSG_ENTITY = "kairon_user_msg"

FAQ_DISABLED_ERR = "Faq feature is disabled for the bot! Please contact support."


class SLOT_SET_TYPE(str, Enum):
    FROM_VALUE = "from_value"
    RESET_SLOT = "reset_slot"


class FORM_SLOT_SET_TYPE(str, Enum):
    current = "current"
    custom = "custom"
    slot = "slot"


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
    login = 'login'
    social_login = 'social_login'
    logout = 'logout'
    login_refresh_token = "login_refresh_token"
    invalid_login = 'invalid_login'
    download = "download"
    template_creation = 'template_creation'
    model_reload = "model_reload"


class EventClass(str, Enum):
    model_training = "model_training"
    model_testing = "model_testing"
    data_importer = "data_importer"
    delete_history = "delete_history"
    multilingual = "multilingual"
    data_generator = "data_generator"
    faq_importer = "faq_importer"
    pyscript_evaluator = "pyscript_evaluator"
    message_broadcast = "message_broadcast"
    web_search = "web_search"
    scheduler_evaluator = "scheduler_evaluator"
    content_importer = "content_importer"
    mail_channel_process_mails = "email_channel_process_mails"
    mail_channel_read_mails = "email_channel_read_mails"


class EventRequestType(str, Enum):
    trigger_async = "trigger_async"
    update_schedule = "update_schedule"
    add_schedule = "add_schedule"
    resend_broadcast = "resend_broadcast"


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
    HANGOUTS = "hangouts"
    MESSENGER = "messenger"
    SLACK = "slack"
    TELEGRAM = "telegram"
    INSTAGRAM = "instagram"
    BUSINESS_MESSAGES = "business_messages"
    LINE = "line"
    MAIL = "mail"

class ElementTypes(str, Enum):
    LINK = "link"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    BUTTON = "button"
    DROPDOWN = "dropdown"
    QUICK_REPLY = "quick_reply"


class WhatsappBSPTypes(str, Enum):
    bsp_360dialog = "360dialog"


class GPT3ResourceTypes(str, Enum):
    embeddings = "embeddings"
    chat_completion = "chat/completions"


class LLMResourceProvider(str, Enum):
    azure = "azure"
    openai = "openai"


class KaironSystemSlots(str, Enum):
    kairon_action_response = "kairon_action_response"
    bot = 'bot'
    image = "image"
    audio = "audio"
    video = "video"
    document = "document"
    doc_url = "doc_url"
    order = "order"
    payment = "payment"
    longitude = "longitude"
    latitude = "latitude"
    flow_reply = "flow_reply"
    quick_reply = "quick_reply"
    http_status_code = "http_status_code"


class VectorEmbeddingsDatabases(str, Enum):
    qdrant = "qdrant"


class ActorType(str, Enum):
    pyscript_runner = "pyscript_runner"
    callable_runner = "callable_runner"
