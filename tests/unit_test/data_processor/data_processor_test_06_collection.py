from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_get_collection_data_with_no_collection_data(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(DataProcessor.list_collection_data(bot))

        assert response == []

    def test_save_collection_data_with_with_keys_not_present(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number", "address"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        processor = CognitionDataProcessor()
        with pytest.raises(ValidationError, match='is_secure contains keys that are not present in data'):
            DataProcessor.save_collection_data(request_body, user, bot)


    def test_save_collection_data_with_collection_name_empty(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "",
            "is_secure": ["name", "mobile_number"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='collection name is empty'):
            DataProcessor.save_collection_data(request_body, user, bot)

    def test_save_collection_data_with_invalid_is_secure(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "user",
            "is_secure": "name, mobile_number",
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='is_secure should be list of keys'):
            DataProcessor.save_collection_data(request_body, user, bot)

    def test_save_collection_data_with_invalid_data(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number"],
            "data": "Mahesh"
        }
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Invalid value for data'):
            DataProcessor.save_collection_data(request_body, user, bot)

    def test_save_collection_data(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        processor = CognitionDataProcessor()
        collection_id = DataProcessor.save_collection_data(request_body, user, bot)
        pytest.collection_id = collection_id

    def test_save_collection_data_with_collection_name_already_exist(self):
        request_body = {
            "collection_name": "user",
            "is_secure": [],
            "data": {
                "name": "Hitesh",
                "age": 25,
                "mobile_number": "989284928928",
                "location": "Mumbai"
            }
        }
        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        DataProcessor.save_collection_data(request_body, user, bot)

    def test_get_collection_data(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(DataProcessor.list_collection_data(bot))

        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': ['name', 'mobile_number'],
                'is_non_editable': [],

                'data': {
                    'name': 'Mahesh',
                    'age': 24,
                    'mobile_number': '9876543210',
                    'location': 'Bangalore'
                }
            },
            {
                'collection_name': 'user',
                'is_secure': [],
                'is_non_editable': [],

                'data': {
                    'name': 'Hitesh',
                    'age': 25,
                    'mobile_number': '989284928928',
                    'location': 'Mumbai'
                }
            }
        ]

    def test_update_collection_data_with_keys_not_present(self):
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number", "aadhar"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }

        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(ValidationError, match='is_secure contains keys that are not present in data'):
            DataProcessor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data_with_collection_name_empty(self):
        request_body = {
            "collection_name": "",
            "is_secure": ["name", "mobile_number"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }

        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='collection name is empty'):
            DataProcessor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data_with_invalid_is_secure(self):
        request_body = {
            "collection_name": "user",
            "is_secure": "name, mobile_number",
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='is_secure should be list of keys'):
            DataProcessor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data_with_invalid_data(self):
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number"],
            "data": "Mahesh"
        }

        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Invalid value for data'):
            DataProcessor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data(self):
        request_body = {
            "collection_name": "user",
            "is_secure": ["mobile_number", "location"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        pytest.collection_id = DataProcessor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data_doesnot_exist(self):
        request_body = {
            "collection_name": "user_details",
            "is_secure": ["mobile_number", "location"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }

        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Collection Data with given id and collection_name not found!'):
            DataProcessor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_get_collection_data_after_update(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(DataProcessor.list_collection_data(bot))

        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': ['mobile_number', 'location'],
                'is_non_editable': [],

                'data': {
                    'name': 'Mahesh',
                    'age': 24,
                    'mobile_number': '9876543210',
                    'location': 'Bangalore'
                }
            },
            {
                'collection_name': 'user',
                'is_secure': [],
                'is_non_editable': [],

                'data': {
                    'name': 'Hitesh',
                    'age': 25,
                    'mobile_number': '989284928928',
                    'location': 'Mumbai'
                }
            }
        ]

    def test_get_collection_data_with_mismatch_filter_length(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Keys and values lists must be of the same length.'):
            list(DataProcessor.get_collection_data(bot, collection_name="user", key=["name", "location"],
                                               value=["Mahesh"]))

    def test_get_collection_data_with_filters(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(DataProcessor.get_collection_data(bot, collection_name="user", key=["name"],
                                                      value=["Mahesh"]))
        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': ['mobile_number', 'location'],
                'is_non_editable': [],
                'data': {
                    'name': 'Mahesh',
                    'age': 24,
                    'mobile_number': '9876543210',
                    'location': 'Bangalore'
                }
            }
        ]
        response = list(DataProcessor.get_collection_data(bot, collection_name="user", key=["name", "location"],
                                                      value=["Mahesh", "Mumbai"]))
        for coll in response:
            coll.pop("_id")
        assert response == []
        response = list(DataProcessor.get_collection_data(bot, collection_name="user", key=["name", "location"],
                                                      value=["Hitesh", "Mumbai"]))
        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': [],
                'is_non_editable': [],
                'data': {
                    'name': 'Hitesh',
                    'age': 25,
                    'mobile_number': '989284928928',
                    'location': 'Mumbai'
                }
            }
        ]

    def test_get_collection_data_pagination_full_verification(self):
        bot = "test_bot"
        from unittest.mock import patch, MagicMock

        mock_docs = []
        for i in range(5):
            mock_obj = MagicMock()
            mock_obj.to_mongo().to_dict.return_value = {
                "_id": ObjectId(),
                "collection_name": "user",
                "is_secure": [],
                "is_non_editable": [],
                "data": {"index": i},
            }
            mock_docs.append(mock_obj)

        full_queryset = MagicMock()
        full_queryset.__iter__.return_value = iter(mock_docs)

        paginated_queryset = MagicMock()
        paginated_queryset.__iter__.return_value = iter(mock_docs[2:4])

        with patch("kairon.shared.data.collection_processor.CollectionData.objects") as objects_mock:
            objects_mock.return_value.order_by.return_value = objects_mock.return_value
            objects_mock.return_value.skip.return_value = objects_mock.return_value
            objects_mock.return_value.limit.return_value = paginated_queryset

            results = list(
                DataProcessor.get_collection_data(
                    bot,
                    collection_name="user",
                    key=[],
                    value=[],
                    page_size=2,
                    start_idx=2,
                )
            )

            assert len(results) == 2
            assert results[0]["data"]["index"] == 2
            assert results[1]["data"]["index"] == 3

            objects_mock.return_value.order_by.assert_called_once()
            objects_mock.return_value.skip.assert_called_once_with(2)
            objects_mock.return_value.limit.assert_called_once_with(2)

    def test_get_collection_data_pagination_negative_when_start_or_size_none(self):
        from unittest.mock import patch, MagicMock
        bot = "test_bot"
        mock_obj = MagicMock()
        mock_obj.to_mongo().to_dict.return_value = {
            "_id": ObjectId(),
            "collection_name": "user",
            "is_secure": [],
            "is_non_editable": [],
            "data": {"name": "A"},
        }

        mock_queryset = MagicMock()
        mock_queryset.__iter__.return_value = iter([mock_obj])
        with patch(
                "kairon.shared.data.collection_processor.CollectionData.objects",
                return_value=mock_queryset
        ) as objects_mock:
            results = list(
                DataProcessor.get_collection_data(
                    bot,
                    collection_name="user",
                    key=[],
                    value=[],
                    start_idx=None,
                    page_size=5,
                )
            )

            assert len(results) == 1
            assert results[0]["data"]["name"] == "A"
            objects_mock.return_value.order_by.assert_not_called()
            objects_mock.return_value.skip.assert_not_called()
            objects_mock.return_value.limit.assert_not_called()


    def test_get_collection_data_with_collection_id(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = DataProcessor.get_collection_data_with_id(bot, collection_id=pytest.collection_id)
        print(response)
        assert response == {
            '_id': pytest.collection_id,
            'collection_name': 'user',
            'is_secure': ['mobile_number', 'location'],
            'is_non_editable': [],
            'data': {
                'name': 'Mahesh',
                'age': 24,
                'mobile_number': '9876543210',
                'location': 'Bangalore'
            }
        }

    def test_delete_collection_data_doesnot_exist(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Collection Data does not exists!'):
            DataProcessor.delete_collection_data("66b1d6218d29ff530381eed5", bot, user)

    def test_delete_collection_data(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        DataProcessor.delete_collection_data(pytest.collection_id, bot, user)

    def test_get_collection_data_with_collection_id_doesnot_exists(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Collection data does not exists!'):
            DataProcessor.get_collection_data_with_id(bot, collection_id=pytest.collection_id)

    def test_get_collection_data_after_delete(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(DataProcessor.list_collection_data(bot))

        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': [],
                'is_non_editable': [],

                'data': {
                    'name': 'Hitesh',
                    'age': 25,
                    'mobile_number': '989284928928',
                    'location': 'Mumbai'
                }
            }
        ]

    def test_get_collection_data_with_timestamp(self):
        bot = 'test_bot'
        user = 'test_user'
        timestamp = utc_now()

        processor = CognitionDataProcessor()

        request_body_1 = {
            "collection_name": "user",
            "is_secure": [
                "aadhar",
                "pan"
            ],
            'is_non_editable': [],

            "data": {
                "name": "User1",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore",
                "aadhar": "1234",
                "pan": "ABCD123"
            },
        }

        request_body_2 = {
            "collection_name": "user",
            "is_secure": [
                "aadhar",
                "pan"
            ],
            "data": {
                "name": "User2",
                "age": 24,
                "mobile_number": "9876543211",
                "location": "Mumbai",
                "aadhar": "1234",
                "pan": "ABCD123"
            },
        }

        DataProcessor.save_collection_data(request_body_1, user, bot)
        DataProcessor.save_collection_data(request_body_2, user, bot)

        response = list(DataProcessor.get_collection_data_with_timestamp(
            bot,
            collection_name="user",
            start_time=timestamp,
            end_time=utc_now(),
            data_filter={"name": "User1"}
        ))
        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': ["aadhar",
                              "pan"
                              ],
                'is_non_editable': [],

                'data': {
                    "name": "User1",
                    "age": 24,
                    "mobile_number": "9876543210",
                    "location": "Bangalore",
                    "aadhar": "1234",
                    "pan": "ABCD123"
                }
            }
        ]

        response = list(DataProcessor.get_collection_data_with_timestamp(
            bot,
            collection_name="user",
            # BSON keeps milliseconds, so utc_now() here can still match the row just saved.
            start_time=utc_now() + timedelta(seconds=1),
            end_time="2027-08-06T00:00:00+00:00",
            data_filter={"name": "User2"}
        ))
        for coll in response:
            coll.pop("_id")
        assert response == []

        response = list(DataProcessor.get_collection_data_with_timestamp(
            bot,
            collection_name="user",
            start_time=timestamp,
            end_time=utc_now(),
            data_filter={"name": "User3"}
        ))
        for coll in response:
            coll.pop("_id")
        assert response == []
