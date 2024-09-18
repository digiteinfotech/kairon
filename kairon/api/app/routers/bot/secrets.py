from fastapi import APIRouter, Path, Security

from kairon.shared.auth import Authentication
from kairon.api.models import Response, KeyVaultRequest
from kairon.shared.constants import ADMIN_ACCESS, TESTER_ACCESS
from kairon.shared.models import User
from kairon.shared.data.processor import MongoProcessor

router = APIRouter()
mongo_processor = MongoProcessor()


@router.post("/add", response_model=Response)
async def add_secret(
        request_data: KeyVaultRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Stores the key, value to key vault.
    """
    key_id = mongo_processor.add_secret(request_data.key, request_data.value, current_user.get_bot(),
                                        current_user.get_user())
    return Response(data={"key_id": key_id}, message="Secret added!")


@router.get("/keys/{key}", response_model=Response)
async def get_secret(
        key: str = Path(description="key to retrieve", examples=["AWS_SECRET"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Returns value for key.
    """
    value = mongo_processor.get_secret(key, current_user.get_bot())
    return Response(data=value)


@router.get("/keys", response_model=Response)
async def list_keys(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Returns keys for bot.
    """
    keys = mongo_processor.list_secrets(bot=current_user.get_bot())
    return Response(data=keys)


@router.put("/update", response_model=Response)
async def update_secret_value(
        request_data: KeyVaultRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Updates secret value for key.
    """
    key_id = mongo_processor.update_secret(request_data.key, request_data.value, current_user.get_bot(),
                                           current_user.get_user())
    return Response(data={"key_id": key_id}, message="Secret updated!")


@router.delete("/{key}", response_model=Response)
async def delete_key_value(
        key: str = Path(description="key to retrieve", examples=["AWS_SECRET"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Deletes key value.
    """
    mongo_processor.delete_secret(key, current_user.get_bot(), user=current_user.get_user())
    return Response(data=None, message="Secret deleted!")
