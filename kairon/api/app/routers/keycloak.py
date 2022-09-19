from fastapi import APIRouter
from fastapi import Depends

from kairon import Utility
from kairon.api.models import Response, IDPConfig
from kairon.idp.processor import IDPProcessor
from kairon.shared.auth import Authentication
from kairon.shared.models import User

router = APIRouter()


@router.get("/provider/list", response_model=Response)
async def get_supported_ipds(current_user: User = Depends(Authentication.get_current_user)):
    """
    Get list of supported provider
    """
    data = IDPProcessor.get_supported_provider_list()
    return Response(data=data)


@router.get("/provider/fields", response_model=Response)
async def idp_privider_fields(current_user: User = Depends(Authentication.get_current_user)):
    """
    Fetch required fields for idp providers
    """
    data = Utility.system_metadata["providers"]
    return Response(data=data)


@router.post("/config", response_model=Response)
async def set_idp_config(request_data: IDPConfig, current_user: User = Depends(Authentication.get_current_user)):
    """
    Save keycloak config for account
    """
    IDPProcessor.save_idp_config(current_user, request_data.dict())
    return Response(data={"message": "Keycloak config saved"})


@router.get("/config", response_model=Response)
async def get_idp_config(current_user: User = Depends(Authentication.get_current_user)):
    """
    Fetch keycloak config for account
    """
    data = IDPProcessor.get_idp_config(current_user.account)
    return Response(data=data)
