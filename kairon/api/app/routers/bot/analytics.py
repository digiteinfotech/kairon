from fastapi import APIRouter, Security


from kairon.api.models import Response
from kairon.events.definitions.analytic_pipeline_handler import AnalyticsPipelineEvent
from kairon.shared.analytics.analytics_pipeline_processor import AnalyticsPipelineProcessor

from kairon.shared.auth import Authentication
from kairon.shared.constants import TESTER_ACCESS, EventRequestType
from kairon.shared.data.data_models import AnalyticsPipelineEventRequest
from kairon.shared.models import User


router = APIRouter()


@router.post("/events", response_model=Response)
async def create_pipeline_event(
    request: AnalyticsPipelineEventRequest,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    event_type = EventRequestType.trigger_async.value

    event = AnalyticsPipelineEvent(current_user.get_bot(), current_user.get_user())
    event.callback_name = request.callback_name
    event.validate()

    if request.scheduler_config:
        if request.scheduler_config.expression_type == "cron":
            event_type = EventRequestType.add_schedule.value
        elif request.scheduler_config.expression_type == "epoch":
            event_type = EventRequestType.add_one_time_schedule.value
    event_id = event.enqueue(event_type, config=request.dict())
    return Response(message="Event scheduled!", data={"event_id": event_id})


@router.get("/events", response_model=Response)
async def list_pipeline_events(
    current_user: User = Security(Authentication.get_current_user_and_bot)
):
    data = AnalyticsPipelineProcessor.get_all_analytics_pipelines(current_user.get_bot())
    return Response(message="Events fetched", data=data)


@router.get("/events/{event_id}", response_model=Response)
async def get_pipeline_event(
    event_id: str,
    current_user: User = Security(Authentication.get_current_user_and_bot)
):
    config = AnalyticsPipelineProcessor.retrieve_config(event_id, current_user.get_bot())
    return Response(message="Event retrieved", data=config)


@router.delete("/events/{event_id}", response_model=Response)
async def delete_pipeline_event(
    event_id: str,
    current_user: User = Security(Authentication.get_current_user_and_bot)
):
    AnalyticsPipelineEvent(current_user.get_bot(),current_user.get_user()).delete_schedule(event_id)

    return Response(message="Event deleted")


@router.put("/events/{event_id}", response_model=Response)
async def update_pipeline_event(
    event_id: str,
    request: AnalyticsPipelineEventRequest,
    current_user: User = Security(Authentication.get_current_user_and_bot)
):
    event = AnalyticsPipelineEvent(
        current_user.get_bot(),
        current_user.get_user()
    )
    event.callback_name = request.callback_name
    event.validate()
    event.enqueue(EventRequestType.update_schedule.value, event_id=event_id, config=request.dict())
    return Response(message="Event updated", data={"event_id": event_id})


