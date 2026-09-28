from typing import Text
from kairon.shared.chat.processor import ChatDataProcessor
from fbmessenger import MessengerClient


class InstagramProcessor:

    def __init__(self, bot: Text, user: Text):
        self.bot = bot
        self.user = user
        self.messenger_client = self._init_messenger_client()

    def _init_messenger_client(self) -> MessengerClient:
        messenger_conf = ChatDataProcessor.get_channel_config("instagram", self.bot, mask_characters=False)
        page_access_token = messenger_conf["config"]["page_access_token"]
        return MessengerClient(page_access_token)

    async def get_page_details(self) -> dict:
        params = f"fields=id,name&access_token={self.messenger_client.auth_args['access_token']}"
        resp = self.messenger_client.session.get(f"{self.messenger_client.graph_url}/me/?{params}")
        return resp.json()

    async def get_user_account_details_from_page(self) -> dict:
        page_details = await self.get_page_details()
        page_id = page_details.get('id')
        params = f"fields=instagram_business_account&access_token={self.messenger_client.auth_args['access_token']}"
        resp = self.messenger_client.session.get(f"{self.messenger_client.graph_url}/{page_id}/?{params}")
        return resp.json()

    async def get_user_media_posts(self) -> dict:
        account_details = await self.get_user_account_details_from_page()
        ig_user_id = account_details.get('instagram_business_account', {}).get('id')

        if not ig_user_id:
            return {"error": "Instagram business account not linked to the page"}

        params = (
            f"fields=id,ig_id,media_product_type,media_type,media_url,thumbnail_url,"
            f"timestamp,username,permalink,caption,like_count,comments_count"
            f"&access_token={self.messenger_client.auth_args['access_token']}"
        )
        resp = self.messenger_client.session.get(
            f"{self.messenger_client.graph_url}/{ig_user_id}/media/?{params}"
        )
        return resp.json()
