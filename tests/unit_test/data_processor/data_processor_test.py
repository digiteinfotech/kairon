from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_collection_data_filterable_attrs_populated_on_save(self):
        from kairon.shared.cognition.data_objects import build_collection_filterable_attrs
        data = {
            "name": "Test",
            "age": 30,
            "score": 9.5,
            "active": True,
            "nested": {"key": "val"},
            "items": [1, 2, 3],
        }
        doc = CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="test_filterable",
            data=data
        )
        doc.save()

        saved = CollectionData.objects(bot="test_bot", collection_name="test_filterable").first()
        expected = build_collection_filterable_attrs(data)
        assert saved.filterable_attrs == expected
        attr_keys = {a["k"] for a in saved.filterable_attrs}
        assert attr_keys == {"name", "age", "score", "active"}
        assert "nested" not in attr_keys
        assert "items" not in attr_keys

        saved.delete()

    def test_collection_data_filterable_attrs_excludes_secure_fields(self):
        data = {
            "name": "Test",
            "age": 30,
            "token": "secret123",
            "active": True,
        }
        doc = CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="test_filterable_secure",
            data=data,
            is_secure=["token"]
        )
        doc.save()

        saved = CollectionData.objects(bot="test_bot", collection_name="test_filterable_secure").first()
        attr_keys = {a["k"] for a in saved.filterable_attrs}
        assert attr_keys == {"name", "age", "active"}
        assert "token" not in attr_keys

        saved.delete()

    def test_get_collection_data_with_filters_list(self, mock_collection_data):
        collection_name = "crop_details"
        filters = [
            {
                "column": "age",
                "condition": "gte",
                "value": "26"
            },
            {
                "column": "name",
                "condition": "iendswith",
                "value": "esh"
            },
        ]
        result = DataProcessor.get_broadcast_collection_data(bot="test_bot",
                                                             collection_name=collection_name,
                                                             filters=filters)
        assert len(result) == 4
        assert result == [
            {'name': 'Mahesh', 'mobile_number': '9876543000', 'crop': 'wheat', 'status': 'stage-1', 'age': '26'},
            {'name': 'Ganesh', 'mobile_number': '9876543001', 'crop': 'Paddy', 'status': 'stage-2', 'age': '26'},
            {'name': 'Hitesh', 'mobile_number': '9876543001', 'crop': 'Okra', 'status': 'stage-4', 'age': '27'},
            {'name': 'Hitesh', 'mobile_number': '9876543002', 'crop': 'wheat', 'status': 'stage-3', 'age': '27'}
        ]

        collection_name = "details"
        filters = [
            {
                "column": "age",
                "condition": "lt",
                "value": "26"
            },
            {
                "column": "age",
                "condition": "gt",
                "value": "20"
            },
            {
                "column": "name",
                "condition": "nin",
                "value": ["Mahesh", "Hitesh"]
            },
        ]
        result = DataProcessor.get_broadcast_collection_data(bot="test_bot",
                                                             collection_name=collection_name,
                                                             filters=filters)
        assert len(result) == 2
        assert result == [
            {'name': 'Mayank', 'mobile_number': '9876543000', 'crop': 'wheat', 'status': 'stage-1', 'age': '22'},
            {'name': 'Ganesh', 'mobile_number': '9876543001', 'crop': 'Paddy', 'status': 'stage-2', 'age': '23'}
        ]

        collection_name = "crop_details"
        filters = [
            {
                "column": "age",
                "condition": "",
                "value": "26"
            }
        ]
        result = DataProcessor.get_broadcast_collection_data(bot="test_bot",
                                                             collection_name=collection_name,
                                                             filters=filters)
        assert len(result) == 2
        assert result == [
            {'name': 'Mahesh', 'mobile_number': '9876543000', 'crop': 'wheat', 'status': 'stage-1', 'age': '26'},
            {'name': 'Ganesh', 'mobile_number': '9876543001', 'crop': 'Paddy', 'status': 'stage-2', 'age': '26'},
        ]

        collection_name = "crop_details"
        filters = []
        result = DataProcessor.get_broadcast_collection_data(bot="test_bot",
                                                             collection_name=collection_name,
                                                             filters=filters)
        assert len(result) == 4
        assert result == [
            {'name': 'Mahesh', 'mobile_number': '9876543000', 'crop': 'wheat', 'status': 'stage-1', 'age': '26'},
            {'name': 'Ganesh', 'mobile_number': '9876543001', 'crop': 'Paddy', 'status': 'stage-2', 'age': '26'},
            {'name': 'Hitesh', 'mobile_number': '9876543001', 'crop': 'Okra', 'status': 'stage-4', 'age': '27'},
            {'name': 'Hitesh', 'mobile_number': '9876543002', 'crop': 'wheat', 'status': 'stage-3', 'age': '27'}
        ]

    def test_get_collection_filter_data_count(self):
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="details_1",
            data={
                "name": "Mahesh",
                "mobile_number": "9876543000",
                "crop": "wheat",
                "status": "stage-1",
                "age": "22"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="details_1",
            data={
                "name": "Mayank",
                "mobile_number": "9876543000",
                "crop": "wheat",
                "status": "stage-1",
                "age": "22"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="details_1",
            data={
                "name": "Ganesh",
                "mobile_number": "9876543001",
                "crop": "Paddy",
                "status": "stage-2",
                "age": "23"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="crop_details_1",
            data={
                "name": "Mahesh",
                "mobile_number": "9876543000",
                "crop": "wheat",
                "status": "stage-1",
                "age": "26"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="crop_details_1",
            data={
                "name": "Ganesh",
                "mobile_number": "9876543001",
                "crop": "Paddy",
                "status": "stage-2",
                "age": "26"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="crop_details_1",
            data={
                "name": "Hitesh",
                "mobile_number": "9876543001",
                "crop": "Okra",
                "status": "stage-4",
                "age": "27"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="details_1",
            data={
                "name": "Aniket",
                "mobile_number": "9876543003",
                "crop": "Okra",
                "status": "stage-4",
                "age": "26"
            }
        ).save()
        collection_name = "crop_details_1"
        filters = """[
            {
                "column": "age",
                "condition": "gte",
                "value": "26"
            },
            {
                "column": "name",
                "condition": "iendswith",
                "value": "esh"
            }
        ]"""
        result = DataProcessor.get_collection_filter_data_count(
            bot="test_bot",
            collection_name=collection_name,
            filters=filters
        )
        assert result == 3

        collection_name = "details_1"
        filters = '''[
            {
                "column": "age",
                "condition": "lt",
                "value": "26"
            },
            {
                "column": "age",
                "condition": "gt",
                "value": "20"
            },
            {
                "column": "name",
                "condition": "nin",
                "value": ["Mahesh", "Hitesh"]
            }
        ]'''
        result = DataProcessor.get_collection_filter_data_count(
            bot="test_bot",
            collection_name=collection_name,
            filters=filters
        )
        assert result == 2

        collection_name = "details_1"
        filters = """[
            {
                "column": "age",
                "condition": "",
                "value": "26"
            }
        ]"""
        result = DataProcessor.get_collection_filter_data_count(
            bot="test_bot",
            collection_name=collection_name,
            filters=filters
        )
        assert result == 1

        collection_name = "details_1"
        filters = []
        result = DataProcessor.get_collection_filter_data_count(
            bot="test_bot",
            collection_name=collection_name,
            filters=filters
        )
        assert result == 4
        CollectionData.objects(bot = "test_bot", collection_name="crop_details_1").delete()
        CollectionData.objects(bot = "test_bot", collection_name="details_1").delete()

    def test_single_filter_with_condition(self):
        bot = "test_bot"
        collection_name = "crop_details"
        filters = [
            {"column": "age", "condition": "gte", "value": 25}
        ]

        result = DataProcessor.get_collection_filter(bot, collection_name, filters)

        assert result == {
            "bot": "test_bot",
            "collection_name": "crop_details",
            "$and": [{"filterable_attrs": {"$elemMatch": {"k": "age", "v": {"$gte": 25}}}}]
        }

    def test_multiple_filters_with_conditions(self):
        bot = "test_bot"
        collection_name = "farmers"
        filters = [
            {"column": "age", "condition": "gte", "value": 20},
            {"column": "city", "condition": "iexact", "value": "Delhi"},
            {"column": "status", "condition": "in", "value": ["active", "pending"]}
        ]

        result = DataProcessor.get_collection_filter(bot, collection_name, filters)

        assert result == {
            "bot": "test_bot",
            "collection_name": "farmers",
            "$and": [
                {"filterable_attrs": {"$elemMatch": {"k": "age", "v": {"$gte": 20}}}},
                {"filterable_attrs": {"$elemMatch": {"k": "city", "v": {"$regex": "^Delhi$", "$options": "i"}}}},
                {"filterable_attrs": {"$elemMatch": {"k": "status", "v": {"$in": ["active", "pending"]}}}}
            ]
        }

    def test_filter_without_condition(self):
        bot = "test_bot"
        collection_name = "crop_details"
        filters = [
            {"column": "name", "condition": "", "value": "Mahesh"}
        ]

        result = DataProcessor.get_collection_filter(bot, collection_name, filters)

        assert result == {
            "bot": "test_bot",
            "collection_name": "crop_details",
            "$and": [{"filterable_attrs": {"$elemMatch": {"k": "name", "v": "Mahesh"}}}]
        }

    def test_empty_filters_list(self):
        bot = "test_bot"
        collection_name = "crop_details"
        filters = []

        result = DataProcessor.get_collection_filter(bot, collection_name, filters)

        assert result == {
            "bot": "test_bot",
            "collection_name": "crop_details"
        }

    def test_missing_keys_in_filter(self):
        bot = "test_bot"
        collection_name = "crop_details"
        filters = [
            {"column": "name", "value": "Mahesh"}  # no condition key
        ]

        result = DataProcessor.get_collection_filter(bot, collection_name, filters)

        assert result == {
            "bot": "test_bot",
            "collection_name": "crop_details",
            "$and": [{"filterable_attrs": {"$elemMatch": {"k": "name", "v": "Mahesh"}}}]
        }

    def test_get_decoded_data_with_valid_encoded_json(self):
        """Should decode and parse valid URL-encoded JSON string."""
        data = '[{"column": "brand", "condition": "equals", "value": "city"}]'
        result = DataProcessor.get_decoded_data(data)
        assert isinstance(result, list)
        assert result[0]["column"] == "brand"
        assert result[0]["value"] == "city"

    def test_get_decoded_data_with_valid_json_string(self):
        """Should parse normal JSON string without URL encoding."""
        data = '[{"column": "brand", "condition": "equals"}]'
        result = DataProcessor.get_decoded_data(data)
        assert isinstance(result, list)
        assert result[0]["column"] == "brand"

    def test_get_decoded_data_with_none(self):
        """Should return default '[]' when data is None."""
        result = DataProcessor.get_decoded_data(None)
        assert result == []

    def test_get_decoded_data_with_empty_string(self):
        """Should return default '[]' when data is empty."""
        result = DataProcessor.get_decoded_data("")
        assert result == []

    def test_get_decoded_data_with_invalid_json(self):
        """Should raise ValueError for invalid JSON."""
        with pytest.raises(ValueError, match="Invalid data format."):
            DataProcessor.get_decoded_data("not_json")

    def test_get_decoded_data_with_partial_encoding(self):
        """Should handle cases with partial URL encoding correctly."""
        raw_data = '[{"key":"val ue"}]'
        encoded = '%5B%7B%22key%22%3A%22val ue%22%7D%5D'
        result = DataProcessor.get_decoded_data(encoded)
        assert isinstance(result, list)
        assert result[0]["key"] == "val ue"
