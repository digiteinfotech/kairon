from fastapi import APIRouter
from fastapi import Depends
from fastapi import Path

from kairon import Utility
from kairon.api.models import Response, IDPConfig
from kairon.idp.processor import IDPProcessor
from kairon.shared.auth import Authentication
from kairon.shared.models import User

router = APIRouter()


@router.get("/provider/fields", response_model=Response)
async def idp_provider_fields(current_user: User = Depends(Authentication.get_current_user)):
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
    broker_redirect_uri = IDPProcessor.save_idp_config(current_user, request_data.dict())
    return Response(message="config saved", data=broker_redirect_uri)


@router.get("/config", response_model=Response)
async def get_idp_config(current_user: User = Depends(Authentication.get_current_user)):
    """
    Fetch keycloak config for account
    """
    data = IDPProcessor.get_idp_config(current_user.account)
    return Response(data=data)


@router.delete("/config/{realm_name}", response_model=Response)
async def delete_idp_config(current_user: User = Depends(Authentication.get_current_user),
                            realm_name: str = Path(description="Realm name", examples=["DOMAIN"])):
    """
    Disable the idp config
    """
    IDPProcessor.delete_idp(realm_name, user=current_user.get_user())
    return Response(message="IDP config deleted")

