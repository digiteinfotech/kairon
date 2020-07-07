import os

from fastapi import APIRouter, BackgroundTasks
from fastapi import Depends, File, UploadFile
from fastapi.responses import FileResponse

from bot_trainer.api.auth import Authentication
from bot_trainer.api.models import (
    TextData,
    User,
    ListData,
    Response,
    StoryRequest,
    Endpoint,
    Config,
)
from bot_trainer.data_processor.data_objects import TrainingExamples, Responses
from bot_trainer.data_processor.processor import (
    MongoProcessor,
    AgentProcessor,
    ModelProcessor,
)
from bot_trainer.exceptions import AppException
from bot_trainer.train import start_training
from bot_trainer.utils import Utility

router = APIRouter()
auth = Authentication()
mongo_processor = MongoProcessor()


@router.get("/intents", response_model=Response)
async def get_intents(current_user: User = Depends(auth.get_current_user)):
    """ This function returns the list of existing intents of the bot """
    return Response(data=mongo_processor.get_intents(current_user.get_bot())).dict()


@router.post("/intents", response_model=Response)
async def add_intents(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """ This function is used to add a new intent to the bot """
    id = mongo_processor.add_intent(
        text=request_data.data.strip(), bot=current_user.get_bot(), user=current_user.get_user()
    )
    return {"message": "Intent added successfully!", "data": {"_id": id}}


@router.post("/intents/predict", response_model=Response)
async def predict_intent(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """ This function returns the predicted intent of the entered text by using the trained
        rasa model of the chatbot """
    model = AgentProcessor.get_agent(current_user.get_bot())
    response = await model.parse_message_using_nlu_interpreter(request_data.data)
    intent = response.get("intent").get("name") if response else None
    confidence = response.get("intent").get("confidence") if response else None
    return {"data": {"intent": intent, "confidence": confidence}}


@router.post("/intents/search", response_model=Response)
async def search_intent(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """ This function returns the search intent of the entered text by using mongo text search"""
    search_items = list(mongo_processor.search_training_examples(request_data.data, current_user.get_bot()))
    return {"data": {"searched_items": search_items}}


@router.get("/training_examples/{intent}", response_model=Response)
async def get_training_examples(
        intent: str, current_user: User = Depends(auth.get_current_user)
):
    """
    fetch all training examples against intent
    :param intent: intent name
    :param current_user: loggedin user id
    :return: list of training examples
    """
    """ This function is used to return the training examples (questions/sentences)
        which are used to train the chatbot, for a particular intent """
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
    add training example
    :param intent: intent name
    :param request_data: training example
    :param current_user: loggedin user id
    :return: Training Example Id
    """
    """ This is used to add a new training example (sentence/question) for a
        particular intent """
    results = list(
        mongo_processor.add_training_example(
            request_data.data, intent, current_user.get_bot(), current_user.get_user()
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
    update existing training example
    :param intent: intent name
    :param id: training example id
    :param request_data: updated training example
    :param current_user: loggedin user id
    :return: "Training Example updated!"
    """
    mongo_processor.edit_training_example(
        id, request_data.data, intent, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Training Example updated!"}


@router.delete("/training_examples", response_model=Response)
async def remove_training_examples(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """
    delete existing training example
    :param request_data: trianing example id
    :param current_user: loggedin user id
    :return: Training Example removed!
    """
    """ This function is used to delete a particular training example (question/sentence) from a list
        of examples for a particular intent """
    mongo_processor.remove_document(
        TrainingExamples,
        request_data.data,
        current_user.get_bot(),
        current_user.get_user(),
    )
    return {"message": "Training Example removed!"}


@router.get("/response/{utterance}", response_model=Response)
async def get_responses(
        utterance: str, current_user: User = Depends(auth.get_current_user)
):
    """
    fetch list of utterances against utterance name
    :param utterance: utterance name
    :param current_user: loggedin user id
    :return: list of utterances
    """
    return {
        "data": list(mongo_processor.get_response(utterance, current_user.get_bot()))
    }


@router.post("/response/{utterance}", response_model=Response)
async def add_responses(
        request_data: TextData,
        utterance: str,
        current_user: User = Depends(auth.get_current_user),
):
    """
    add utterance
    :param request_data: utterance value to add
    :param utterance: utterance name
    :param current_user: loggedin user id
    :return: Utterance added!
    """
    id = mongo_processor.add_text_response(
        request_data.data, utterance, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Utterance added!", "data": {"_id": id}}


@router.delete("/response", response_model=Response)
async def remove_responses(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """
    remove existing utterance
    :param request_data: utterance id
    :param current_user: loggedin user id
    :return: Utterance removed!
    """
    mongo_processor.remove_document(
        Responses, request_data.data, current_user.get_bot(), current_user.get_user()
    )
    return {
        "message": "Utterance removed!",
    }


@router.put("/response/{utterance}/{id}", response_model=Response)
async def edit_responses(
        utterance: str,
        id: str,
        request_data: TextData,
        current_user: User = Depends(auth.get_current_user)
):
    """
    update exising utterance
    :param utterance: utterance name
    :param id: utterance id
    :param request_data: new utterance value
    :param current_user: loggedin user id
    :return: Utterance updated!
    """
    mongo_processor.edit_text_response(
        id, request_data.data, utterance, current_user.get_bot(), current_user.get_user()
    )
    return {
        "message": "Utterance updated!",
    }


@router.post("/stories", response_model=Response)
async def add_stories(
        story: StoryRequest, current_user: User = Depends(auth.get_current_user)
):
    """ This function is used to add a story (conversational flow) to the chatbot """
    return {
        "message": "Story added successfully",
        "data": {
            "_id": mongo_processor.add_story(
                story.name,
                story.get_events(),
                current_user.get_bot(),
                current_user.get_user(),
            )
        },
    }


@router.get("/stories", response_model=Response)
async def get_stories(current_user: User = Depends(auth.get_current_user)):
    """ This returns the existing list of stories (conversation flows) of the bot """
    return {"data": list(mongo_processor.get_stories(current_user.get_bot()))}


@router.get("/utterance_from_intent/{intent}", response_model=Response)
async def get_story_from_intent(
        intent: str, current_user: User = Depends(auth.get_current_user)
):
    """ This function returns the utterance or response that is mapped to a particular intent """
    return {
        "data": mongo_processor.get_utterance_from_intent(
            intent, current_user.get_bot()
        )
    }


@router.post("/chat", response_model=Response)
async def chat(
        request_data: TextData, current_user: User = Depends(auth.get_current_user)
):
    """ This function returns a bot response for a given text/query. It is basically
        used to test the chat functionality of the bot """
    model = AgentProcessor.get_agent(current_user.get_bot())
    response = await model.handle_text(request_data.data, sender_id=current_user.get_user())
    return {"data": {"response": response[0]["text"] if response else None}}


@router.post("/train", response_model=Response)
async def train(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(auth.get_current_user),
):
    """ This is used to train the chatbot """
    ModelProcessor.is_training_inprogress(current_user.get_bot())
    ModelProcessor.is_daily_training_limit_exceeded(current_user.get_bot())
    background_tasks.add_task(
        start_training, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Model training started."}


@router.get("/model_training_history", response_model=Response)
async def get_model_training_history(
        current_user: User = Depends(auth.get_current_user),
):
    training_history = list(ModelProcessor.get_training_history(current_user.get_bot()))
    return {"data": {"training_history": training_history}}


@router.post("/deploy", response_model=Response)
async def deploy(current_user: User = Depends(auth.get_current_user)):
    """ This function is used to deploy the model of the currently trained chatbot """
    response = mongo_processor.deploy_model(bot=current_user.get_bot(), user=current_user.get_user())
    return {"message": response}


@router.get("/deployment_history", response_model=Response)
async def deployment_history(current_user: User = Depends(auth.get_current_user)):
    """ This function is used to deploy the model of the currently trained chatbot """
    return {"data": {"deployment_history": list(mongo_processor
                                                .get_model_deployment_history(bot=current_user.get_bot()))}}


@router.post("/upload", response_model=Response)
async def upload_Files(
        background_tasks: BackgroundTasks,
        nlu: UploadFile = File(...),
        domain: UploadFile = File(...),
        stories: UploadFile = File(...),
        config: UploadFile = File(...),
        overwrite: bool = True,
        current_user: User = Depends(auth.get_current_user),
):
    """Upload training data nlu.md, domain.yml, stories.md and config.yml files"""
    await mongo_processor.upload_and_save(
        await nlu.read(),
        await domain.read(),
        await stories.read(),
        await config.read(),
        current_user.get_bot(),
        current_user.get_user(),
        overwrite,
    )
    background_tasks.add_task(
        start_training, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Data uploaded successfully!"}


@router.get("/download_data")
async def download_data(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(auth.get_current_user), ):
    """Download training data nlu.md, domain.yml, stories.md, config.yml files"""
    file = mongo_processor.download_files(current_user.get_bot())
    response = FileResponse(file, filename=os.path.basename(file), background=background_tasks)
    response.headers["Content-Disposition"] = "attachment; filename=" + os.path.basename(file)
    return response


@router.get("/download_model")
async def download_model(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(auth.get_current_user), ):
    """Download latest trained model file"""
    try:
        model_path = AgentProcessor.get_latest_model(current_user.get_bot())
        response = FileResponse(model_path, filename=os.path.basename(model_path), background=background_tasks)
        response.headers["Content-Disposition"] = "attachment; filename=" + os.path.basename(model_path)
        return response
    except Exception as e:
        raise AppException(str(e))


@router.get("/endpoint", response_model=Response)
async def get_endpoint(current_user: User = Depends(auth.get_current_user), ):
    """get the model endpoint"""
    endpoint = mongo_processor.get_endpoints(
        current_user.get_bot(), raise_exception=False
    )
    return {"data": {"endpoint": endpoint}}


@router.put("/endpoint", response_model=Response)
async def set_endpoint(
        background_tasks: BackgroundTasks,
        endpoint: Endpoint,
        current_user: User = Depends(auth.get_current_user)
):
    """get the bot config"""
    mongo_processor.add_endpoints(
        endpoint.dict(), current_user.get_bot(), current_user.get_user()
    )

    if endpoint.action_endpoint:
        background_tasks.add_task(
            AgentProcessor.reload, current_user.get_bot()
        )
    return {"message": "Endpoint saved successfully!"}


@router.get("/config", response_model=Response)
async def get_config(current_user: User = Depends(auth.get_current_user), ):
    """
    fetch bot pipeline and polcies configurations
    :param current_user: user id
    :return: dict of configurations
    """
    config = mongo_processor.load_config(current_user.get_bot())
    return {"data": {"config": config}}


@router.put("/config", response_model=Response)
async def set_config(
        config: Config, current_user: User = Depends(auth.get_current_user),
):
    """
    save the bot pipeline and policies configurations
    :param config: configuration
    :param current_user: user id
    :return: Config saved!
    """
    mongo_processor.save_config(
        config.dict(), current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Config saved!"}


@router.get("/templates", response_model=Response)
async def get_templates(current_user: User = Depends(auth.get_current_user)):
    """
    fetch use-case templates name
    :param current_user:
    :return: list of use-case name
    """
    return {"data": {"use-cases": Utility.list_directories("./template/use-cases")}}


@router.post("/templates", response_model=Response)
async def get_templates(
        request_data: TextData,
        current_user: User = Depends(auth.get_current_user)):
    """
    apply the use-case template
    :param request_data: use-case name
    :param current_user: user id
    :return: Data applied!
    :exception: Invalid template
    """
    await mongo_processor.apply_template(request_data.data,
                                        bot=current_user.get_bot(),
                                        user=current_user.get_user())
    return {"message": "Data applied!"}


@router.get("/reload_model", response_model=Response)
async def reload_model(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(auth.get_current_user)):
    """
    reload model with configuration in cache
    :param current_user: user id
    :return: Model reloaded!
    """
    background_tasks.add_task(
        AgentProcessor.reload, current_user.get_bot()
    )
    return {"message": "Reloading Model!"}


@router.get("/config/templates", response_model=Response)
async def get_config_template(
        current_user: User = Depends(auth.get_current_user)):
    """
    fetch config templates
    :param current_user: user id
    :return: list of config templates with name
    """
    return {"data": {"config-templates": mongo_processor.get_config_templates()}}


@router.post("/config/templates", response_model=Response)
async def set_config_template(
        request_data: TextData,
        current_user: User = Depends(auth.get_current_user)):
    """
    apply the config template
    :param request_data: config template name
    :param current_user: user id
    :return: Config Applied!
    """
    mongo_processor.apply_config(request_data.data, current_user.get_bot(), current_user.get_user())
    return {"message": "Config applied!"}

@router.delete("/Intent/{intent}", response_model=Response)
async def delete_intent(
        intent: str, current_user: User = Depends(auth.get_current_user)
):
    """This function will be utilized to delete an intent and its dependencies with TrainingExamples and Stories"""
    intentName = mongo_processor.deleteIntentWithDependencies(
        intent, current_user.get_bot(), current_user.get_user()
    )
    return {"message": "Intent successfully deleted!", "data": {"IntentName": intentName}}