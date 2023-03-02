import os

from fastapi import UploadFile, File, Security, APIRouter

from kairon.api.models import Response, TextData
from kairon.events.definitions.faq_importer import FaqDataImporterEvent
from kairon.shared.auth import Authentication
from kairon.shared.constants import DESIGNER_ACCESS
from kairon.shared.models import User
from starlette.responses import FileResponse

from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility

router = APIRouter()
processor = MongoProcessor()


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


@router.post("/text/faq", response_model=Response)
def save_bot_text(
        text: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Saves text content into the bot
    """
    return {
        "message": "Text saved!",
        "data": {
            "_id": processor.save_content(
                    text.data,
                    current_user.get_user(),
                    current_user.get_bot(),
            )
        }
    }


@router.put("/text/faq/{text_id}", response_model=Response)
def update_bot_text(
        text_id: str,
        text: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Updates text content into the bot
    """
    return {
        "message": "Text updated!",
        "data": {
            "_id": processor.update_content(
                text_id,
                text.data,
                current_user.get_user(),
                current_user.get_bot(),
            )
        }
    }


@router.delete("/text/faq/{text_id}", response_model=Response)
def delete_bot_text(
        text_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Deletes text content of the bot
    """
    processor.delete_content(text_id, current_user.get_user(), current_user.get_bot())
    return {
        "message": "Text deleted!"
    }


@router.get("/text/faq", response_model=Response)
def get_text(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Fetches text content of the bot
    """
    return {"data": list(processor.get_content(current_user.get_bot()))}
