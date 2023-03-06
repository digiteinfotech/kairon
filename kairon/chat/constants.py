WABA_AUTH_TOKEN = "/api/v2/token"
WABA_GENERATE_KEY = "/api/v2/partners/{partner_id}/channels/{channel_id}/api_keys"
WABA_SEND_MESSAGE = "/v1/messages"
WABA_SET_WEBHOOK = "/v1/configs/webhook"
WABA_MESSAGE_STATUS_READ = "/v1/messages/message-id"
GET_WABA_TEMPLATE = "/api/v2/partners/{partner_id}/waba_accounts/{waba_account_id}/waba_templates?filters={{'id':'{template_id}}'}"
GET_WABA_ACCOUNT = "/api/v2/partners/{partner_id}/channels?filters={{'id':'{channel_id}'}}"

API_HEADER_KEY = "D360-API-KEY"
