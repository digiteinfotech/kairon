import os
from datetime import date, datetime
from typing import List, Optional, Dict, Text

from fastapi import APIRouter, BackgroundTasks, Path, Security, Request
from fastapi import UploadFile
from fastapi.responses import FileResponse
from pydantic import constr

from kairon.api.models import (
    TextData,
    ListData,
    Response,
    Endpoint,
    RasaConfig,
    StoryRequest,
    SynonymRequest, RegexRequest,
    StoryType, ComponentConfig, SlotRequest, DictData, LookupTablesRequest, Forms,
    TextDataLowerCase, SlotMappingRequest, EventConfig, MultiFlowStoryRequest, BotSettingsRequest
)
from kairon.events.definitions.data_importer import TrainingDataImporterEvent
from kairon.events.definitions.mail_channel import MailReadEvent
from kairon.events.definitions.model_testing import ModelTestingEvent
from kairon.events.definitions.model_training import ModelTrainingEvent
from kairon.exceptions import AppException
from kairon.shared.account.activity_log import UserActivityLogger
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.auth import Authentication
from kairon.shared.channels.mail.processor import MailProcessor
from kairon.shared.constants import TESTER_ACCESS, DESIGNER_ACCESS, CHAT_ACCESS, UserActivityType, ADMIN_ACCESS, \
    EventClass, AGENT_ACCESS
from kairon.shared.content_importer.content_processor import ContentImporterLogProcessor
from kairon.shared.content_importer.data_objects import ContentValidationLogs
from kairon.shared.data.assets_processor import AssetsProcessor
from kairon.shared.data.audit.processor import AuditDataProcessor
from kairon.shared.data.constant import ENDPOINT_TYPE, ModelTestType, \
    AuditlogActions
from kairon.shared.data.data_models import FlowTagChangeRequest
from kairon.shared.data.data_objects import TrainingExamples, ModelTraining, Rules
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.events.processor import ExecutorProcessor
from kairon.shared.importer.data_objects import ValidationLogs
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.live_agent.live_agent import LiveAgentHandler
from kairon.shared.llm.processor import LLMProcessor
from kairon.shared.models import User, TemplateType
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.shared.utils import Utility

router = APIRouter()
v2 = APIRouter()
mongo_processor = MongoProcessor()


