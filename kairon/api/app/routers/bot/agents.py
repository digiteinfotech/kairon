from fastapi import APIRouter, Security
from kairon.shared.auth import Authentication
from kairon.api.models import (
    Response,
)
from kairon.shared.constants import DESIGNER_ACCESS, TESTER_ACCESS
from kairon.shared.live_agent.models import LiveAgentRequest
from kairon.shared.live_agent.processor import LiveAgentsProcessor
from kairon.shared.models import User
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility

router = APIRouter()
mongo_processor = MongoProcessor()


@router.get("/live/params", response_model=Response)
async def live_agent_config_params(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Retrieves live agent config parameters.

    Includes required and optional fields for storing the config.
    """
    return Response(data=Utility.system_metadata['live_agents'])


@router.put("/live", response_model=Response)
async def save_live_agent_config(
        request_data: LiveAgentRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Stores live agent config.
    """
    LiveAgentsProcessor.save_config(request_data.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Live agent system added')


@router.get("/live", response_model=Response)
async def get_live_agent_config(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Retrieves the live agents config.
    """
    return Response(data={"agent": LiveAgentsProcessor.get_config(current_user.get_bot(), raise_error=False)})


@router.delete("/live", response_model=Response)
async def delete_live_agent_config(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes the live agent config.
    """
    LiveAgentsProcessor.delete_config(current_user.get_bot(), user=current_user.get_user())
    return Response(message='Live agent system deleted')
