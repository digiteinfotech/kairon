import os
from typing import List, Optional
from fastapi import UploadFile, File, Security, APIRouter, Query, HTTPException, Path
from starlette.requests import Request
from starlette.responses import FileResponse
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.chat.user_media import UserMedia
from kairon.api.models import Response, CognitiveDataRequest, CognitionSchemaRequest, CollectionDataRequest
from kairon.events.definitions.content_importer import DocContentImporterEvent
from kairon.events.definitions.faq_importer import FaqDataImporterEvent
from kairon.events.definitions.upload_handler import UploadHandler
from kairon.exceptions import AppException
from kairon.shared.auth import Authentication
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.cognition.data_objects import CognitionSchema
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.constants import ActorType, CatalogSyncClass, UploadHandlerClass, ChannelTypes
from kairon.shared.constants import DESIGNER_ACCESS
from kairon.shared.data.data_models import POSIntegrationRequest, BulkCollectionDataRequest
from kairon.shared.data.collection_processor import DataProcessor
from kairon.shared.data.data_models import  BulkDeleteRequest
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import User
from kairon.shared.utils import Utility

router = APIRouter()
processor = MongoProcessor()
cognition_processor = CognitionDataProcessor()


@router.post("/faq/upload", response_model=Response)
def upload_faq_files(
        csv_file: UploadFile = File(...),
        overwrite: bool = True,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Uploads faq csv/excel file
    """
    event = FaqDataImporterEvent(
        current_user.get_bot(), current_user.get_user(), overwrite=overwrite
    )
    event.validate(training_data_file=csv_file)
    event.enqueue()
    return {"message": "Upload in progress! Check logs."}


@router.get("/faq/download", response_model=Response)
async def download_faq_files(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Downloads faq into csv file
    """
    qna = list(processor.flatten_qna(bot=current_user.get_bot(), fetch_all=True))
    file, _ = Utility.download_csv(qna, filename="faq.csv")
    response = FileResponse(
        file, filename=os.path.basename(file)
    )
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=" + os.path.basename(file)
    return response


@router.post("/cognition/schema", response_model=Response)
async def save_cognition_schema(
        schema: CognitionSchemaRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Saves and updates cognition metadata into the bot
    """
    return {
        "message": "Schema saved!",
        "data": {
            "_id": cognition_processor.save_cognition_schema(
                    schema.dict(),
                    current_user.get_user(),
                    current_user.get_bot(),
            )
        }
    }


@router.delete("/cognition/schema/{schema_id}", response_model=Response)
async def delete_cognition_schema(
        schema_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Deletes cognition content of the bot
    """
    metadata = CognitionSchema.objects(bot=current_user.get_bot(), id=schema_id).first()
    if not metadata:
        raise AppException("Schema does not exists!")

    CognitionDataProcessor.validate_collection_name(current_user.get_bot(), metadata['collection_name'])

    metadata.activeStatus = False
    metadata.save()

    actor = ActorFactory.get_instance(ActorType.callable_runner.value)
    actor.execute(cognition_processor.delete_cognition_schema, schema_id, current_user.get_bot(),
                  user=current_user.get_user())
    return {
        "message": "Schema will be deleted soon!"
    }


@router.get("/cognition/schema", response_model=Response)
async def list_cognition_schema(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches cognition content of the bot
    """
    return {"data": list(cognition_processor.list_cognition_schema(current_user.get_bot()))}


@router.post("/cognition", response_model=Response)
async def save_cognition_data(
        cognition: CognitiveDataRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Saves cognition content into the bot
    """
    return {
        "message": "Record saved!",
        "data": {
            "_id": cognition_processor.save_cognition_data(
                    cognition.dict(),
                    current_user.get_user(),
                    current_user.get_bot(),
            )
        }
    }


@router.put("/cognition/{row_id}", response_model=Response)
async def update_cognition_data(
        row_id: str,
        cognition: CognitiveDataRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Updates cognition content into the bot
    """
    return {
        "message": "Record updated!",
        "data": {
            "_id": cognition_processor.update_cognition_data(
                row_id,
                cognition.dict(),
                current_user.get_user(),
                current_user.get_bot(),
            )
        }
    }


@router.delete("/cognition/{row_id}", response_model=Response)
async def delete_cognition_data(
        row_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Deletes cognition content of the bot
    """
    cognition_processor.delete_cognition_data(row_id, current_user.get_bot(), user=current_user.get_user())
    return {
        "message": "Record deleted!"
    }

@router.post("/cognition/delete_multiple", response_model=Response)
async def delete_multiple_cognition_data(
    request: BulkDeleteRequest,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Deletes multiple cognition content entries of the bot in bulk
    """
    cognition_processor.delete_multiple_cognition_data(request.row_ids, current_user.get_bot(), current_user.get_user())
    return {"message": "Records deleted!"}

@router.get("/cognition", response_model=Response)
async def list_cognition_data(
        request: Request,
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches cognition content of the bot
    """
    kwargs = request.query_params._dict.copy()
    kwargs.pop('start_idx', None)
    kwargs.pop('page_size', None)
    cognition_data, row_cnt = cognition_processor.get_cognition_data(current_user.get_bot(), start_idx, page_size, **kwargs)
    data = {
        "rows": cognition_data,
        "total": row_cnt
    }
    return Response(data=data)


@router.post("/collection", response_model=Response)
async def save_collection_data(
        collection: CollectionDataRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Saves collection data
    """
    return {
        "message": "Record saved!",
        "data": {
            "_id": DataProcessor.save_collection_data(
                collection.dict(),
                current_user.get_user(),
                current_user.get_bot(),
            )
        }
    }


@router.put("/collection/{collection_id}", response_model=Response)
async def update_collection_data(
        collection_id: str,
        collection: CollectionDataRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Updates collection data
    """
    return {
        "message": "Record updated!",
        "data": {
            "_id": DataProcessor.update_collection_data(
                collection_id,
                collection.dict(),
                current_user.get_user(),
                current_user.get_bot(),
            )
        }
    }


@router.delete("/collection/{collection_id}", response_model=Response)
async def delete_collection_data(
        collection_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Deletes collection data
    """
    DataProcessor.delete_collection_data(collection_id, current_user.get_bot(), current_user.get_user())
    return {
        "message": "Record deleted!"
    }


@router.get("/collection", response_model=Response)
async def list_collection_data(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches collection data of the bot
    """
    return {"data": list(DataProcessor.list_collection_data(current_user.get_bot()))}


@router.get("/collection/{collection_name}/metadata", response_model=Response)
async def get_collection_metadata(
        collection_name: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches collection data of the bot
    """
    return {"data": DataProcessor.get_crud_metadata(bot=current_user.get_bot(), collection_name=collection_name)}


@router.get("/collection/{collection_name}", response_model=Response)
async def get_collection_data(
        collection_name: str,
        key: List[str] = Query([]), value: List[str] = Query([]),
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches collection data based on the multiple filters provided
    """
    
    return {"data": list(DataProcessor.get_collection_data(current_user.get_bot(),
                                                           collection_name=collection_name,
                                                           key=key, value=value, page_size=page_size,
                                                           start_idx=start_idx))}


@router.get("/collection/{collection_name}/filter", response_model=Response)
async def get_collection_data_with_timestamp(
        collection_name: str,
        filters = Query(default='{}'),
        start_time: str = Query(default=None),
        end_time: str = Query(default=None),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches collection data based on the multiple filters provided
    """
    return {"data": list(DataProcessor.get_collection_data_with_timestamp(bot=current_user.get_bot(),
                                                                                   data_filter=filters,
                                                                                 collection_name=collection_name,
                                                                                   start_time=start_time,
                                                                                   end_time=end_time))}


@router.get("/collection/data/{collection_id}", response_model=Response)
async def get_collection_data_with_id(
        collection_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches collection data based on the collection_id provided
    """
    return {"data": DataProcessor.get_collection_data_with_id(current_user.get_bot(),
                                                                    collection_id=collection_id)}

@router.get("/collections/all", response_model=Response)
async def get_all_collections(
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    List all collection names for the bot.
    """
    names = DataProcessor.get_all_collections(current_user.get_bot())
    return Response(data=names)

@router.get("/collections/{collection_name}/filter/count", response_model=Response)
async def get_collection_filter_count(
    collection_name: str,
    filters: Optional[str] = Query(None),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Count of filtered records
    """
    count = DataProcessor.get_collection_filter_data_count(
        current_user.get_bot(),
        collection_name,
        filters
    )

    return Response(
        success=True,
        message="Filtered count fetched successfully",
        data={"count": count}
    )

@router.delete("/collection/delete/{collection_name}", response_model=Response)
async def delete_collection(
    collection_name: str = Path(...),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Drop an entire collection and its documents by collection name.
    """
    message, deleted_count = DataProcessor.delete_collection(
        bot=current_user.get_bot(),
        name=collection_name
    )
    return Response(message=message, data={"deleted": deleted_count})

@router.post("/content/upload", response_model=Response)
async def upload_doc_content(
        doc_content: UploadFile,
        table_name: str,
        overwrite: bool = True,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Handles the upload of document content for processing, validation, and eventual storage.
    """
    event = DocContentImporterEvent(
        bot=current_user.get_bot(),
        user=current_user.get_user(),
        table_name=table_name,
        overwrite=overwrite
    )
    is_event_data = event.validate(doc_content=doc_content, is_data_uploaded=True)
    if is_event_data:
        event.enqueue()
    return {"message": "Document content upload in progress! Check logs."}

@router.post("/upload/collection_data/{collection_name}", response_model=Response)
async def upload_file_content(
    file_content: UploadFile,
    collection_name: str = Path(..., description="Collection name"),
    overwrite: bool = False,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Handles the upload of file content for processing, validation, and eventual storage.
    """
    MongoProcessor.validate_file_type(file_content)
    DataProcessor.validate_collection_name(collection_name)
    event = UploadHandler(
        bot=current_user.get_bot(),
        user=current_user.get_user(),
        upload_type=UploadHandlerClass.crud_data,
        overwrite=overwrite,
        collection_name=collection_name
    )
    is_event_data = event.validate(file_content=file_content)
    if is_event_data:
        event.enqueue(bot=current_user.get_bot(),
                      user=current_user.get_user(),
                      upload_type=UploadHandlerClass.crud_data,
                      overwrite=overwrite,
                      collection_name=collection_name)
    return {"message": "File content upload in progress! Check logs."}

@router.get("/content/error-report/{event_id}", response_model=Response)
async def download_error_csv(
    event_id: str,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Downloads the error report file for validation errors.
    """
    try:
        file_path = processor.get_error_report_file_path(current_user.get_bot(), event_id)

        response = FileResponse(file_path, filename=os.path.basename(file_path))
        response.headers["Content-Disposition"] = f"attachment; filename={os.path.basename(file_path)}"

        return response
    except HTTPException as e:
        return Response(
            success=False,
            message=e.detail,
            data=None,
            error_code=e.status_code
        )

@router.post("/cognition/sync", response_model=Response)
async def knowledge_vault_sync(
    primary_key_col: str,
    collection_name: str,
    sync_type: str,
    data: List[dict],
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Validates and syncs data to the specified MongoDB collection and vector database.
    """
    data = [{key.lower(): value for key, value in row.items()} for row in data]

    error_summary = cognition_processor.validate_data(primary_key_col.lower(), collection_name.lower(), sync_type.lower(), data, current_user.get_bot())

    if error_summary:
        return Response(
            success=False,
            message="Validation failed",
            data=error_summary,
            error_code=400
        )

    await cognition_processor.upsert_data(primary_key_col.lower(), collection_name.lower(), sync_type.lower(), data,
                                    current_user.get_bot(), current_user.get_user())

    return Response(
        success=True,
        message="Processing completed successfully",
        data=None
    )

@router.post("/integrations/add", response_model=Response)
async def add_pos_integration_config(
    request_data: POSIntegrationRequest,
    sync_type: str,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Add data integration config
    """
    CognitionDataProcessor.load_catalog_provider_mappings()

    if request_data.provider not in CatalogSyncClass.__members__.values():
        raise AppException("Invalid Provider")

    integration_endpoint = await cognition_processor.save_pos_integration_config(
        request_data.dict(), current_user.get_bot(), current_user.get_user(), sync_type
    )

    return Response(message='POS Integration Complete', data=integration_endpoint)

@router.get("/integrations", response_model=Response)
async def list_pos_integration_configs(
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetch POS integration config for a provider and sync_type
    """
    config = cognition_processor.list_pos_integration_configs(current_user.get_bot())
    return Response(message="POS Integration config fetched", data=config)

@router.delete("/integrations", response_model=Response)
async def delete_pos_integration_config(
    provider: str,
    sync_type: Optional[str] = None,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Delete POS integration config for a provider and sync_type
    """
    try:
        result = cognition_processor.delete_pos_integration_config(current_user.get_bot(), provider, sync_type)
        return Response(message="POS Integration config deleted", data=result)
    except Exception as e:
        raise AppException(str(e))

@router.get("/pos/params", response_model=Response)
async def pos_config_params():
    """
    Retrieves pos config parameters.

    Includes required and optional fields for storing the config.
    """
    return Response(data=Utility.system_metadata['pos_integrations'])


@router.get("/{provider}/{sync_type}/endpoint", response_model=Response)
async def get_pos_endpoint(
    provider: str,
    sync_type: str,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Retrieve channel endpoint.
    """
    integration_endpoint = cognition_processor.get_pos_integration_endpoint(current_user.get_bot(), provider, sync_type)
    return Response(data=integration_endpoint, message="Endpoint fetched", success=True, error_code=0)

@router.post("/collection/bulk/{collection_name}", response_model=Response)
async def save_bulk_collection_data(
    request: BulkCollectionDataRequest,
    collection_name: str = Path(..., description="Collection name"),
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Saves collection data in bulk.
    """
    result = DataProcessor.save_bulk_collection_data(
        payloads=[collection.dict() for collection in request.payload],
        user=current_user.get_user(),
        bot=current_user.get_bot(),
        collection_name=collection_name
    )
    return {
        "message": "Bulk save completed",
        "data": result,
    }


@router.get("/fetch_media_ids", response_model=Response)
async def get_media_ids(
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    try:
        media_ids = UserMedia.get_media_ids(current_user.get_bot())
        return Response(message="List of media ids", data=media_ids)
    except Exception as e:
        raise AppException(f"Error while fetching media ids: {str(e)}")

@router.delete("/{channel}/media/{media_id}", response_model=Response)
async def delete_media_data(
        channel: ChannelTypes,
        media_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    ChatDataProcessor.delete_media_from_bsp(current_user.get_bot(), channel, media_id)
    UserMedia.delete_media(current_user.get_bot(), media_id)
    return Response(message="Deleted Successfully")

@router.get("/fetch_media_url/{filename}")
async def fetch_media_url(
        filename: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    media_url = CloudUtility.get_s3_media_url(filename, current_user.get_bot())
    return Response(message="Successfully fetched media details", data={"media_url": f"{media_url}",
                                                                        "filename": f"{filename}"})
