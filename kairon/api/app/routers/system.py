from fastapi import APIRouter
from rasa.shared.core.constants import DEFAULT_INTENTS, DEFAULT_ACTION_NAMES, DEFAULT_SLOT_NAMES
from kairon.shared.utils import Utility
from kairon.api.models import Response

router = APIRouter()


@router.get("/properties", response_model=Response)
async def get_app_properties():
    """
    List social media logins enabled.
    """
    return Response(data=Utility.get_app_properties())


@router.get("/metadata", response_model=Response)
async def get_system_metadata():
    """
    Retrieves System Metadata.
    """
    return Response(data=Utility.system_metadata)


@router.get("/templates/use-case", response_model=Response)
async def get_templates():
    """
    Fetches use-case templates name
    """
    return {"data": {"use-cases": Utility.list_directories("./template/use-cases")}}


@router.get("/default/names", response_model=Response)
async def get_default_names():
    """
    Fetches the default intents, action names, and slot names.
    """
    default_names = DEFAULT_INTENTS + DEFAULT_ACTION_NAMES + list(DEFAULT_SLOT_NAMES)
    return Response(data={"default_names": default_names})
