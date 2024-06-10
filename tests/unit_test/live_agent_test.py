
import pytest
from unittest.mock import patch, MagicMock
from kairon.shared.actions.utils import ActionUtility
from rasa.core.channels import UserMessage
from kairon import Utility
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.live_agent.live_agent import LiveAgentHandler


@pytest.fixture
def mock_environment():
    return {
        'live_agent': {
            'enable': True,
            'url': 'http://live-agent-service',
            'auth_token': 'fake-token'
        }
    }

@pytest.fixture
def bot_id():
    return 'test_bot'


@pytest.fixture
def sender_id():
    return 'test_sender'


@pytest.fixture
def channel():
    return 'test_channel'


@pytest.fixture
def user_message():
    user_msg = MagicMock(spec=UserMessage)
    user_msg.text = "Hello, I need help"
    user_msg.sender_id = 'test_sender'
    user_msg.output_channel = MagicMock()
    user_msg.output_channel.name.return_value = 'test_channel'
    return user_msg


@pytest.fixture
def mock_bot_settings():
    return {'live_agent_enabled': True}


def test_is_live_agent_service_enabled(mock_environment):
    with patch.object(Utility, 'environment', mock_environment):
        assert LiveAgentHandler.is_live_agent_service_enabled() is True


def test_is_live_agent_service_available(mock_environment, bot_id, mock_bot_settings):
    with patch.object(Utility, 'environment', mock_environment), \
         patch.object(BotSettings, 'objects', return_value=MagicMock(get=MagicMock(return_value=MagicMock(to_mongo=MagicMock(return_value=MagicMock(to_dict=MagicMock(return_value=mock_bot_settings))))))):
        assert LiveAgentHandler.is_live_agent_service_available(bot_id) is True


def test_is_live_agent_service_available_disabled(mock_environment, bot_id):
    mock_environment['live_agent']['enable'] = False
    with patch.object(Utility, 'environment', mock_environment):
        assert LiveAgentHandler.is_live_agent_service_available(bot_id) is False


@pytest.mark.asyncio
async def test_request_live_agent(mock_environment, bot_id, sender_id, channel):
    with patch.object(Utility, 'environment', mock_environment), \
         patch.object(LiveAgentHandler, 'is_live_agent_service_available', return_value=True), \
         patch.object(ActionUtility, 'execute_request_async', return_value=({'data': None}, 200, None)):
        response = await LiveAgentHandler.request_live_agent(bot_id, sender_id, channel)
        assert response is None


@pytest.mark.asyncio
async def test_request_live_agent_service_unavailable(mock_environment, bot_id, sender_id, channel):
    with patch.object(Utility, 'environment', mock_environment), \
         patch.object(LiveAgentHandler, 'is_live_agent_service_available', return_value=False):
        response = await LiveAgentHandler.request_live_agent(bot_id, sender_id, channel)
        assert response == {'msg': 'Live agent service is not available'}


@pytest.mark.asyncio
async def test_process_live_agent(mock_environment, bot_id, user_message):
    with patch.object(Utility, 'environment', mock_environment), \
         patch.object(LiveAgentHandler, 'is_live_agent_service_available', return_value=True), \
         patch.object(ActionUtility, 'execute_request_async', return_value=({'data': None}, 200, None)):
        response = await LiveAgentHandler.process_live_agent(bot_id, user_message)
        assert response is None


@pytest.mark.asyncio
async def test_process_live_agent_service_unavailable(mock_environment, bot_id, user_message):
    with patch.object(Utility, 'environment', mock_environment), \
         patch.object(LiveAgentHandler, 'is_live_agent_service_available', return_value=False):
        with pytest.raises(Exception) as e:
            await LiveAgentHandler.process_live_agent(bot_id, user_message)
        assert str(e.value) == "Live agent service is not enabled"


@pytest.mark.asyncio
async def test_check_live_agent_active(mock_environment, bot_id, user_message):
    with patch.object(Utility, 'environment', mock_environment), \
         patch.object(LiveAgentHandler, 'is_live_agent_service_available', return_value=True), \
         patch.object(ActionUtility, 'execute_request_async', return_value=({'data': {'status': True}}, 200, None)):
        response = await LiveAgentHandler.check_live_agent_active(bot_id, user_message)
        assert response is True


@pytest.mark.asyncio
async def test_authenticate_agent(mock_environment, bot_id):
    user = 'test_user'
    with patch.object(Utility, 'environment', mock_environment), \
         patch.object(LiveAgentHandler, 'is_live_agent_service_available', return_value=True), \
         patch.object(ActionUtility, 'execute_request_async', return_value=({'data': 'auth_token'}, 200, None)):
        response = await LiveAgentHandler.authenticate_agent(user, bot_id)
        assert response == 'auth_token'

@pytest.mark.asyncio
async def test_authenticate_agent_service_unavailable(mock_environment, bot_id):
    user = 'test_user'
    with patch.object(Utility, 'environment', mock_environment), \
         patch.object(LiveAgentHandler, 'is_live_agent_service_available', return_value=False):
        response = await LiveAgentHandler.authenticate_agent(user, bot_id)
        assert not response


def test_get_channel():
    user_message = UserMessage('test', output_channel=MagicMock())
    user_message.output_channel.name.return_value = 'collector'
    ch = LiveAgentHandler.get_channel(user_message)
    assert ch == 'web'
    user_message.output_channel.name.return_value = 'other'
    ch = LiveAgentHandler.get_channel(user_message)
    assert ch == 'other'
