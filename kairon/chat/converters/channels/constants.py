from enum import Enum

class CHANNEL_TYPES(str, Enum):
    HANGOUT = "hangout"
    MESSENGER = "messenger"
    SLACK = "slack"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    MSTEAMS = "msteams"

class ELEMENT_TYPE(str, Enum):
    LINK = "link"
    IMAGE = "image"
    VIDEO = "video"
    BUTTON = "button"