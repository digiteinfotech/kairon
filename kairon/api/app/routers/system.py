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
