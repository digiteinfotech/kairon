from enum import Enum

class CHANNEL_TYPES(str, Enum):
    HANGOUT = "hangout"
    MESSENGER = "messenger"
    SLACK = "slack"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"

class ELEMENT_TYPE(str, Enum):
    LINK = "link"
    IMAGE = "image"