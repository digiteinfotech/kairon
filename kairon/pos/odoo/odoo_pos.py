from kairon import Utility
from kairon.pos.definitions.base import POSBase
from kairon.shared.pos.constants import OdooPOSMenus, OdooPOSActions, PageType
from kairon.shared.pos.processor import POSProcessor

pos_processor = POSProcessor()


class OdooPOS(POSBase):
    __base_url = Utility.environment["pos"]["odoo"]["odoo_url"]

    def onboarding(self, **kwargs):
        client_name = kwargs.get("client_name")
        bot = kwargs.get("bot")
        user = kwargs.get("user")
        result = pos_processor.onboarding_client(
            client_name=client_name,
            bot=bot,
            user=user
        )

        return result

    def authenticate(self, **kwargs):
        client_name = kwargs.get("client_name")
        bot = kwargs.get('bot')
        page_type = kwargs.get('page_type', PageType.pos_products.value)
        data = pos_processor.pos_login(client_name, bot)
        page_url_json = None
        if page_type == PageType.pos_products.value:
            page_url_json = self.products_list()
        elif page_type == PageType.pos_orders.value:
            page_url_json = self.orders_list()
        data.update(page_url_json)

        response = pos_processor.set_odoo_session_cookie(data)

        return response

    def products_list(self, **kwargs):
        action = OdooPOSActions.ACTION_POS_PRODUCT_LIST.value
        menu = OdooPOSMenus.MENU_POS_PRODUCTS.value
        product_list_json = {
            "url": f"{self.__base_url}/web#action={action}&model=product.template&view_type=kanban&cids=1&menu_id={menu}"
        }
        return product_list_json

    def orders_list(self, **kwargs):
        action = OdooPOSActions.ACTION_POS_ORDER_LIST.value
        menu = OdooPOSMenus.MENU_POS_ORDERS.value
        order_list_json = {
            "url": f"{self.__base_url}/web#action={action}&model=pos.order&view_type=list&cids=1&menu_id={menu}"
        }
        return order_list_json

