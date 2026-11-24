import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.shared.utils import Utility

Utility.load_system_metadata()

import pytest
import requests
import responses
from unittest.mock import patch
from mongoengine import connect
from pydantic import ValidationError
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from responses import matchers

from kairon.actions.definitions.factory import ActionFactory
from kairon.actions.definitions.keenable import ActionKeenableSearch
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import Actions, ActionServerLogs, \
    KeenableSearchAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.data.action_serializer import ActionSerializer
from kairon.shared.data.constant import KEENABLE_API_KEY_REQUIRED, STATUSES
from kairon.shared.data.data_models import KeenableSearchActionRequest
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import StoryStepType

KEENABLE_SEARCH_URL = "https://api.keenable.ai/v1/search"
KEENABLE_SEARCH_PUBLIC_URL = "https://api.keenable.ai/v1/search/public"


def keenable_config(**overrides):
    return patch.dict(Utility.environment['action']['keenable'], overrides)


KEENABLE_RESPONSE = {
    "query": "what is kanban",
    "mode": "pro",
    "results": [
        {
            "title": "What Is Kanban? An Overview Of The Kanban Method",
            "url": "https://www.digite.com/kanban/what-is-kanban/",
            "description": "",
            "snippet": "Kanban visualizes both the process (the workflow) and the actual work passing through that process.",
            "acquired_at": "2026-11-14T01:33:04Z",
        },
        {
            "title": "Kanban Board",
            "url": "https://www.digite.com/kanban/kanban-board/",
            "description": "A Kanban board is a visual project management tool.",
            "snippet": "Longer page text",
        },
    ],
}


