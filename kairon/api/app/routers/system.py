from fastapi import APIRouter
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
