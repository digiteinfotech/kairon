import logging
import os

from fastapi import APIRouter, BackgroundTasks, Path
from fastapi import Depends, File, UploadFile
from fastapi.responses import FileResponse

from kairon.shared.actions.data_objects import HttpActionLog
from kairon.api.auth import Authentication
from kairon.api.models import (
    TextData,
    User,
    ListData,
    Response,
    Endpoint,
    RasaConfig,
    HttpActionConfigRequest, BulkTrainingDataAddRequest, TrainingDataGeneratorStatusModel, StoryRequest,
    FeedbackRequest,
    StoryType
)
from kairon.data_processor.constant import MODEL_TRAINING_STATUS, TRAINING_DATA_GENERATOR_STATUS
from kairon.data_processor.data_objects import TrainingExamples
from kairon.data_processor.processor import (
    MongoProcessor,
    AgentProcessor,
    ModelProcessor, TrainingDataGenerationProcessor,
)
from kairon.exceptions import AppException
from kairon.train import start_training
from kairon.utils import Utility
from urllib.parse import urljoin

router = APIRouter()
auth = Authentication()
mongo_processor = MongoProcessor()


@router.get("/intents", response_model=Response)
async def get_intents(current_user: User = Depends(auth.get_current_user)):
    """
    Fetches list of existing intents for particular bot
    """
    return Response(data=mongo_processor.get_intents(current_user.get_bot())).dict()


@router.get("/intents/all", response_model=Response)
async def get_intents_with_training_examples(current_user: User = Depends(auth.get_current_user)):
    """
    Fetches list of existing intents and associated training examples for particular bot
    """
    return Response(data=mongo_processor.get_intents_and_training_examples(current_user.get_bot())).dict()


