from fastapi import APIRouter, Path, Security

from kairon.shared.end_user_metrics.constants import MetricTypes
from kairon.shared.end_user_metrics.processor import EndUserMetricsProcessor
from kairon.shared.metering.constants import MetricType
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
        metric_type: MetricType = Path(default=None, description="metric type", example="test_chat, prod_chat"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Returns metering for supplied type.
    """
    metric_count = MeteringProcessor.get_metrics(current_user.account, metric_type)
    return Response(data=metric_count)


@router.get("/user/logs", response_model=Response)
async def get_end_user_metrics(
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    List end user logs.
    """
    return Response(
        data=EndUserMetricsProcessor.get_logs(start_idx, page_size, bot=current_user.get_bot())
    )


@router.post("/user/logs/{log_type}", response_model=Response)
async def add_end_user_metrics(
        request_data: DictData,
        log_type: MetricTypes = Path(default=None, description="metric type", example=MetricTypes.user_metrics),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    """
    Stores End User Metrics
    """
    data = request_data.dict()["data"]
    EndUserMetricsProcessor.add_log_with_geo_location(
        log_type=log_type.value, bot=current_user.get_bot(), user_id=current_user.get_user(), **data
    )
    return Response(
        message='Metrics added'
    )
