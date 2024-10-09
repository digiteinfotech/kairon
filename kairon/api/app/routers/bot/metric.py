from datetime import datetime

from fastapi import APIRouter, Path, Security
from starlette.requests import Request

from kairon.shared.metering.constants import MetricType, UpdateMetricType
from kairon.shared.metering.metering_processor import MeteringProcessor
from kairon.shared.auth import Authentication
from kairon.api.models import Response, DictData
from kairon.shared.constants import ADMIN_ACCESS, TESTER_ACCESS, CHAT_ACCESS
from kairon.shared.models import User
from kairon.shared.data.processor import MongoProcessor

router = APIRouter()
mongo_processor = MongoProcessor()


@router.get("/{metric_type}", response_model=Response)
async def get_metering_data(
        metric_type: MetricType = Path(description="metric type", examples=["test_chat, prod_chat"]),
        start_date: datetime = None, end_date: datetime = None,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Returns metering for supplied type.
    """
    metric_count = MeteringProcessor.get_metric_count(current_user.bot_account, metric_type, start_date, end_date)
    return Response(data=metric_count)


@router.get("/user/logs/{metric_type}", response_model=Response)
async def get_end_user_metrics(
        request: Request,
        metric_type: MetricType = Path(description="metric type", examples=["test_chat, prod_chat"]),
        start_idx: int = 0, page_size: int = 10, start_date: datetime = None, end_date: datetime = None,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    List end user logs.
    This endpoint also takes key-value pairs as query parameters and
    uses them as filter while retrieving logs.
    """
    kwargs = request.query_params._dict.copy()
    kwargs.update({
        'metric_type': metric_type.value, 'bot': current_user.get_bot(), 'start_idx': start_idx, 'page_size': page_size,
        'start_date': start_date, 'end_date': end_date
    })
    data = MeteringProcessor.get_logs(current_user.bot_account, **kwargs)
    return Response(data=data)


@router.post("/user/logs/{metric_type}", response_model=Response)
async def add_end_user_metrics(
        request_data: DictData, request: Request,
        metric_type: MetricType = Path(description="metric type", examples=[MetricType.user_metrics]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    """
    Stores End User Metrics
    """
    data = request_data.dict()["data"]
    id = MeteringProcessor.add_log_with_geo_location(
        metric_type=metric_type.value, request=request, bot=current_user.get_bot(), user=current_user.get_user(),
        account_id=current_user.bot_account, **data
    )
    return Response(message='Metrics added', data={"id": id})


@router.put("/user/logs/{metric_type}/{id}", response_model=Response)
async def update_end_user_metrics(
        id: str,
        request_data: DictData,
        metric_type: UpdateMetricType = Path(description="metric type",
                                               examples=[MetricType.conversation_feedback]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    """
    Update End User Metrics
    """
    data = request_data.data
    MeteringProcessor.update_metrics(id=id,
                                     metric_type=metric_type.value, bot=current_user.get_bot(),
                                     user=current_user.get_user(),
                                     account_id=current_user.bot_account, **data
                                     )
    return Response(message='Metrics updated')