class TestKeenableSearchAction:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        yield
        KeenableSearchAction.objects(bot__startswith='test_keenable').delete()
        Actions.objects(bot__startswith='test_keenable').delete()

    @responses.activate
    def test_perform_keenable_search_keyless(self):
        responses.add(
            responses.POST, KEENABLE_SEARCH_PUBLIC_URL, json=KEENABLE_RESPONSE,
            match=[
                matchers.json_params_matcher(
                    {"query": "what is kanban", "max_results": 2, "snippet_max_length": 300}
                ),
                matchers.header_matcher({"X-Keenable-Title": "kairon"}),
            ],
        )
        with keenable_config(allow_keyless=True):
            results = ActionUtility.perform_keenable_search(None, 'what is kanban', num=2)
        assert results == [
            {
                'title': 'What Is Kanban? An Overview Of The Kanban Method',
                'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.',
                'link': 'https://www.digite.com/kanban/what-is-kanban/',
            },
            {
                'title': 'Kanban Board',
                'text': 'A Kanban board is a visual project management tool.',
                'link': 'https://www.digite.com/kanban/kanban-board/',
            },
        ]
        assert 'X-API-Key' not in responses.calls[0].request.headers

    @responses.activate
    def test_perform_keenable_search_with_key_and_website(self):
        responses.add(
            responses.POST, KEENABLE_SEARCH_URL, json=KEENABLE_RESPONSE,
            match=[
                matchers.json_params_matcher(
                    {"query": "what is kanban", "max_results": 1, "snippet_max_length": 300,
                     "site": "digite.com"}
                ),
                matchers.header_matcher({"X-API-Key": "test-key"}),
            ],
        )
        results = ActionUtility.perform_keenable_search('test-key', 'what is kanban', num=1, website='digite.com')
        assert len(results) == 2
        assert results[0]['link'] == 'https://www.digite.com/kanban/what-is-kanban/'

    def test_keenable_config_defaults(self):
        config = Utility.environment['action']['keenable']
        assert config['allow_keyless'] is False
        assert config['search_url'] == KEENABLE_SEARCH_URL
        assert config['public_search_url'] == KEENABLE_SEARCH_PUBLIC_URL
        assert config['search_timeout'] == 10
        assert config['app_title'] == 'kairon'

    @responses.activate
    def test_perform_keenable_search_keyless_disabled_requires_api_key(self):
        with pytest.raises(ActionFailure, match="api_key is required for Keenable search"):
            ActionUtility.perform_keenable_search(None, 'what is kanban', num=1)
        assert len(responses.calls) == 0

    @responses.activate
    def test_perform_keenable_search_uses_configured_values(self):
        responses.add(
            responses.POST, "https://keenable.example.com/search", json=KEENABLE_RESPONSE,
            match=[matchers.header_matcher({"X-Keenable-Title": "my-app", "X-API-Key": "test-key"})],
        )
        with keenable_config(search_url="https://keenable.example.com/search", app_title="my-app",
                             search_timeout=3), \
                patch("kairon.shared.actions.utils.requests.post", wraps=requests.post) as mock_post:
            results = ActionUtility.perform_keenable_search('test-key', 'what is kanban', num=1)
        assert len(results) == 2
        assert mock_post.call_args.kwargs['timeout'] == 3

    @responses.activate
    def test_perform_keenable_search_error(self):
        responses.add(responses.POST, KEENABLE_SEARCH_URL, status=429, json={"error": "Too many requests"})
        with pytest.raises(ActionFailure, match="Keenable search failed with status 429"):
            ActionUtility.perform_keenable_search('test-key', 'what is kanban', num=1)

    def test_keenable_search_action_data_object_defaults(self):
        action = KeenableSearchAction(name=' Keenable_Action ', bot='test_keenable_bot', user='test_user',
                                      failure_response=' ', num_results='abc')
        action.validate()
        assert action.name == 'keenable_action'
        assert action.api_key is None
        assert action.failure_response == 'I have failed to process your request.'
        assert action.num_results == 1
        assert action.dispatch_response

    def test_keenable_search_action_request_validation(self):
        api_key = {'value': 'KEENABLE_API_KEY', 'parameter_type': 'key_vault'}
        request = KeenableSearchActionRequest(name='Keenable_Action', api_key=api_key)
        assert request.name == 'keenable_action'
        assert request.api_key.value == 'KEENABLE_API_KEY'
        assert request.num_results == 1
        with pytest.raises(ValidationError, match="num_results must be greater than or equal to 1!"):
            KeenableSearchActionRequest(name='keenable_action', api_key=api_key, num_results=0)

    def test_keenable_search_action_request_missing_api_key(self):
        with pytest.raises(ValidationError) as e:
            KeenableSearchActionRequest(name='keenable_action')
        assert KEENABLE_API_KEY_REQUIRED in str(e.value)

    def test_keenable_search_action_request_keyless_allowed(self):
        with keenable_config(allow_keyless=True):
            request = KeenableSearchActionRequest(name='keenable_action')
        assert request.api_key is None

    def test_keenable_search_action_registered(self):
        assert ActionType.keenable_search_action.value == 'keenable_search_action'
        assert StoryStepType.keenable_search_action.value == 'KEENABLE_SEARCH_ACTION'
        config = ActionSerializer.action_lookup[ActionType.keenable_search_action.value]
        assert config['db_model'] == KeenableSearchAction
        assert config['validation_model'] == KeenableSearchActionRequest

    def test_keenable_import_fills_parameter_keys(self):
        modify = ActionSerializer.action_lookup[ActionType.keenable_search_action.value]["modify"]
        data = modify("bot", {
            "name": "keenable_import",
            "api_key": {"value": "secret", "parameter_type": "value"},
            "search_term": {"value": "slot_q", "parameter_type": "slot", "key": "custom"},
        })
        assert data["api_key"]["key"] == "api_key"
        assert data["search_term"]["key"] == "custom"
        assert modify("bot", {"name": "keyless"}) == {"name": "keyless"}

    def test_add_list_edit_keenable_search_action(self):
        processor = MongoProcessor()
        bot = 'test_keenable_processor'
        user = 'test_user'
        action_id = processor.add_keenable_search_action(
            {'name': 'keenable_search', 'num_results': 3, 'website': 'digite.com', 'set_slot': 'search_result'},
            bot, user
        )
        assert action_id
        assert Actions.objects(name='keenable_search', bot=bot).get().type == ActionType.keenable_search_action.value
        actions = list(processor.list_keenable_search_actions(bot, False))
        assert actions == [{
            'name': 'keenable_search', 'website': 'digite.com',
            'failure_response': 'I have failed to process your request.', 'num_results': 3,
            'dispatch_response': True, 'set_slot': 'search_result',
        }]

        with pytest.raises(AppException):
            processor.add_keenable_search_action({'name': 'keenable_search'}, bot, user)

        processor.edit_keenable_search_action(
            {'name': 'keenable_search', 'num_results': 5,
             'api_key': {'value': 'KEENABLE_API_KEY', 'parameter_type': 'key_vault'}},
            bot, user
        )
        action = list(processor.list_keenable_search_actions(bot))[0]
        assert action['num_results'] == 5
        assert action['api_key']['parameter_type'] == 'key_vault'
        assert action['api_key']['key'] == 'api_key'

        with pytest.raises(AppException, match='Keenable search action with name "missing" not found'):
            processor.edit_keenable_search_action({'name': 'missing'}, bot, user)

    def test_factory_returns_keenable_action(self):
        bot = 'test_keenable_factory'
        Actions(name='keenable_factory_action', type=ActionType.keenable_search_action.value, bot=bot,
                user='test_user').save()
        KeenableSearchAction(name='keenable_factory_action', bot=bot, user='test_user').save()
        assert isinstance(ActionFactory.get_instance(bot, 'keenable_factory_action'), ActionKeenableSearch)

    def test_retrieve_config_not_exists(self):
        with pytest.raises(ActionFailure, match="No Keenable search action found for given action and bot"):
            ActionKeenableSearch('test_keenable_missing', 'keenable_search').retrieve_config()

    @pytest.mark.asyncio
    async def test_execute_keenable_search_action(self, monkeypatch):
        bot = 'test_keenable_execute'
        action_name = 'keenable_execute_action'
        Actions(name=action_name, type=ActionType.keenable_search_action.value, bot=bot, user='test_user').save()
        KeenableSearchAction(name=action_name, bot=bot, user='test_user', num_results=1,
                             set_slot='search_result').save()
        captured = {}

        def _perform(api_key, search_term, **kwargs):
            captured.update({'api_key': api_key, 'search_term': search_term, **kwargs})
            return [{'title': 'Kanban', 'text': 'Kanban visualizes work.',
                     'link': 'https://www.digite.com/kanban/what-is-kanban/'}]

        monkeypatch.setattr(ActionUtility, 'perform_keenable_search', _perform)
        tracker = Tracker(sender_id='sender_keenable', slots={'bot': bot}, events=[],
                          latest_message={'text': 'what is kanban', 'intent_ranking': [{'name': 'test_run'}]},
                          paused=False, followup_action=None, active_loop=None,
                          latest_action_name=None)
        dispatcher = CollectingDispatcher()
        slots = await ActionKeenableSearch(bot, action_name).execute(dispatcher, tracker, {})
        assert captured == {'api_key': None, 'search_term': 'what is kanban', 'num': 1, 'website': None}
        assert 'what-is-kanban' in slots['search_result']
        assert dispatcher.messages[0]['text'] == slots['search_result']
        log = ActionServerLogs.objects(bot=bot, action=action_name).get()
        assert log.type == ActionType.keenable_search_action.value
        assert log.status == STATUSES.SUCCESS.value

    @pytest.mark.asyncio
    async def test_execute_keenable_search_action_configured_search_term_empty_message(self, monkeypatch):
        bot = 'test_keenable_execute_term'
        action_name = 'keenable_execute_term_action'
        Actions(name=action_name, type=ActionType.keenable_search_action.value, bot=bot, user='test_user').save()
        KeenableSearchAction(name=action_name, bot=bot, user='test_user', num_results=1,
                             search_term={'_cls': 'CustomActionRequestParameters', 'key': 'search_term',
                                          'value': 'what is kanban', 'parameter_type': 'value'}).save()
        captured = {}

        def _perform(api_key, search_term, **kwargs):
            captured.update({'search_term': search_term})
            return [{'title': 'Kanban', 'text': 'Kanban visualizes work.',
                     'link': 'https://www.digite.com/kanban/what-is-kanban/'}]

        monkeypatch.setattr(ActionUtility, 'perform_keenable_search', _perform)
        tracker = Tracker(sender_id='sender_keenable', slots={'bot': bot}, events=[],
                          latest_message={'text': '', 'intent_ranking': [{'name': 'test_run'}]},
                          paused=False, followup_action=None, active_loop=None,
                          latest_action_name=None)
        dispatcher = CollectingDispatcher()
        await ActionKeenableSearch(bot, action_name).execute(dispatcher, tracker, {})
        assert captured == {'search_term': 'what is kanban'}
        assert 'what-is-kanban' in dispatcher.messages[0]['text']

    def test_delete_slot_blocked_by_keenable_reference_in_any_case(self):
        from kairon.shared.data.data_objects import Slots
        processor = MongoProcessor()
        bot = 'test_keenable_slot_case'
        user = 'test_user'
        Slots(name='query', type='text', bot=bot, user=user).save()
        KeenableSearchAction(
            name='keenable_case', bot=bot, user=user,
            search_term={'parameter_type': 'slot', 'value': 'Query'},
        ).save()
        try:
            with pytest.raises(AppException, match='Slot is attached to action'):
                processor.delete_slot('QUERY', bot, user)
            assert Slots.objects(name='query', bot=bot, status=True).count() == 1
        finally:
            Slots.objects(bot=bot).delete()
            KeenableSearchAction.objects(bot=bot).delete()

    def test_is_slot_in_keenable_search_action_config(self):
        config = {'api_key': {'parameter_type': 'value', 'value': 'k'},
                  'search_term': {'parameter_type': 'slot', 'value': 'query'}}
        assert MongoProcessor.is_slot_in_keenable_search_action_config(config, 'query')
        assert not MongoProcessor.is_slot_in_keenable_search_action_config(config, 'other')
        assert MongoProcessor.is_slot_in_keenable_search_action_config({'set_slot': 'other'}, 'other')
