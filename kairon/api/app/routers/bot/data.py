import os

from fastapi import UploadFile, File, Security, APIRouter
from starlette.requests import Request
from starlette.responses import FileResponse

from kairon.api.models import Response, CognitiveDataRequest, CognitionSchemaRequest
from kairon.events.definitions.faq_importer import FaqDataImporterEvent
from kairon.shared.auth import Authentication
from kairon.shared.cognition.processor import CognitionDataProcessor
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
    cognition_processor.delete_cognition_schema(schema_id, current_user.get_bot(), user=current_user.get_user())
    return {
        "message": "Schema deleted!"
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
