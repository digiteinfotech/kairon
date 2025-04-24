from typing import  Text

from fastapi import Security, APIRouter, Path
from starlette.requests import Request

from kairon.api.models import Response
from kairon.events.definitions.catalog_sync import CatalogSync
from kairon.exceptions import AppException
from kairon.shared.auth import Authentication
from kairon.shared.catalog_sync.data_objects import CatalogSyncLogs
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.constants import CatalogProvider
from kairon.shared.constants import DESIGNER_ACCESS
from kairon.shared.models import User
from kairon.shared.utils import MailUtility

router = APIRouter()
cognition_processor = CognitionDataProcessor()

@router.post("/{provider}/{sync_type}/{bot}/{token}", response_model=Response)
async def sync_data(
    request: Request,
    provider: CatalogProvider = Path(description="Catalog provider name",
                                 examples=[CatalogProvider.PETPOOJA.value]),
    bot: Text = Path(description="Bot id"),
    sync_type: Text = Path(description="Sync Type"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
    token: str = Path(description="JWT token for authentication"),
):
    """
    Handles incoming data from catalog_sync (e.g., Petpooja) for processing, validation, and eventual storage.
    """

    request_body = await request.json()

    event = CatalogSync(
        bot=bot,
        user=current_user.get_user(),
        provider=provider,
        sync_type=sync_type,
        token=token
    )

    is_event_data = await event.validate(request_body=request_body)
    if is_event_data is True:
        event.enqueue()
        return {"message": "Sync in progress! Check logs."}
    else:
        raise AppException(is_event_data)



@router.post("/{provider}/{sync_type}/{bot}/{token}/{execution_id}", response_model=Response)
async def rerun_sync(
    provider: CatalogProvider = Path(description="Catalog provider name",
                                 examples=[CatalogProvider.PETPOOJA.value]),
    bot: Text = Path(description="Bot id"),
    sync_type: Text = Path(description="Sync Type"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
    token: str = Path(description="JWT token for authentication"),
    execution_id: str = Path(description="Execution id"),
):
    """
    Handles incoming data from catalog_sync (e.g., Petpooja) for processing, validation, and eventual storage.
    """
    sync_log_entry = CatalogSyncLogs.objects(execution_id=execution_id).first()
    if not sync_log_entry:
        raise AppException(f"Sync log with execution ID {execution_id} not found.")

    request_body = sync_log_entry.raw_payload

    event = CatalogSync(
        bot=bot,
        user=current_user.get_user(),
        provider=provider,
        sync_type=sync_type,
        token=token
    )

    is_event_data = await event.validate(request_body=request_body)
    if is_event_data is True:
        event.enqueue()
        return {"message": "Sync in progress! Check logs."}
    else:
        raise AppException(is_event_data)