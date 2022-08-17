from fastapi import APIRouter, Path, Security

from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.metering_processor import MeteringProcessor
from kairon.shared.auth import Authentication
from kairon.api.models import Response
from kairon.shared.constants import ADMIN_ACCESS
from kairon.shared.models import User
from kairon.shared.data.processor import MongoProcessor

router = APIRouter()
mongo_processor = MongoProcessor()


@router.get("/{metric_type}", response_model=Response)
async def get_http_action(metric_type: MetricType = Path(default=None, description="metric type", example="test_chat, prod_chat"),
                          current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Returns metering for supplied type.
    """
    metric_count = MeteringProcessor.get_metrics(current_user.account, metric_type)
    return Response(data=metric_count)
