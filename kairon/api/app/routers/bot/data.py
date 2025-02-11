import os
from typing import List

from fastapi import UploadFile, File, Security, APIRouter, Query, HTTPException
from mongoengine import DoesNotExist
from starlette.requests import Request
from starlette.responses import FileResponse

from kairon.api.models import Response, CognitiveDataRequest, CognitionSchemaRequest, CollectionDataRequest
from kairon.events.definitions.content_importer import DocContentImporterEvent
from kairon.events.definitions.faq_importer import FaqDataImporterEvent
from kairon.exceptions import AppException
from kairon.shared.auth import Authentication
from kairon.shared.cognition.data_objects import CognitionSchema, CognitionData
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.constants import ActorType
from kairon.shared.constants import DESIGNER_ACCESS
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


@router.delete("/cognition", response_model=Response)
async def delete_multiple_cognition_data(
        row_ids: list[str] = Query(...),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Deletes multiple cognition content entries of the bot in bulk
    """
    try:
        query = {"id__in": row_ids}
        Utility.hard_delete_document([CognitionData], bot=current_user.get_bot(), **query, user=current_user.get_user())
    except DoesNotExist:
        raise AppException("Some or all records do not exist!")

    return {
        "message": "Records deleted!"
    }


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
            "_id": cognition_processor.save_collection_data(
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
            "_id": cognition_processor.update_collection_data(
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
    cognition_processor.delete_collection_data(collection_id, current_user.get_bot(), current_user.get_user())
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
    return {"data": list(cognition_processor.list_collection_data(current_user.get_bot()))}


@router.get("/collection/{collection_name}", response_model=Response)
async def get_collection_data(
        collection_name: str,
        key: List[str] = Query([]), value: List[str] = Query([]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches collection data based on the multiple filters provided
    """
    return {"data": list(cognition_processor.get_collection_data(current_user.get_bot(),
                                                                 collection_name=collection_name,
                                                                 key=key, value=value))}


@router.get("/collection/data/{collection_id}", response_model=Response)
async def get_collection_data_with_id(
        collection_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches collection data based on the collection_id provided
    """
    return {"data": cognition_processor.get_collection_data_with_id(current_user.get_bot(),
                                                                    collection_id=collection_id)}


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
    event_type: str,
    data: List[dict],
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Validates and syncs data to the specified MongoDB collection and vector database.
    """
    data = [{key.lower(): value for key, value in row.items()} for row in data]

    error_summary = cognition_processor.validate_data(primary_key_col.lower(), collection_name.lower(), event_type.lower(), data, current_user.get_bot())

    if error_summary:
        return Response(
            success=False,
            message="Validation failed",
            data=error_summary,
            error_code=400
        )

    await cognition_processor.upsert_data(primary_key_col.lower(), collection_name.lower(), event_type.lower(), data,
                                    current_user.get_bot(), current_user.get_user())

    return Response(
        success=True,
        message="Processing completed successfully",
        data=None
    )