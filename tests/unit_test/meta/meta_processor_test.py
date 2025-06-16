import json
import os
from urllib.parse import unquote, urlparse, parse_qs

import pytest
import requests
from mongoengine import connect
from unittest.mock import patch, Mock
from kairon import Utility
from kairon.meta.processor import MetaProcessor
from kairon.shared.catalog_sync.data_objects import CatalogProviderMapping

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

class TestMetaProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        connect(**Utility.mongoengine_connection())

    def test_preprocess_data_create_success(self):
        bot = "test_bot"
        method = "CREATE"
        catalog_id = "12345"
        access_token = "test_token"
        provider = "petpooja"

        CatalogProviderMapping(
            provider=provider,
            meta_mappings={
                "name": {"source": "itemname", "default": "No title"},
                "description": {"source": "itemdescription", "default": "No description available"},
                "price": {"source": "price", "default": 0.0},
                "availability": {"source": "in_stock", "default": "out of stock"},
                "image_url": {"source": "item_image_url", "default": "https://www.kairon.com/default-image.jpg"},
                "url": {"source": None, "default": "https://www.kairon.com/"},
                "brand": {"source": None, "default": "Sattva"},
                "condition": {"source": None, "default": "new"}
            },
            kv_mappings={
                "title": {"source": "itemname", "default": "No title"},
                "description": {"source": "itemdescription", "default": "No description available"},
                "price": {"source": "price", "default": 0.0},
                "facebook_product_category": {"source": "item_categoryid", "default": "Food and drink > General"},
                "availability": {"source": "in_stock", "default": "out of stock"}
            }
        ).save()

        payload_data = [
            {
                "id": "10539634",
                "name": "Potter 4",
                "description": "Chicken fillet in a bun  with coleslaw,lettuce, pickles and our  spicy cocktail sauce. This sandwich is made with care to make sure that each and every bite is packed with Mmmm",
                "price": 8700,
                "availability": "in stock",
                "image_url": "https://picsum.photos/id/237/200/300",
                "url": "https://www.kairon.com/",
                "brand": "Test Restaurant",
                "condition": "new"
            },
            {
                "id": "10539699",
                "name": "Potter 99",
                "description": "Chicken fillet in a bun  with coleslaw,lettuce, pickles and our  spicy cocktail sauce. This sandwich is made with care to make sure that each and every bite is packed with Mmmm",
                "price": 3426,
                "availability": "in stock",
                "image_url": "https://picsum.photos/id/237/200/300",
                "url": "https://www.kairon.com/",
                "brand": "Test Restaurant",
                "condition": "new"
            },
            {
                "id": "10539580",
                "name": "Potter 5",
                "description": "chicken fillet  nuggets come with a sauce of your choice (nugget/garlic sauce). Bite-sized pieces of tender all breast chicken fillets, marinated in our unique & signature blend, breaded and seasoned to perfection, then deep-fried until deliciously tender, crispy with a golden crust",
                "price": 3159,
                "availability": "in stock",
                "image_url": "https://picsum.photos/id/237/200/300",
                "url": "https://www.kairon.com/",
                "brand": "Test Restaurant",
                "condition": "new"
            }
        ]

        processor  = MetaProcessor(catalog_id=catalog_id, access_token=access_token)
        processed_data = processor.preprocess_data(bot, payload_data, method, provider)
        expected_processed_data = [
            {
                "retailer_id": "10539634",
                "data": {
                    "currency": "INR",
                    "name": "Potter 4",
                    "description": "Chicken fillet in a bun  with coleslaw,lettuce, pickles and our  spicy cocktail sauce. This sandwich is made with care to make sure that each and every bite is packed with Mmmm",
                    "price": 8700,
                    "availability": "in stock",
                    "image_url": "https://picsum.photos/id/237/200/300",
                    "url": "https://www.kairon.com/",
                    "brand": "Test Restaurant",
                    "condition": "new"
                },
                "method": "CREATE",
                "item_type": "PRODUCT_ITEM"
            },
            {
                "retailer_id": "10539699",
                "data": {
                    "currency": "INR",
                    "name": "Potter 99",
                    "description": "Chicken fillet in a bun  with coleslaw,lettuce, pickles and our  spicy cocktail sauce. This sandwich is made with care to make sure that each and every bite is packed with Mmmm",
                    "price": 3426,
                    "availability": "in stock",
                    "image_url": "https://picsum.photos/id/237/200/300",
                    "url": "https://www.kairon.com/",
                    "brand": "Test Restaurant",
                    "condition": "new"
                },
                "method": "CREATE",
                "item_type": "PRODUCT_ITEM"
            },
            {
                "retailer_id": "10539580",
                "data": {
                    "currency": "INR",
                    "name": "Potter 5",
                    "description": "chicken fillet  nuggets come with a sauce of your choice (nugget/garlic sauce). Bite-sized pieces of tender all breast chicken fillets, marinated in our unique & signature blend, breaded and seasoned to perfection, then deep-fried until deliciously tender, crispy with a golden crust",
                    "price": 3159,
                    "availability": "in stock",
                    "image_url": "https://picsum.photos/id/237/200/300",
                    "url": "https://www.kairon.com/",
                    "brand": "Test Restaurant",
                    "condition": "new"
                },
                "method": "CREATE",
                "item_type": "PRODUCT_ITEM"
            }
        ]

        assert processed_data == expected_processed_data
        CatalogProviderMapping.objects.delete()


    def test_preprocess_data_update_success(self):
        bot = "test_bot"
        method = "UPDATE"
        catalog_id = "12345"
        access_token = "test_token"
        provider = "petpooja"

        CatalogProviderMapping(
            provider=provider,
            meta_mappings={
                "name": {"source": "itemname", "default": "No title"},
                "description": {"source": "itemdescription", "default": "No description available"},
                "price": {"source": "price", "default": 0.0},
                "availability": {"source": "in_stock", "default": "out of stock"},
                "image_url": {"source": "item_image_url", "default": "https://www.kairon.com/default-image.jpg"},
                "url": {"source": None, "default": "https://www.kairon.com/"},
                "brand": {"source": None, "default": "Test Restaurant"},
                "condition": {"source": None, "default": "new"}
            },
            kv_mappings={
                "title": {"source": "itemname", "default": "No title"},
                "description": {"source": "itemdescription", "default": "No description available"},
                "price": {"source": "price", "default": 0.0},
                "facebook_product_category": {"source": "item_categoryid", "default": "Food and drink > General"},
                "availability": {"source": "in_stock", "default": "out of stock"}
            }
        ).save()

        payload_data = [
            {"id": "10539580", "availability": "out of stock"},
            {"id": "10539634", "availability": "out of stock"},
        ]

        processor  = MetaProcessor(catalog_id=catalog_id, access_token=access_token)
        processed_data = processor.preprocess_data(bot, payload_data, method, provider)
        expected_processed_data = [
            {
                "retailer_id": "10539580",
                "data": {
                    "availability": "out of stock"
                },
                "method": "UPDATE",
                "item_type": "PRODUCT_ITEM"
            },
            {
                "retailer_id": "10539634",
                "data": {
                    "availability": "out of stock"
                },
                "method": "UPDATE",
                "item_type": "PRODUCT_ITEM"
            }
        ]

        assert processed_data == expected_processed_data
        CatalogProviderMapping.objects.delete()

    def test_preprocess_delete_data_success(self):
        catalog_id = "12345"
        access_token = "test_token"

        payload_data = ['10539580','10539634']

        processor  = MetaProcessor(catalog_id=catalog_id, access_token=access_token)
        processed_data = processor.preprocess_delete_data(payload_data)
        expected_processed_data = [
            {'retailer_id': '10539580', 'method': 'DELETE'},
            {'retailer_id': '10539634', 'method': 'DELETE'}
        ]

        assert processed_data == expected_processed_data
        CatalogProviderMapping.objects.delete()

    @pytest.mark.asyncio
    async def test_push_meta_catalog_success(self):
        access_token = "test_token"
        catalog_id = "12345"

        processor = MetaProcessor(access_token=access_token, catalog_id=catalog_id)

        processor.processed_data = [
            {
                "retailer_id": "10539634",
                "data": {
                    "currency": "INR",
                    "name": "Potter 4",
                    "description": "Tasty item",
                    "price": 8700,
                    "availability": "in stock",
                    "image_url": "https://picsum.photos/id/237/200/300",
                    "url": "https://www.kairon.com/",
                    "brand": "Test Restaurant",
                    "condition": "new"
                },
                "method": "CREATE",
                "item_type": "PRODUCT_ITEM"
            },
            {
                "retailer_id": "1053963",
                "data": {
                    "currency": "INR",
                    "name": "Potter 4",
                    "description": "Tasty item",
                    "price": 8700,
                    "availability": "in stock",
                    "image_url": "https://picsum.photos/id/237/200/300",
                    "url": "https://www.kairon.com/",
                    "brand": "Test Restaurant",
                    "condition": "new"
                },
                "method": "CREATE",
                "item_type": "PRODUCT_ITEM"
            }
        ]

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {'handles': ['Acy4vFScxA7q5jquK1vKf20tlbWuXEW0dqxj3aSHY68QLMZriJaMuojJummx1sZhqlfj5DdKxqBw09YQ9DWVT2-6']}

        with patch("kairon.meta.processor.requests.post", return_value=mock_response) as mock_post:
            await processor.push_meta_catalog()

            assert mock_post.called is True
            called_url = mock_post.call_args[0][0]
            assert f"https://graph.facebook.com/v21.0/{catalog_id}/batch" in called_url

            data_arg = mock_post.call_args[1]["data"]
            assert data_arg["access_token"] == access_token

            called_url = mock_post.call_args[0][0]
            query_params = parse_qs(urlparse(called_url).query)
            encoded_requests = query_params.get("requests")[0]
            decoded_requests = json.loads(unquote(encoded_requests))

            assert any(item.get("method") == "CREATE" for item in decoded_requests)

    @pytest.mark.asyncio
    async def test_push_meta_catalog_failure(self):
        access_token = "test_token"
        catalog_id = "12345"

        processor = MetaProcessor(access_token=access_token, catalog_id=catalog_id)

        processor.processed_data = [
            {
                "retailer_id": "10539634",
                "data": {
                    "currency": "INR",
                    "name": "Potter 4",
                    "price": 8700,
                },
                "method": "CREATE",
                "item_type": "PRODUCT_ITEM"
            }
        ]

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "400 Client Error: Bad Request for url")

        with patch("kairon.meta.processor.requests.post", return_value=mock_response):
            with patch("kairon.meta.processor.logger") as mock_logger:
                with pytest.raises(requests.exceptions.HTTPError):
                    await processor.push_meta_catalog()

                assert mock_logger.exception.called
                log_message = mock_logger.exception.call_args[0][0]
                assert "Error syncing product items to Meta catalog for push menu" in log_message

    @pytest.mark.asyncio
    async def test_update_meta_catalog_success(self):
        access_token = "test_token"
        catalog_id = "12345"

        processor = MetaProcessor(access_token=access_token, catalog_id=catalog_id)

        processor.processed_data = [
            {
                "retailer_id": "10539580",
                "data": {
                    "availability": "out of stock"
                },
                "method": "UPDATE",
                "item_type": "PRODUCT_ITEM"
            }
        ]

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {'handles': ['Acy4vFScxA7q5jquK1vKf20tlbWuXEW0dqxj3aSHY68QLMZriJaMuojJummx1sZhqlfj5DdKxqBw09YQ9DWVT2-6']}

        with patch("kairon.meta.processor.requests.post", return_value=mock_response) as mock_post:
            await processor.update_meta_catalog()

            assert mock_post.called is True
            called_url = mock_post.call_args[0][0]
            assert f"https://graph.facebook.com/v21.0/{catalog_id}/batch" in called_url

            data_arg = mock_post.call_args[1]["data"]
            assert data_arg["access_token"] == access_token

            called_url = mock_post.call_args[0][0]
            query_params = parse_qs(urlparse(called_url).query)
            encoded_requests = query_params.get("requests")[0]
            decoded_requests = json.loads(unquote(encoded_requests))

            assert any(item.get("method") == "UPDATE" for item in decoded_requests)

    @pytest.mark.asyncio
    async def test_update_meta_catalog_failure(self):
        access_token = "test_token"
        catalog_id = "12345"

        processor = MetaProcessor(access_token=access_token, catalog_id=catalog_id)

        processor.processed_data = [
            {
                "retailer_id": "10539580",
                "data": {
                    "availability": "out of stock"
                },
                "method": "UPDATE",
                "item_type": "PRODUCT_ITEM"
            }
        ]

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "400 Client Error: Bad Request for url")

        with patch("kairon.meta.processor.requests.post", return_value=mock_response):
            with patch("kairon.meta.processor.logger") as mock_logger:
                with pytest.raises(requests.exceptions.HTTPError):
                    await processor.update_meta_catalog()

                assert mock_logger.exception.called
                log_message = mock_logger.exception.call_args[0][0]
                assert "Error syncing product items to Meta catalog for item toggle" in log_message

    @pytest.mark.asyncio
    async def test_delete_meta_catalog_success(self):
        access_token = "test_token"
        catalog_id = "12345"

        processor = MetaProcessor(access_token=access_token, catalog_id=catalog_id)

        delete_payload = [
            {'retailer_id': '10539580', 'method': 'DELETE'},
            {'retailer_id': '10539634', 'method': 'DELETE'}
        ]

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {'handles': ['Acy4vFScxA7q5jquK1vKf20tlbWuXEW0dqxj3aSHY68QLMZriJaMuojJummx1sZhqlfj5DdKxqBw09YQ9DWVT2-6']}

        with patch("kairon.meta.processor.requests.post", return_value=mock_response) as mock_post:
            await processor.delete_meta_catalog(delete_payload)

            assert mock_post.called is True
            called_url = mock_post.call_args[0][0]
            assert f"https://graph.facebook.com/v21.0/{catalog_id}/batch" in called_url

            data_arg = mock_post.call_args[1]["data"]
            assert data_arg["access_token"] == access_token

            called_url = mock_post.call_args[0][0]
            query_params = parse_qs(urlparse(called_url).query)
            encoded_requests = query_params.get("requests")[0]
            decoded_requests = json.loads(unquote(encoded_requests))

            assert any(item.get("method") == "DELETE" for item in decoded_requests)

    @pytest.mark.asyncio
    async def test_delete_meta_catalog_failure(self):
        access_token = "test_token"
        catalog_id = "12345"

        processor = MetaProcessor(access_token=access_token, catalog_id=catalog_id)

        delete_payload = [
            {'retailer_id': '10539580', 'method': 'DELETE'},
            {'retailer_id': '10539634', 'method': 'DELETE'}
        ]

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "400 Client Error: Bad Request for url")

        with patch("kairon.meta.processor.requests.post", return_value=mock_response):
            with patch("kairon.meta.processor.logger") as mock_logger:
                with pytest.raises(requests.exceptions.HTTPError):
                    await processor.delete_meta_catalog(delete_payload)

                assert mock_logger.exception.called
                log_message = mock_logger.exception.call_args[0][0]
                assert "Error deleting data from meta" in log_message