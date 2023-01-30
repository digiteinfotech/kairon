import os

from fastapi import UploadFile, File, Security, APIRouter

from kairon.api.models import Response
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
