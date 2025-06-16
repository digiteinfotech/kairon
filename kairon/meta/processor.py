import asyncio
import json
from typing import Text, List
from loguru import logger
import requests
from kairon.shared.catalog_sync.data_objects import CatalogProviderMapping
from urllib.parse import quote


class MetaProcessor:

    def __init__(self, access_token: Text, catalog_id:Text):
        self.catalog_id = catalog_id
        self.access_token = access_token
        self.headers = {}
        self.processed_data = []

    def preprocess_data(self,bot: Text, data: List[dict], method: Text, provider: str):
        doc = CatalogProviderMapping.objects(provider=provider).first()
        if not doc:
            raise Exception(f"Metadata mappings not found for provider={provider}")

        meta_fields = list(doc.meta_mappings.keys())

        for item in data:
            transformed_item = {"retailer_id": item["id"]}

            if method == "UPDATE":
                transformed_item["data"] = {}
                for field in meta_fields:
                    if field in item:
                        value = int(item[field]) if field == "price" else item[field]
                        transformed_item["data"][field] = value

            else:
                transformed_item["data"] = {"currency": "INR"}
                for field in meta_fields:
                    if field in item:
                        value = int(item[field]) if field == "price" else item[field]
                        transformed_item["data"][field] = value

            transformed_item["method"] = method
            transformed_item["item_type"] = "PRODUCT_ITEM"
            self.processed_data.append(transformed_item)

        return self.processed_data

    def preprocess_delete_data(self, remaining_ids: List):
        """
        Creates a payload for deleting stale records from the catalog.
        Args:
            remaining_ids: List of primary keys that need to be deleted.
        Returns:
            Dict: Payload containing the list of delete operations.
        """
        return [{"retailer_id": id, "method": "DELETE"} for id in remaining_ids]

    async def push_meta_catalog(self):
        """
        Sync the data to meta when event type is 'push_menu'
        """
        try:
            req = quote(json.dumps(self.processed_data))
            base_url = f"https://graph.facebook.com/v21.0/{self.catalog_id}/batch"
            url = f"{base_url}?item_type=PRODUCT_ITEM&requests={req}"

            data = {
                "access_token": self.access_token,
            }

            response = await asyncio.to_thread(requests.post, url, headers={}, data=data)
            response.raise_for_status()
            print("Response JSON:", response.json())
            print("Successfully synced product items to Meta catalog(Push Menu)")
        except Exception as e:
            logger.exception(f"Error syncing product items to Meta catalog for push menu: {str(e)}")
            raise e

    async def update_meta_catalog(self):
        """
        Sync the data to meta when event type is 'push_menu'
        """
        try:
            req = quote(json.dumps(self.processed_data))
            base_url = f"https://graph.facebook.com/v21.0/{self.catalog_id}/batch"
            url = f"{base_url}?item_type=PRODUCT_ITEM&requests={req}"

            data = {
                "access_token": self.access_token,
            }

            response = await asyncio.to_thread(requests.post, url, headers={}, data=data)
            response.raise_for_status()
            print("Response JSON:", response.json())
            print("Successfully synced product items to Meta catalog(Item Toggle)")
        except Exception as e:
            logger.exception(f"Error syncing product items to Meta catalog for item toggle: {str(e)}")
            raise e


    async def delete_meta_catalog(self, delete_payload: list):
        """
        Sync the data to meta when event type is 'push_menu'
        """
        try:
            req = quote(json.dumps(delete_payload))
            base_url = f"https://graph.facebook.com/v21.0/{self.catalog_id}/batch"
            url = f"{base_url}?requests={req}"

            data = {
                "access_token": self.access_token,
            }
            response = await asyncio.to_thread(requests.post, url, headers={}, data=data)
            response.raise_for_status()
            print("Response JSON:", response.json())
            print("Successfully deleted data from meta.")
        except Exception as e:
            logger.exception(f"Error deleting data from meta: {str(e)}")
            raise e