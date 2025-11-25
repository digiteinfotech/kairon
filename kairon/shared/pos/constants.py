from enum import Enum


class POSType(str, Enum):
    odoo = "odoo"


class OnboardingStatus(str, Enum):
    initiated = "Initiated"
    client_db_created = "Client DB Created"
    pos_activated = "POS Activated"
    completed = "Completed"


class PageType(str, Enum):
    pos_products = "pos_products"
    pos_orders = "pos_orders"


class OdooPOSActions(str, Enum):
    ACTION_POS_PRODUCT_LIST = 388
    ACTION_POS_ORDER_LIST = 380


class OdooPOSMenus(str, Enum):
    MENU_POS_PRODUCTS = 233
    MENU_POS_ORDERS = 231