@router.post("/intents", response_model=Response)
async def add_intents(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """
    Adds a new intent to the bot
    """
    intent_id = mongo_processor.add_intent(
        text=request_data.data.strip().lower(),
        bot=current_user.get_bot(),
        user=current_user.get_user(),
        is_integration=current_user.get_integration_status()
    )
    return {"message": "Intent added successfully!", "data": {"_id": intent_id}}


@router.delete("/intents/{intent}/{delete_dependencies}", response_model=Response)
async def delete_intent(
        intent: str = Path(default=None, description="intent name", example="greet"),
        delete_dependencies: bool = Path(
            default=True,
            description="""if True delete bot data related to this intent otherwise only delete intent""",
        ),
        current_user: User = Depends(auth.get_current_user),
):
    """
    deletes an intent including training examples and stories
    """
    mongo_processor.delete_intent(
        intent, current_user.get_bot(), current_user.get_user(), current_user.get_integration_status(),
        delete_dependencies
    )
    return {"message": "Intent deleted!"}


@router.post("/intents/predict", response_model=Response)
async def predict_intent(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """
    Fetches the predicted intent of the entered text form the loaded agent
    """
    model = AgentProcessor.get_agent(current_user.get_bot())
    response = await model.parse_message_using_nlu_interpreter(request_data.data)
    intent = response.get("intent").get("name") if response else None
    confidence = response.get("intent").get("confidence") if response else None
    return {"data": {"intent": intent, "confidence": confidence}}


@router.post("/intents/search", response_model=Response)
async def search_training_examples(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
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
        intent: str, current_user: User = Depends(auth.get_current_user)
):
    """
    Fetches all training examples against intent
    """
    return {
        "data": list(
            mongo_processor.get_training_examples(intent, current_user.get_bot())
        )
    }


@router.post("/training_examples/{intent}", response_model=Response)
async def add_training_examples(
        intent: str,
        request_data: ListData,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Adds training example in particular intent
    """
    results = list(
        mongo_processor.add_training_example(
            request_data.data, intent.lower(), current_user.get_bot(), current_user.get_user(),
            current_user.get_integration_status()
        )
    )
    return {"data": results}


@router.put("/training_examples/{intent}/{id}", response_model=Response)
async def edit_training_examples(
        intent: str,
        id: str,
        request_data: TextData,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Updates existing training example
    """
    mongo_processor.edit_training_example(
        id, request_data.data, intent.lower(), current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Training Example updated!"}


@router.delete("/training_examples", response_model=Response)
async def remove_training_examples(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """
    Deletes existing training example
    """
    mongo_processor.remove_document(
        TrainingExamples,
        request_data.data,
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {"message": "Training Example removed!"}


@router.get("/response/all", response_model=Response)
async def get_all_responses(
        current_user: User = Depends(auth.get_current_user)
):
    """
    Fetches list of all utterances added.
    """
    return {
        "data": list(mongo_processor.get_all_responses(current_user.get_bot()))
    }


@router.get("/response/{utterance}", response_model=Response)
async def get_responses(
        utterance: str, current_user: User = Depends(auth.get_current_user)
):
    """
    Fetches list of utterances against utterance name
    """
    return {
        "data": list(mongo_processor.get_response(utterance.lower(), current_user.get_bot()))
    }


@router.post("/response/{utterance}", response_model=Response)
async def add_responses(
        request_data: TextData,
        utterance: str,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Adds utterance value in particular utterance
    """
    utterance_id = mongo_processor.add_text_response(
        request_data.data, utterance.lower(), current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Utterance added!", "data": {"_id": utterance_id}}


@router.put("/response/{utterance}/{id}", response_model=Response)
async def edit_responses(
        utterance: str,
        id: str,
        request_data: TextData,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Updates existing utterance value
    """
    mongo_processor.edit_text_response(
        id,
        request_data.data,
        utterance.lower(),
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {
        "message": "Utterance updated!",
    }


@router.delete("/response/{delete_utterance}", response_model=Response)
async def remove_responses(
        request_data: TextData,
        delete_utterance: bool = Path(default=False, description="Deletes utterance if True"),
        current_user: User = Depends(auth.get_current_user)
):
    """
    Deletes existing utterance completely along with its examples.
    """
    if delete_utterance:
        mongo_processor.delete_utterance(
            request_data.data.lower(), current_user.get_bot(), current_user.get_user()
        )
    else:
        mongo_processor.delete_response(
            request_data.data, current_user.get_bot(), current_user.get_user()
        )
    return {
        "message": "Utterance removed!",
    }


@router.post("/stories", response_model=Response)
async def add_story(
        story: StoryRequest, current_user: User = Depends(auth.get_current_user)
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


@router.put("/stories", response_model=Response)
async def update_story(
        story: StoryRequest, current_user: User = Depends(auth.get_current_user)
):
    """
    Updates a story (conversational flow) in the particular bot
    """
    return {
        "message": "Flow updated successfully",
        "data": {
            "_id": mongo_processor.update_complex_story(
                story.dict(),
                current_user.get_bot(),
                current_user.get_user(),
            )
        },
    }


@router.get("/stories", response_model=Response)
async def get_stories(current_user: User = Depends(auth.get_current_user)):
    """
    Fetches existing list of stories (conversation flows)
    """
    return {"data": list(mongo_processor.get_stories(current_user.get_bot()))}


@router.delete("/stories/{story}/{type}", response_model=Response)
async def delete_stories(story: str = Path(default=None, description="Story name", example="happy_path"),
                         type: str = StoryType,
                         current_user: User = Depends(auth.get_current_user)
):
    """
    Updates a story (conversational flow) in the particular bot
    """
    mongo_processor.delete_complex_story(
        story,
        type,
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {
        "message": "Flow deleted successfully"
    }


@router.get("/utterance_from_intent/{intent}", response_model=Response)
async def get_story_from_intent(
        intent: str, current_user: User = Depends(auth.get_current_user)
):
    """
    Fetches the utterance or response that is mapped to a particular intent
    """
    response = mongo_processor.get_utterance_from_intent(intent, current_user.get_bot())
    return_data = {"name": response[0], "type": response[1]}
    return {"data": return_data}


@router.post("/chat", response_model=Response)
async def chat(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """
    Fetches a bot response for a given text/query.
    It is basically used to test the chat functionality of the agent
    """
    if Utility.environment.get('model') and Utility.environment['model']['train'].get('agent_url'):
        agent_url = Utility.environment['model']['train'].get('agent_url')
        token = auth.create_access_token(data={"sub": current_user.email})
        response = Utility.http_request('post', urljoin(agent_url, "/api/bot/chat"), token.decode('utf8'), current_user.get_user(), json={'data': request_data.data})
    else:
        model = AgentProcessor.get_agent(current_user.get_bot())
        response = await model.handle_text(
            request_data.data, sender_id=current_user.get_user()
        )
        response = {"data": {"response": response}}
    return response


@router.post("/train", response_model=Response)
async def train(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Trains the chatbot
    """
    Utility.train_model(background_tasks, current_user.get_bot(), current_user.get_user(), current_user.email, 'train')
    return {"message": "Model training started."}


@router.get("/model/reload", response_model=Response)
async def reload_model(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Reloads model with configuration in cache
    """
    background_tasks.add_task(AgentProcessor.reload, current_user.get_bot())
    return {"message": "Reloading Model!"}


@router.get("/train/history", response_model=Response)
async def get_model_training_history(
        current_user: User = Depends(auth.get_current_user),
):
    """
    Fetches model training history, when and who trained the bot
    """
    training_history = list(ModelProcessor.get_training_history(current_user.get_bot()))
    return {"data": {"training_history": training_history}}


@router.post("/deploy", response_model=Response)
async def deploy(current_user: User = Depends(auth.get_current_user)):
    """
    Deploys the latest bot model to the particular http endpoint
    """
    response = mongo_processor.deploy_model(
        bot=current_user.get_bot(), user=current_user.get_user()
    )
    return {"message": response}


@router.get("/deploy/history", response_model=Response)
async def deployment_history(current_user: User = Depends(auth.get_current_user)):
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
async def upload_Files(
        background_tasks: BackgroundTasks,
        nlu: UploadFile = File(...),
        domain: UploadFile = File(...),
        stories: UploadFile = File(...),
        config: UploadFile = File(...),
        rules: UploadFile = File(None),
        http_action: UploadFile = File(None),
        overwrite: bool = True,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Uploads training data nlu.md, domain.yml, stories.md and config.yml files
    """
    await mongo_processor.upload_and_save(
        nlu,
        domain,
        stories,
        config,
        rules,
        http_action,
        current_user.get_bot(),
        current_user.get_user(),
        overwrite)
    try:
        Utility.train_model(background_tasks, current_user.get_bot(), current_user.get_user(), current_user.email,
                            'upload')
    except Exception as e:
        logging.error(e)
        return {"message": "Please train your model!"}
    return {"message": "Data uploaded successfully!"}


@router.post("/upload/data_generation/file", response_model=Response)
async def upload_data_generation_file(
    background_tasks: BackgroundTasks,
    doc: UploadFile = File(...),
    current_user: User = Depends(auth.get_current_user)
):
    """
    Uploads document for training data generation and triggers event for intent creation
    """
    TrainingDataGenerationProcessor.is_in_progress(current_user.get_bot())
    TrainingDataGenerationProcessor.check_data_generation_limit(current_user.get_bot())
    file_path = await Utility.upload_document(doc)
    TrainingDataGenerationProcessor.set_status(bot=current_user.get_bot(),
          user=current_user.get_user(), status=TRAINING_DATA_GENERATOR_STATUS.INITIATED.value, document_path=file_path)
    token = auth.create_access_token(data={"sub": current_user.email})
    background_tasks.add_task(
        Utility.trigger_data_generation_event, current_user.get_bot(), current_user.get_user(), token.decode('utf8')
    )
    return {"message": "File uploaded successfully and training data generation has begun"}


@router.get("/download/data")
async def download_data(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Downloads training data nlu.md, domain.yml, stories.md, config.yml files
    """
    file = mongo_processor.download_files(current_user.get_bot())
    response = FileResponse(
        file, filename=os.path.basename(file), background=background_tasks
    )
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=" + os.path.basename(file)
    return response


@router.get("/download/model")
async def download_model(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Downloads latest trained model file
    """
    try:
        model_path = AgentProcessor.get_latest_model(current_user.get_bot())
        response = FileResponse(
            model_path,
            filename=os.path.basename(model_path),
            background=background_tasks,
        )
        response.headers[
            "Content-Disposition"
        ] = "attachment; filename=" + os.path.basename(model_path)
        return response
    except Exception as e:
        raise AppException(str(e))


@router.get("/endpoint", response_model=Response)
async def get_endpoint(current_user: User = Depends(auth.get_current_user),):
    """
    Fetches the http and mongo endpoint for the bot
    """
    endpoint = mongo_processor.get_endpoints(
        current_user.get_bot(), raise_exception=False
    )
    return {"data": {"endpoint": endpoint}}


@router.put("/endpoint", response_model=Response)
async def set_endpoint(
        background_tasks: BackgroundTasks,
        endpoint: Endpoint,
        current_user: User = Depends(auth.get_current_user),
):
    """
    Saves or Updates the bot endpoint configuration
    """
    mongo_processor.add_endpoints(
        endpoint.dict(), current_user.get_bot(), current_user.get_user()
    )

    if endpoint.action_endpoint:
        background_tasks.add_task(AgentProcessor.reload, current_user.get_bot())
    return {"message": "Endpoint saved successfully!"}


@router.get("/config", response_model=Response)
async def get_config(current_user: User = Depends(auth.get_current_user), ):
    """
    Fetches bot pipeline and polcies configurations
    """
    config = mongo_processor.load_config(current_user.get_bot())
    return {"data": {"config": config}}


@router.put("/config", response_model=Response)
async def set_config(
        config: RasaConfig, current_user: User = Depends(auth.get_current_user),
):
    """
    Saves or Updates the bot pipeline and policies configurations
    """
    mongo_processor.save_config(
        config.dict(), current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Config saved!"}


@router.get("/templates/use-case", response_model=Response)
async def get_templates(current_user: User = Depends(auth.get_current_user)):
    """
    Fetches use-case templates name
    """
    return {"data": {"use-cases": Utility.list_directories("./template/use-cases")}}


@router.post("/templates/use-case", response_model=Response)
async def set_templates(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """
    Applies the use-case template
    """
    await mongo_processor.apply_template(
        request_data.data, bot=current_user.get_bot(), user=current_user.get_user()
    )
    return {"message": "Data applied!"}


@router.get("/templates/config", response_model=Response)
async def get_config_template(current_user: User = Depends(auth.get_current_user)):
    """
    Fetches config templates
    """
    return {"data": {"config-templates": mongo_processor.get_config_templates()}}


@router.post("/templates/config", response_model=Response)
async def set_config_template(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """
    Applies the config template
    """
    mongo_processor.apply_config(
        request_data.data, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Config applied!"}


@router.post("/action/httpaction", response_model=Response)
async def add_http_action(request_data: HttpActionConfigRequest, current_user: User = Depends(auth.get_current_user)):
    """
    Stores the http action config and story event
    """
    http_config_id = mongo_processor.add_http_action_config(request_data.dict(), current_user.get_user(),
                                                            current_user.get_bot())
    response = {"http_config_id": http_config_id}
    message = "Http action added!"
    return Response(data=response, message=message)


@router.get("/action/httpaction/{action}", response_model=Response)
async def get_http_action(action: str = Path(default=None, description="action name", example="http_action"),
                          current_user: User = Depends(auth.get_current_user)):
    """
    Returns configuration set for the HTTP action
    """
    http_action_config = mongo_processor.get_http_action_config(action_name=action,
                                                                           bot=current_user.bot)
    action_config = Utility.build_http_response_object(http_action_config, current_user.get_user(), current_user.bot)
    return Response(data=action_config)


@router.get("/action/httpaction", response_model=Response)
async def list_http_actions(current_user: User = Depends(auth.get_current_user)):
    """
    Returns list of http actions for bot.
    """
    actions = mongo_processor.list_http_actions(bot=current_user.bot)
    return Response(data=actions)


@router.get("/actions", response_model=Response)
async def list_actions(current_user: User = Depends(auth.get_current_user)):
    """
    Returns list of actions for bot.
    """
    actions = mongo_processor.list_actions(bot=current_user.bot)
    return Response(data=actions)


@router.put("/action/httpaction", response_model=Response)
async def update_http_action(request_data: HttpActionConfigRequest,
                             current_user: User = Depends(auth.get_current_user)):
    """
    Updates the http action config and related story event
    """
    http_config_id = mongo_processor.update_http_config(request_data=request_data, user=current_user.get_user(),
                                                        bot=current_user.get_bot())
    response = {"http_config_id": http_config_id}
    message = "Http action updated!"
    return Response(data=response, message=message)


@router.delete("/action/httpaction/{action}", response_model=Response)
async def delete_http_action(action: str = Path(default=None, description="action name", example="http_action"),
                             current_user: User = Depends(auth.get_current_user)):
    """
    Deletes the http action config and story event
    """
    try:
        mongo_processor.delete_http_action_config(action, user=current_user.get_user(),
                                                  bot=current_user.bot)
    except Exception as e:
        raise AppException(e)
    message = "HTTP action deleted"
    return Response(message=message)


@router.get("/actions/logs", response_model=Response)
async def get_action_server_logs(start_idx: int = 0, page_size: int = 10, current_user: User = Depends(auth.get_current_user)):
    """
    Retrieves action server logs for the bot.
    """
    logs = list(mongo_processor.get_action_server_logs(current_user.get_bot(), start_idx, page_size))
    row_cnt = mongo_processor.get_row_count(HttpActionLog, current_user.get_bot())
    data = {
        "logs": logs,
        "total": row_cnt
    }
    return Response(data=data)


@router.post("/data/bulk", response_model=Response)
async def add_training_data(
        request_data: BulkTrainingDataAddRequest, current_user: User = Depends(auth.get_current_user)
):
    """
    Adds intents, training examples and responses along with story against the responses
    """
    try:
        TrainingDataGenerationProcessor.validate_history_id(request_data.history_id)
        status, training_data_added = mongo_processor.add_training_data(
            training_data=request_data.training_data,
            bot=current_user.get_bot(),
            user=current_user.get_user(),
            is_integration=current_user.get_integration_status()
        )
        TrainingDataGenerationProcessor.update_is_persisted_flag(request_data.history_id, training_data_added)
    except Exception as e:
        raise AppException(e)
    return {"message": "Training data added successfully!", "data": status}


@router.put("/update/data/generator/status", response_model=Response)
async def update_training_data_generator_status(
        request_data: TrainingDataGeneratorStatusModel, current_user: User = Depends(auth.get_current_user)
):
    """
    Update training data generator status
    """
    try:
        TrainingDataGenerationProcessor.retreive_response_and_set_status(request_data, current_user.get_bot(),
                                                                         current_user.get_user())
    except Exception as e:
        raise AppException(e)
    return {"message": "Status updated successfully!"}


@router.get("/data/generation/history", response_model=Response)
async def get_trainData_history(
        current_user: User = Depends(auth.get_current_user),
):
    """
    Fetches File Data Generation history, when and who initiated the process
    """
    file_history = TrainingDataGenerationProcessor.get_training_data_generator_history(current_user.get_bot())
    return {"data": {"training_history": file_history}}


@router.get("/data/generation/latest", response_model=Response)
async def get_latest_data_generation_status(
        current_user: User = Depends(auth.get_current_user),
):
    """
    Fetches status for latest data generation request
    """
    latest_data_generation_status = TrainingDataGenerationProcessor.fetch_latest_workload(current_user.get_bot(), current_user.get_user())
    return {"data": latest_data_generation_status}


@router.get("/slots", response_model=Response)
async def get_latest_data_generation_status(
        current_user: User = Depends(auth.get_current_user),
):
    """
    Fetches status for latest data generation request
    """
    slots = list(mongo_processor.get_existing_slots(current_user.get_bot()))
    return {"data": slots}


@router.post("/feedback", response_model=Response)
async def feedback(feedback: FeedbackRequest, current_user: User = Depends(auth.get_current_user),):
    """
    Receive feedback from user.
    """
    mongo_processor.add_feedback(feedback.rating, current_user.get_bot(), current_user.get_user(),
                                  feedback.scale, feedback.feedback)
    return {"message": "Thanks for your feedback!"}