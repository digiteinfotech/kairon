import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.shared.utils import Utility

Utility.load_system_metadata()

import pytest
import responses
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
from kairon.shared.data.constant import KEENABLE_SEARCH_PUBLIC_URL, KEENABLE_SEARCH_URL, STATUSES
from kairon.shared.data.data_models import KeenableSearchActionRequest
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import StoryStepType

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

    @responses.activate
    def test_perform_keenable_search_error(self):
        responses.add(responses.POST, KEENABLE_SEARCH_PUBLIC_URL, status=429, json={"error": "Too many requests"})
        with pytest.raises(ActionFailure, match="Keenable search failed with status 429"):
            ActionUtility.perform_keenable_search(None, 'what is kanban', num=1)

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
        request = KeenableSearchActionRequest(name='Keenable_Action')
        assert request.name == 'keenable_action'
        assert request.api_key is None
        assert request.num_results == 1
        with pytest.raises(ValidationError, match="num_results must be greater than or equal to 1!"):
            KeenableSearchActionRequest(name='keenable_action', num_results=0)

    def test_keenable_search_action_registered(self):
        assert ActionType.keenable_search_action.value == 'keenable_search_action'
        assert StoryStepType.keenable_search_action.value == 'KEENABLE_SEARCH_ACTION'
        config = ActionSerializer.action_lookup[ActionType.keenable_search_action.value]
        assert config['db_model'] == KeenableSearchAction
        assert config['validation_model'] == KeenableSearchActionRequest

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