@router.get("/intents", response_model=Response)
async def get_intents(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches list of existing intents for particular bot
    """
    return Response(data=mongo_processor.get_intents(current_user.get_bot())).dict()


@router.get("/intents/all", response_model=Response)
async def get_intents_with_training_examples(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches list of existing intents and associated training examples for particular bot
    """
    return Response(data=mongo_processor.get_intents_and_training_examples(current_user.get_bot())).dict()


@router.post("/intents", response_model=Response)
async def add_intents(
        request_data: TextDataLowerCase,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Adds a new intent to the bot
    """
    intent_id = mongo_processor.add_intent(
        text=request_data.data,
        bot=current_user.get_bot(),
        user=current_user.get_user(),
        is_integration=current_user.get_integration_status()
    )
    return {"message": "Intent added successfully!", "data": {"_id": intent_id}}


@router.delete("/intents/{intent}", response_model=Response)
async def delete_intent(
        intent: str = Path(description="intent name", examples=["greet"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    deletes an intent including training examples and stories
    """
    mongo_processor.delete_intent(
        intent, current_user.get_bot(), current_user.get_user(), current_user.get_integration_status(),
    )
    return {"message": "Intent deleted!"}


@router.post("/intents/search", response_model=Response)
async def search_training_examples(
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Searches existing training examples
    """
    search_items = list(
        mongo_processor.search_training_examples(
            request_data.data, current_user.get_bot()
        )
    )
    return {"data": {"searched_items": search_items}}


@router.get("/training_examples/{intent}", response_model=Response)
async def get_training_examples(
        intent: str, current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches all training examples against intent
    """
    return {
        "data": list(
            mongo_processor.get_training_examples(intent, current_user.get_bot())
        )
    }


@router.get("/training_examples", response_model=Response)
async def get_all_training_examples_for_bot(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches all training examples against a bot.
    """
    return {
        "data": mongo_processor.get_training_examples_as_dict(current_user.get_bot())
    }


@router.get("/training_examples/exists/{text}", response_model=Response)
async def training_example_exists(
        text: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Checks if training example exists
    """
    return {
        "data": mongo_processor.check_training_example_exists(text, current_user.get_bot())
    }


@router.post("/training_examples/{intent}", response_model=Response)
async def add_training_examples(
        intent: constr(to_lower=True, strip_whitespace=True),
        request_data: ListData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Adds training example in particular intent
    """
    results = list(
        mongo_processor.add_training_example(
            request_data.data, intent, current_user.get_bot(), current_user.get_user(),
            current_user.get_integration_status()
        )
    )
    return {"data": results}


@router.post("/training_examples/move/{intent}", response_model=Response)
async def move_training_examples(
        intent: constr(to_lower=True, strip_whitespace=True),
        request_data: ListData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Moves training example to particular intent
    """
    results = list(
        mongo_processor.add_or_move_training_example(
            request_data.data, intent, current_user.get_bot(), current_user.get_user()
        )
    )
    return {"data": results}


@router.put("/training_examples/{intent}/{id}", response_model=Response)
async def edit_training_examples(
        intent: str,
        id: str,
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Updates existing training example
    """
    mongo_processor.edit_training_example(
        id, request_data.data, intent, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Training Example updated!"}


@router.delete("/training_examples/{id}", response_model=Response)
async def remove_training_examples(
        id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes existing training example
    """
    mongo_processor.remove_document(
        TrainingExamples,
        id,
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {"message": "Training Example removed!"}


@router.get("/response/all", response_model=Response)
async def get_all_responses(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches list of all utterances added.
    """
    return {
        "data": list(mongo_processor.get_all_responses(current_user.get_bot()))
    }


@router.get("/response/{utterance}", response_model=Response)
async def get_responses(
        utterance: str, current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches list of utterances against utterance name
    """
    return {
        "data": list(mongo_processor.get_response(utterance, current_user.get_bot()))
    }


@router.post("/response/{utterance}", response_model=Response)
async def add_responses(
        request_data: TextData,
        utterance: constr(to_lower=True, strip_whitespace=True),
        form_attached: Optional[str] = None,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Adds utterance value in particular utterance
    """
    utterance_id = mongo_processor.add_text_response(
        request_data.data, utterance, current_user.get_bot(), current_user.get_user(), form_attached
    )
    return {"message": "Response added!", "data": {"_id": utterance_id}}


@router.post("/response/json/{utterance}", response_model=Response)
async def add_custom_responses(
        request_data: DictData,
        utterance: constr(to_lower=True, strip_whitespace=True),
        form_attached: Optional[str] = None,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Adds utterance value in particular utterance
    """
    utterance_id = mongo_processor.add_custom_response(
        request_data.data, utterance, current_user.get_bot(), current_user.get_user(), form_attached
    )
    return {"message": "Response added!", "data": {"_id": utterance_id}}


@router.put("/response/{utterance}/{utterance_id}", response_model=Response)
async def edit_responses(
        utterance: str,
        utterance_id: str,
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Updates existing utterance value
    """
    mongo_processor.edit_text_response(
        utterance_id,
        request_data.data,
        utterance,
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {
        "message": "Utterance updated!",
    }


@router.put("/response/json/{utterance}/{utterance_id}", response_model=Response)
async def edit_custom_responses(
        utterance: str,
        utterance_id: str,
        request_data: DictData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Updates existing utterance value
    """
    mongo_processor.edit_custom_response(
        utterance_id,
        request_data.data,
        utterance,
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {
        "message": "Utterance updated!",
    }


@router.delete("/response/{response_id}", response_model=Response)
async def remove_response(
        response_id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes existing utterance example.
    """
    mongo_processor.delete_response(
        response_id, current_user.get_bot(), user=current_user.get_user()
    )
    return {
        "message": "Response removed!",
    }


@router.delete("/responses/{utterance}", response_model=Response)
async def remove_responses(
        utterance: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes existing utterance completely along with its examples.
    """
    mongo_processor.delete_utterance(
        utterance, current_user.get_bot(), user=current_user.get_user()
    )
    return {
        "message": "Utterance removed!",
    }


@router.post("/stories", response_model=Response)
async def add_story(
        story: StoryRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Adds a story (conversational flow) in the particular bot
    """
    return {
        "message": "Flow added successfully",
        "data": {
            "_id": mongo_processor.add_complex_story(
                story.dict(),
                current_user.get_bot(),
                current_user.get_user(),
            )
        },
    }


@router.put("/stories/{story_id}", response_model=Response)
async def update_story(
        story_id: str,
        story: StoryRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Updates a story (conversational flow) in the particular bot
    """
    return {
        "message": "Flow updated successfully",
        "data": {
            "_id": mongo_processor.update_complex_story(
                story_id,
                story.dict(),
                current_user.get_bot(),
                current_user.get_user(),
            )
        },
    }


@router.get("/stories", response_model=Response)
async def get_stories(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches existing list of stories (conversation flows)
    """
    return {"data": list(mongo_processor.get_all_stories(current_user.get_bot()))}


@v2.post("/stories", response_model=Response)
async def add_story_multiflow(
        story: MultiFlowStoryRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Adds a multiflow story (conversational flow) in the particular bot
    """
    return {
        "message": "Story flow added successfully",
        "data": {
            "_id": mongo_processor.add_multiflow_story(
                story.dict(),
                current_user.get_bot(),
                current_user.get_user(),
            )
        },
    }


@v2.put("/stories/{story_id}", response_model=Response)
async def update_story_multiflow(
        story_id: str,
        story: MultiFlowStoryRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Updates a multiflow story (conversational flow) in the particular bot
    """
    return {
        "message": "Story flow updated successfully",
        "data": {
            "_id": mongo_processor.update_multiflow_story(
                story_id,
                story.dict(),
                current_user.get_bot(),
            )
        },
    }


@router.delete("/stories/{story_id}/{type}", response_model=Response)
async def delete_stories(story_id: str,
                         type: str = StoryType,
                         current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
                         ):
    """
    Updates a story (conversational flow) in the particular bot
    """
    mongo_processor.delete_complex_story(
        story_id,
        type,
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {
        "message": "Flow deleted successfully"
    }


@router.get("/utterance_from_intent/{intent}", response_model=Response)
async def get_story_from_intent(
        intent: str, current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the utterance or response that is mapped to a particular intent
    """
    response = mongo_processor.get_utterance_from_intent(intent, current_user.get_bot())
    return_data = {"name": response[0], "type": response[1]}
    return {"data": return_data}


@router.post("/chat", response_model=Response)
async def chat(
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    """
    Fetches a bot response for a given text/query.
    It is basically used to test the chat functionality of the agent
    """
    return await Utility.chat(request_data.data,
                              bot=current_user.get_bot(),
                              user=current_user.get_user(),
                              email=current_user.email)


@router.post("/chat/{user}", response_model=Response)
async def augment_chat(
        request_data: TextData,
        user: str = Path(description="user for which the chats needs to be log"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=CHAT_ACCESS)
):
    """
    Fetches a bot response for a given text/query for user on path parameter.
    It is basically used to test the chat functionality of the agent
    """
    return await Utility.chat(request_data.data,
                              bot=current_user.get_bot(),
                              user=user,
                              email=current_user.email)


@router.post("/train", response_model=Response)
async def train(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Trains the chatbot
    """
    event = ModelTrainingEvent(current_user.get_bot(), current_user.get_user())
    event.validate()
    event.enqueue()
    return {"message": "Model training started."}


@router.post("/abort/{event_type}", response_model=Response)
async def abort_event(
        event_type: EventClass = Path(description="Event type", examples=[e.value for e in EventClass]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Aborts the event
    """
    mongo_processor.abort_current_event(current_user.get_bot(), current_user.get_user(), event_type)

    return {"message": f"{event_type} aborted."}


@router.get("/model/reload", response_model=Response)
async def reload_model(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Reloads model with configuration in cache
    """
    response = Utility.reload_model(
        bot=current_user.get_bot(),
        email=current_user.email)
    return response


@router.get("/train/history", response_model=Response)
async def get_model_training_history(
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Fetches model training history, when and who trained the bot
    """
    training_history = list(ModelProcessor.get_training_history(current_user.get_bot(), start_idx, page_size))
    row_cnt = mongo_processor.get_row_count(ModelTraining, current_user.get_bot())
    data = {
        "logs": training_history,
        "total": row_cnt
    }
    return {"data": {"training_history": data}}


@router.post("/deploy", response_model=Response)
async def deploy(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)):
    """
    Deploys the latest bot model to the particular http endpoint
    """
    response = mongo_processor.deploy_model(
        bot=current_user.get_bot(), user=current_user.get_user()
    )
    return {"message": response}


@router.get("/deploy/history", response_model=Response)
async def deployment_history(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches model deployment history, when and who deployed the model
    """
    return {
        "data": {
            "deployment_history": list(
                mongo_processor.get_model_deployment_history(bot=current_user.get_bot())
            )
        }
    }


@router.post("/upload", response_model=Response)
def upload_files(
        training_files: List[UploadFile],
        import_data: bool = True,
        overwrite: bool = True,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Uploads training data nlu.yml, domain.yml, stories.yml, config.yml, rules.yml and actions.yml files.
    """
    event = TrainingDataImporterEvent(
        current_user.get_bot(), current_user.get_user(), import_data=import_data, overwrite=overwrite
    )
    is_event_data = event.validate(training_files=training_files, is_data_uploaded=True)
    if is_event_data:
        event.enqueue()
    return {"message": "Upload in progress! Check logs."}


@router.get("/download/data")
async def download_data(
        background_tasks: BackgroundTasks,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
        download_multiflow_stories: bool = False
):
    """
    Downloads training data nlu.yml, domain.yml, stories.yml, config.yml, chat_client_config.yml files
    """
    file = mongo_processor.download_files(current_user.get_bot(), current_user.get_user(), download_multiflow_stories)
    response = FileResponse(
        file, filename=os.path.basename(file), background=background_tasks
    )
    AuditDataProcessor.log("Training Data", current_user.account, current_user.get_bot(), current_user.get_user(),
                           data={"download_multiflow_stories": download_multiflow_stories},
                           action=AuditlogActions.DOWNLOAD.value)
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=" + os.path.basename(file)
    return response


@router.get("/download/model")
async def download_model(
        background_tasks: BackgroundTasks,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Downloads latest trained model file
    """
    try:
        model_path = Utility.get_latest_model(current_user.get_bot())
        response = FileResponse(
            model_path,
            filename=os.path.basename(model_path),
            background=background_tasks,
            media_type='application/octet-stream'
        )
        AuditDataProcessor.log("Model", current_user.account, current_user.get_bot(), current_user.get_user(),
                               action=AuditlogActions.DOWNLOAD.value)
        response.headers[
            "Content-Disposition"
        ] = "attachment; filename=" + os.path.basename(model_path)
        return response
    except Exception as e:
        raise AppException(str(e))


@router.post("/test", response_model=Response)
async def test_model(
        augment_data: bool = True,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Run tests on a trained model.
    """
    event = ModelTestingEvent(current_user.get_bot(), current_user.get_user(), augment_data=augment_data)
    event.validate()
    event.enqueue()
    return {"message": "Testing in progress! Check logs."}


@router.get("/logs/test", response_model=Response)
async def model_testing_logs(
        log_type: ModelTestType = None, reference_id: str = None,
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    List model testing logs.
    """
    logs, row_cnt = ModelTestingLogProcessor.get_logs(current_user.get_bot(), log_type, reference_id, start_idx, page_size)
    data = {
        "logs": logs,
        "total": row_cnt
    }
    return Response(data=data)


@router.get("/endpoint", response_model=Response)
async def get_endpoint(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)):
    """
    Fetches the http and mongo endpoint for the bot
    """
    endpoint = mongo_processor.get_endpoints(
        current_user.get_bot(), mask_characters=True, raise_exception=False
    )
    return {"data": {"endpoint": endpoint}}


@router.put("/endpoint", response_model=Response)
async def set_endpoint(
        background_tasks: BackgroundTasks,
        endpoint: Endpoint,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS),
):
    """
    Saves or Updates the bot endpoint configuration
    """
    mongo_processor.add_endpoints(
        endpoint.dict(), current_user.get_bot(), current_user.get_user()
    )

    if endpoint.action_endpoint:
        background_tasks.add_task(Utility.reload_model, current_user.get_bot(), current_user.email)
    return {"message": "Endpoint saved successfully!"}


@router.delete("/endpoint/{endpoint_type}", response_model=Response)
async def delete_endpoint(
        endpoint_type: ENDPOINT_TYPE = Path(description="One of bot_endpoint, action_endpoint, "
                                                                      "history_endpoint", examples=["bot_endpoint"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """
    Deletes the bot endpoint configuration
    """
    mongo_processor.delete_endpoint(
        current_user.get_bot(), endpoint_type
    )

    return {"message": "Endpoint removed"}


@router.get("/config", response_model=Response)
async def get_config(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches bot pipeline and polcies configurations
    """
    config = mongo_processor.load_config(current_user.get_bot())
    return {"data": {"config": config}}


@router.put("/config", response_model=Response)
async def set_config(
        config: RasaConfig,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Saves or Updates the bot pipeline and policies configurations
    """
    mongo_processor.save_config(
        config.dict(), current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Config saved!"}


@router.put("/config/properties", response_model=Response)
async def set_epoch_and_fallback_properties(config: ComponentConfig,
                                            current_user: User = Security(Authentication.get_current_user_and_bot,
                                                                          scopes=DESIGNER_ACCESS)):
    """
    Set properties (epoch and fallback) in the bot pipeline and policies configurations
    """
    mongo_processor.save_component_properties(config.dict(), current_user.get_bot(), current_user.get_user())
    return {"message": "Config saved"}


@router.get("/config/properties", response_model=Response)
async def list_epoch_and_fallback_properties(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    List properties (epoch and fallback) in the bot pipeline and policies configurations
    """
    config = mongo_processor.list_epoch_and_fallback_config(current_user.get_bot())
    return {"data": config}


@router.post("/templates/use-case", response_model=Response)
async def set_templates(
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Applies the use-case template
    """
    await mongo_processor.apply_template(
        request_data.data, bot=current_user.get_bot(), user=current_user.get_user()
    )
    return {"message": "Data applied!"}


@router.get("/templates/config", response_model=Response)
async def get_config_template(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetches config templates
    """
    return {"data": {"config-templates": mongo_processor.get_config_templates()}}


@router.post("/templates/config", response_model=Response)
async def set_config_template(
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Applies the config template
    """
    mongo_processor.apply_config(
        request_data.data, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Config applied!"}


@router.get("/actions", response_model=Response)
async def list_actions(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Returns list of actions for bot.
    """
    actions = mongo_processor.list_actions(bot=current_user.get_bot())
    return Response(data=actions)


@router.get("/actions/logs", response_model=Response)
async def get_action_server_logs(start_idx: int = 0, page_size: int = 10,
                                 current_user: User = Security(Authentication.get_current_user_and_bot,
                                                               scopes=TESTER_ACCESS)):
    """
    Retrieves action server logs for the bot.
    """
    logs = list(mongo_processor.get_action_server_logs(current_user.get_bot(), start_idx, page_size))
    row_cnt = mongo_processor.get_row_count(ActionServerLogs, current_user.get_bot())
    data = {
        "logs": logs,
        "total": row_cnt
    }
    return Response(data=data)


@router.get("/slots", response_model=Response)
async def get_slots(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Fetches status for latest data generation request
    """
    slots = list(mongo_processor.get_existing_slots(current_user.get_bot()))
    return {"data": slots}


@router.post("/slots", response_model=Response)
async def add_slots(
        request_data: SlotRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    adds a new slot
    :param request_data:
    :param current_user:
    :return: Success message with slot id
    """
    slot_id = mongo_processor.add_slot(slot_value=request_data.dict(), bot=current_user.get_bot(),
                                       user=current_user.get_user(), raise_exception_if_exists=True)
    return {"message": "Slot added successfully!", "data": {"_id": slot_id}}


@router.delete("/slots/{slot}", response_model=Response)
async def delete_slots(
        slot: str = Path(description="slot name", examples=["bot"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    deletes an existing slot
    :param slot:
    :param current_user:
    :return: Success message
    """
    mongo_processor.delete_slot(slot_name=slot, bot=current_user.get_bot(), user=current_user.get_user())

    return {"message": "Slot deleted!"}


@router.put("/slots", response_model=Response)
async def edit_slots(
        request_data: SlotRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Updates an existing slot
    :param request_data:
    :param current_user:
    :return: Success message
    """
    try:
        slot_value = request_data.dict()
        mongo_processor.add_slot(slot_value=slot_value, bot=current_user.get_bot(), user=current_user.get_user(),
                                 raise_exception_if_exists=False)
    except Exception as e:
        raise AppException(e)

    return {"message": "Slot updated!"}


@router.get("/importer/logs", response_model=Response)
async def get_data_importer_logs(
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Get data importer event logs.
    """
    logs = list(DataImporterLogProcessor.get_logs(current_user.get_bot(), start_idx, page_size))
    row_cnt = mongo_processor.get_row_count(ValidationLogs, current_user.get_bot())
    data = {
        "logs": logs,
        "total": row_cnt
    }
    return Response(data=data)


@router.get("/content/logs", response_model=Response)
async def get_content_importer_logs(
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Get data importer event logs.
    """
    logs = list(ContentImporterLogProcessor.get_logs(current_user.get_bot(), start_idx, page_size))
    row_cnt = mongo_processor.get_row_count(ContentValidationLogs, current_user.get_bot())
    data = {
        "logs": logs,
        "total": row_cnt
    }
    return Response(data=data)


@router.post("/validate", response_model=Response)
async def validate_training_data(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Validates bot training data.
    """
    event = TrainingDataImporterEvent(current_user.get_bot(), current_user.get_user())
    event.validate()
    event.enqueue()
    return {"message": "Event triggered! Check logs."}


@router.get("/entity/synonyms", response_model=Response)
async def get_all_synonyms(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Fetches the stored synonyms of the bot
    """
    synonyms = list(mongo_processor.fetch_synonyms(current_user.get_bot()))
    return {"data": synonyms}


@router.get("/entity/synonym/{name:path}/values", response_model=Response)
async def get_synonym_values(
        name: constr(to_lower=True, strip_whitespace=True),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches list of values against synonym name
    """
    return {
        "data": list(mongo_processor.get_synonym_values(name, current_user.get_bot()))
    }


@router.post("/entity/synonym", response_model=Response)
async def add_synonym(
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
       adds a new synonym values
       :param name:
       :param request_data:
       :param current_user:
       :return: Success message and sysnonym value id
   """
    id = mongo_processor.add_synonym(synonym_name=request_data.data,
                                     bot=current_user.get_bot(),
                                     user=current_user.get_user())
    return {"data": {"_id": id}, "message": "Synonym added!"}


@router.post("/entity/synonym/{name:path}/value", response_model=Response)
async def add_synonym_value(
        name: str,
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
       adds a new synonym values
       :param name:
       :param request_data:
       :param current_user:
       :return: Success message and sysnonym value id
   """
    id = mongo_processor.add_synonym_value(value=request_data.data,
                                           synonym_name=name,
                                           bot=current_user.get_bot(),
                                           user=current_user.get_user())
    return {"data": {"_id": id}, "message": "Synonym value added!"}


@router.post("/entity/synonym/{name:path}/values", response_model=Response)
async def add_synonym_values(
        name: str,
        request_data: SynonymRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    adds values to synonym
    :param name:
    :param request_data:
    :param current_user:
    :return: Success message
    """
    data = request_data.dict()
    data['name'] = name
    added_synonyms = mongo_processor.add_synonym_values(synonyms_dict=data, bot=current_user.get_bot(),
                                                        user=current_user.get_user())

    return {"data": added_synonyms, "message": "Synonym values added!"}


@router.put("/entity/synonym/{name:path}/value/{id}", response_model=Response)
async def edit_synonym_value(
        name: constr(to_lower=True, strip_whitespace=True),
        id: str,
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Updates existing synonym value
    """
    mongo_processor.edit_synonym(
        id,
        request_data.data,
        name,
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {
        "message": "Synonym value updated!"
    }


@router.delete("/entity/synonym/{id}", response_model=Response)
async def delete_synonym_value(
        id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes existing synonym with value.
    """
    mongo_processor.delete_synonym(
        id=id, bot=current_user.get_bot(), user=current_user.get_user()
    )
    return {
        "message": "Synonym removed!"
    }


@router.delete("/entity/synonym/{name:path}/value/{id}", response_model=Response)
async def delete_synonym_value(
        name: constr(to_lower=True, strip_whitespace=True),
        id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes existing synonym value.
    """
    mongo_processor.delete_synonym_value(
        synonym_name=name, value_id=id, bot=current_user.get_bot(), user=current_user.get_user()
    )
    return {
        "message": "Synonym value removed!"
    }


@router.post("/utterance", response_model=Response)
async def add_utterance(request: TextDataLowerCase,
                        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)):
    mongo_processor.add_utterance_name(
        request.data, current_user.get_bot(), current_user.get_user(), raise_error_if_exists=True
    )
    return {'message': 'Utterance added!'}


@router.get("/utterance", response_model=Response)
async def get_utterance(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    return {'data': {"utterances": list(mongo_processor.get_utterances(current_user.get_bot()))}}


@router.get("/data/count", response_model=Response)
async def get_training_data_count(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    count = mongo_processor.get_training_data_count(current_user.get_bot())
    return Response(data=count)


@router.get("/chat/client/config/url", response_model=Response)
async def get_chat_client_config_url(
        request: Request,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)):
    url = mongo_processor.get_chat_client_config_url(current_user.get_bot(), current_user.email,
                                                     request=request, account=current_user.account,
                                                     bot_account=current_user.bot_account)
    return Response(data=url)


@router.get("/chat/client/config/{token}", response_model=Response)
async def get_client_config_using_uid(
        request: Request, bot: Text = Path(description="Bot id"),
        token: Text = Path(description="Token generated from api server"),
        token_claims: Dict = Security(Authentication.validate_bot_specific_token, scopes=TESTER_ACCESS)
):
    config = mongo_processor.get_client_config_using_uid(bot, token_claims)
    config = Utility.validate_domain(request, config)
    return Response(data=config['config'])


@router.get("/chat/client/config", response_model=Response)
async def get_client_config(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    config = mongo_processor.get_chat_client_config(current_user.get_bot(), current_user.email)
    config = config.to_mongo().to_dict()
    return Response(data=config['config'])


@router.post("/chat/client/config", response_model=Response)
async def set_client_config(request: DictData, current_user: User = Security(Authentication.get_current_user_and_bot,
                                                                             scopes=DESIGNER_ACCESS)):
    mongo_processor.save_chat_client_config(request.data, current_user.get_bot(), current_user.get_user())
    return {"message": "Config saved"}


@router.get("/regex", response_model=Response)
async def get_all_regex_patterns(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the stored regex patterns of the bot
    """
    regex = list(mongo_processor.fetch_regex_features(bot=current_user.get_bot()))
    return {"data": regex}


@router.post("/regex", response_model=Response)
async def add_regex(
        request_data: RegexRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    adds a new regex and its pattern
    :param request_data:
    :param current_user:
    :return: Success message
    """

    regex_id = mongo_processor.add_regex(regex_dict=request_data.dict(), bot=current_user.get_bot(),
                                         user=current_user.get_user())

    return {"message": "Regex pattern added successfully!", "data": {"_id": regex_id}}


@router.put("/regex", response_model=Response)
async def edit_regex(
        request_data: RegexRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    edits a regex pattern
    :param request_data:
    :param current_user:
    :return: Success message
    """

    mongo_processor.edit_regex(regex_dict=request_data.dict(), bot=current_user.get_bot(), user=current_user.get_user())

    return {"message": "Regex pattern modified successfully!"}


@router.delete("/regex/{name}", response_model=Response)
async def delete_regex(
        name: str = Path(description="regex name", examples=["bot"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    deletes an existing regex pattern
    :param name: regex pattern name
    :param current_user:
    :return: Success message
    """
    mongo_processor.delete_regex(regex_name=name, bot=current_user.get_bot(), user=current_user.get_user())

    return {"message": "Regex pattern deleted!"}


@router.get("/lookups", response_model=Response)
async def get_all_lookup_tables(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    """
    Fetches the stored lookup tables of the bot
    """
    lookup = list(mongo_processor.get_lookups(bot=current_user.get_bot()))
    return {"data": lookup}


@router.get("/lookup/{name:path}/values", response_model=Response)
async def get_lookup_values(
        name: str, current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches list of values against lookup table name
    """
    return {
        "data": list(mongo_processor.get_lookup_values(name, current_user.get_bot()))
    }


@router.post("/lookup", response_model=Response)
async def add_lookup(
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    adds a new lookup
    :param name:
    :param request_data:
    :param current_user:
    :return: Success message
    """
    id = mongo_processor.add_lookup(lookup_name=request_data.data, bot=current_user.get_bot(),
                               user=current_user.get_user())

    return {"message": "Lookup added!", "data": {"_id": id}}


@router.post("/lookup/{name:path}/values", response_model=Response)
async def add_lookup_values(
        name: str,
        request_data: LookupTablesRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    adds a new lookup table and its values
    :param name:
    :param request_data:
    :param current_user:
    :return: Success message
    """
    data = request_data.dict()
    data['name'] = name
    values = mongo_processor.add_lookup_values(lookup_dict=data, bot=current_user.get_bot(),
                                      user=current_user.get_user())

    return {"message": "Lookup values added!", "data": values}


@router.post("/lookup/{name:path}/value", response_model=Response)
async def add_lookup_value(
        name: str,
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    adds a new lookup table and its values
    :param name:
    :param request_data:
    :param current_user:
    :return: Success message
    """
    id = mongo_processor.add_lookup_value(lookup_name=name,
                                     lookup_value=request_data.data,
                                     bot=current_user.get_bot(),
                                     user=current_user.get_user())

    return {"message": "Lookup value added!", "data": {"_id": id}}


@router.put("/lookup/{name:path}/value/{id}", response_model=Response)
async def edit_lookup_value(
        name: str,
        id: str,
        request_data: TextData,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Updates existing lookup table value
    """
    mongo_processor.edit_lookup_value(
        id,
        request_data.data,
        name,
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {
        "message": "Lookup value updated!"
    }


@router.delete("/lookup/{name:path}/value/{id}", response_model=Response)
async def delete_lookup_value(
        name: str,
        id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes existing lookup value.
    """
    mongo_processor.delete_lookup_value(
        id, name, current_user.get_bot(), user=current_user.get_user()
    )
    return {
        "message": "Lookup value removed!"
    }


@router.delete("/lookup/{id}", response_model=Response)
async def delete_lookup(
        id: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes existing lookup.
    """
    mongo_processor.delete_lookup(
        id, current_user.get_bot(), user=current_user.get_user()
    )
    return {
        "message": "Lookup removed!"
    }


@router.post("/slots/mapping", response_model=Response)
async def add_slot_mapping(request: SlotMappingRequest,
                           current_user: User = Security(Authentication.get_current_user_and_bot,
                                                         scopes=DESIGNER_ACCESS)):
    """
    Adds slot mapping.
    """
    mapping_id = mongo_processor.add_slot_mapping(request.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Slot mapping added', data={"id": mapping_id})


@router.put("/slots/mapping/{mapping_id}", response_model=Response)
async def update_slot_mapping(request: SlotMappingRequest,
                              mapping_id: str = Path(description="Slot Mapping id"),
                              current_user: User = Security(Authentication.get_current_user_and_bot,
                                                            scopes=DESIGNER_ACCESS)):
    """
    Updates slot mapping.
    """
    mongo_processor.update_slot_mapping(request.dict(), mapping_id)
    return Response(message='Slot mapping updated')


@router.get("/slots/mapping", response_model=Response)
async def get_slot_mapping(
        form: str = None,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Retrieves slot mapping.
    If form name is given as `form` query parameter, then slot mappings for that particular form will be retrieved.
    """
    return Response(data=list(mongo_processor.get_slot_mappings(current_user.get_bot(), form, True)))


@router.delete("/slots/mapping_id/{mapping_id}", response_model=Response)
async def delete_slot_mapping(mapping_id: str = Path(description="Slot Mapping id"),
                              current_user: User = Security(Authentication.get_current_user_and_bot,
                                                            scopes=DESIGNER_ACCESS)):
    """
    Deletes a slot mapping.
    """
    mongo_processor.delete_singular_slot_mapping(mapping_id)
    return Response(message='Slot mapping deleted')


@router.delete("/slots/mapping/{name}", response_model=Response)
async def delete_slot_mapping(name: str = Path(description="Name of the mapping"),
                              current_user: User = Security(Authentication.get_current_user_and_bot,
                                                            scopes=DESIGNER_ACCESS)):
    """
    Deletes a slot mapping.
    """
    mongo_processor.delete_slot_mapping(name, current_user.get_bot(), current_user.get_user())
    return Response(message='Slot mapping deleted')


@router.post("/forms", response_model=Response)
async def add_form(
        request: Forms, current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Adds a new form.
    """
    form = mongo_processor.add_form(request.name, request.dict()['settings'], current_user.get_bot(),
                                    current_user.get_user())
    return Response(data=form, message='Form added')


@router.get("/forms", response_model=Response)
async def list_forms(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Lists all forms in the bot.
    """
    forms = list(mongo_processor.list_forms(current_user.get_bot()))
    return Response(data=forms)


@router.get("/forms/{form_id}", response_model=Response)
async def get_form(
        form_id: str = Path(description="Form id"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Get a particular form.
    """
    form = mongo_processor.get_form(form_id, current_user.get_bot())
    return Response(data=form)


@router.put("/forms", response_model=Response)
async def edit_form(
        request: Forms, current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Edits a form.
    """
    mongo_processor.edit_form(request.name, request.dict()['settings'], current_user.get_bot(), current_user.get_user())
    return Response(message='Form updated')


@router.delete("/forms/{form_name}", response_model=Response)
async def delete_form(
        form_name: str,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes a form and its associated utterances.
    """
    mongo_processor.delete_form(form_name, current_user.get_bot(), current_user.get_user())
    return Response(message='Form deleted')


@router.get("/entities", response_model=Response)
async def list_entities(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)):
    """
    Fetch entities registered in a bot.
    """
    return Response(data=mongo_processor.get_entities(current_user.get_bot()))


@router.put("/assets/{asset_type}", response_model=Response)
async def upload_bot_assets(
        asset_type: str, asset: UploadFile,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Uploads bot assets to repository.
    """
    data = {"url": await AssetsProcessor.add_asset(current_user.get_bot(), current_user.get_user(), asset, asset_type)}
    UserActivityLogger.add_log(
        UserActivityType.add_asset, current_user.account, current_user.get_user(), current_user.get_bot(),
        [f"asset_type={asset_type}"]
    )
    return Response(message='Asset added', data=data)


@router.delete("/assets/{asset_type}", response_model=Response)
async def delete_bot_assets(
        asset_type: str, current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes bot assets from repository.
    """
    AssetsProcessor.delete_asset(current_user.get_bot(), current_user.get_user(), asset_type)
    UserActivityLogger.add_log(
        UserActivityType.delete_asset, current_user.account, current_user.get_user(), current_user.get_bot(),
        [f"asset_type={asset_type}"]
    )
    return Response(message='Asset deleted')


@router.get("/assets", response_model=Response)
async def list_bot_assets(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    Deletes bot assets from repository.
    """
    return Response(data={"assets": list(AssetsProcessor.list_assets(current_user.get_bot()))})


@router.post("/audit/event/config", response_model=Response)
async def set_auditlog_config(request_data: EventConfig,
                              current_user: User = Security(Authentication.get_current_user_and_bot,
                                                            scopes=DESIGNER_ACCESS)):
    mongo_processor.save_auditlog_event_config(current_user.get_bot(), current_user.get_user(), request_data.dict())
    return {"message": "Event config saved"}


@router.get("/audit/event/config", response_model=Response)
async def get_auditlog_config(current_user: User = Security(Authentication.get_current_user_and_bot,
                                                            scopes=DESIGNER_ACCESS)):
    data = mongo_processor.get_auditlog_event_config(current_user.get_bot())
    return Response(data=data)


@router.get("/auditlog/data/{from_date}/{to_date}", response_model=Response)
async def get_auditlog_for_bot(
        start_idx: int = 0, page_size: int = 10,
        from_date: date = Path(description="from date in yyyy-mm-dd format", examples=["1999-01-01"]),
        to_date: date = Path(description="to date in yyyy-mm-dd format", examples=["1999-01-01"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    logs, row_cnt = mongo_processor.get_auditlog_for_bot(current_user.get_bot(), from_date, to_date, start_idx, page_size)
    data = {
        "logs": logs,
        "total": row_cnt
    }
    return Response(data=data)


@router.get("/logs/download/{log_type}", response_model=Response)
async def download_logs(
        background_tasks: BackgroundTasks,
        start_date: datetime, end_date: datetime,
        log_type: str, current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    logs = mongo_processor.get_logs(current_user.get_bot(), log_type, start_date, end_date)
    file, temp_path = Utility.download_csv(logs, message=f"Logs not found!", filename=f"{log_type}.csv")
    response = FileResponse(
        file, filename=os.path.basename(file), background=background_tasks
    )
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=" + os.path.basename(file)
    background_tasks.add_task(Utility.delete_directory, temp_path)
    return response


@router.get("/qna/flatten", response_model=Response)
async def get_qna_flattened(
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS),
):
    qna = list(mongo_processor.flatten_qna(current_user.get_bot(), start_idx, page_size))
    page_cnt = mongo_processor.get_row_count(Rules, current_user.get_bot(), status=True,
                                             template_type=TemplateType.QNA.value)
    data = {
        "qna": qna,
        "total": page_cnt
    }
    return Response(data=data)


router.include_router(v2, prefix="/v2")


@router.get("/settings", response_model=Response)
async def get_bot_settings(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=AGENT_ACCESS),
):
    """Retrieves bot settings"""
    bot_settings = MongoProcessor.get_bot_settings(current_user.get_bot(), current_user.get_user())
    bot_settings = bot_settings.to_mongo().to_dict()
    bot_settings.pop("_id")
    return Response(data=bot_settings)


@router.put("/settings", response_model=Response)
async def update_bot_settings(
        bot_settings: BotSettingsRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS)
):
    """Updates bot settings"""
    MongoProcessor.edit_bot_settings(bot_settings.dict(), current_user.get_bot(), current_user.get_user())
    return Response(message='Bot Settings updated')


@router.get("/live_agent_token", response_model=Response)
async def get_live_agent_token(current_user: User = Security(Authentication.get_current_user_and_bot, scopes=AGENT_ACCESS)):
    """
    Fetches existing list of stories (conversation flows)
    """
    data = await LiveAgentHandler.authenticate_agent(current_user.get_user(), current_user.get_bot())
    return Response(data=data)


@router.get("/llm/logs", response_model=Response)
async def get_llm_logs(
        start_idx: int = 0, page_size: int = 10,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Get data llm event logs.
    """
    logs = list(LLMProcessor.get_logs(current_user.get_bot(), start_idx, page_size))
    row_cnt = LLMProcessor.get_row_count(current_user.get_bot())
    data = {
        "logs": logs,
        "total": row_cnt
    }
    return Response(data=data)


@router.get("/executor/logs", response_model=Response)
async def get_executor_logs(
        start_idx: int = 0, page_size: int = 10,
        event_class: str = None, task_type: str = None,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Get executor logs data based on filters provided.
    """
    logs = list(ExecutorProcessor.get_executor_logs(current_user.get_bot(), start_idx, page_size,
                                                    event_class=event_class, task_type=task_type))
    row_cnt = ExecutorProcessor.get_row_count(current_user.get_bot(),
                                              event_class=event_class,
                                              task_type=task_type)
    data = {
        "logs": logs,
        "total": row_cnt
    }
    return Response(data=data)


@router.get("/metadata/llm", response_model=Response)
async def get_llm_metadata(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)) -> Response:
    """
    Returns a list of LLMs and their corresponding models available for the bot.
    """
    llm_models = LLMProcessor.fetch_llm_metadata(current_user.get_bot())
    return Response(data=llm_models)


@router.get("/slots/{slot_name}", response_model=Response)
async def get_slot_actions(
        slot_name: str = Path(description="slot name", examples=["audio", "order"]),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)) -> Response:
    """
    Returns a list of Actions mapped to that particular slot name.
    """
    llm_models = MongoProcessor.get_slot_mapped_actions(current_user.get_bot(), slot_name)
    return Response(data=llm_models)



@router.get("/mail_channel/logs", response_model=Response)
async def get_mail_channel_logs(start_idx: int = 0, page_size: int = 10,
                                 current_user: User = Security(Authentication.get_current_user_and_bot,
                                                               scopes=TESTER_ACCESS)):
    """
    Retrieves mail channel related logs for the bot.
    """
    data = MailProcessor.get_log(current_user.get_bot(), start_idx, page_size)
    return Response(data=data)


@router.get("/mail_channel/read_mailbox", response_model=Response)
async def trigger_mail_channel_read(
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS),
):
    """
    Triggers asynchronous reading of emails from the configured mailbox.
    """
    event = MailReadEvent(current_user.get_bot(), current_user.get_user())
    event.validate()
    event.enqueue()
    return Response(message="mail channel read triggered")


@router.post("/change_flow_tag", response_model=Response)
async def change_flow_tag(
        request: FlowTagChangeRequest,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=DESIGNER_ACCESS)
):
    """
    change tag or rule or multiflow
    """
    data = request.dict()
    mongo_processor.change_flow_tag(
        bot = current_user.get_bot(),
        flow_name=data['name'],
        tag=data['tag'],
        flow_type=data['type']
    )
    return Response(message=f"Flow tag changed to '{data['tag']}'")

@router.get("/flow_tag/{tag}", response_model=Response)
async def get_flow_tag(
        tag: str = Path(description="flow tag"),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Fetches the flows with the given tag
    """
    flows = mongo_processor.get_flows_by_tag(current_user.get_bot(), tag)
    return Response(data=flows)

