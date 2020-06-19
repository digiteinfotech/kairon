import logging
import os
import tempfile
from contextlib import ExitStack
from typing import Text, Optional, Dict

import yaml
from rasa.constants import DEFAULT_CONFIG_PATH, DEFAULT_DATA_PATH, DEFAULT_DOMAIN_PATH
from rasa.importers.importer import TrainingDataImporter
from rasa.train import DEFAULT_MODELS_PATH
from rasa.train import _train_async_internal, handle_domain_if_not_exists, train
from rasa.utils.common import TempDirectoryPath

from bot_trainer.data_processor.constant import MODEL_TRAINING_STATUS
from bot_trainer.data_processor.importer import MongoDataImporter
from bot_trainer.data_processor.processor import AgentProcessor, ModelProcessor
from bot_trainer.data_processor.processor import MongoProcessor
from bot_trainer.exceptions import AppException
from bot_trainer.utils import Utility


async def train_model(
    data_importer: TrainingDataImporter,
    output_path: Text,
    force_training: bool = False,
    fixed_model_name: Optional[Text] = None,
    persist_nlu_training_data: bool = False,
    additional_arguments: Optional[Dict] = None,
):
    """ Trains the rasa model internally, using functions from the rasa modules """

    with ExitStack() as stack:
        train_path = stack.enter_context(TempDirectoryPath(tempfile.mkdtemp()))

        domain = await data_importer.get_domain()
        if domain.is_empty():
            return await handle_domain_if_not_exists(
                data_importer, output_path, fixed_model_name
            )

        return await _train_async_internal(
            data_importer,
            train_path,
            output_path,
            force_training,
            fixed_model_name,
            persist_nlu_training_data,
            additional_arguments,
        )


async def train_model_from_mongo(
    bot: str,
    force_training: bool = False,
    fixed_model_name: Optional[Text] = None,
    persist_nlu_training_data: bool = False,
    additional_arguments: Optional[Dict] = None,
):
    """ Trains the rasa model, using the data that is loaded onto
        Mongo, through the bot files """
    data_importer = MongoDataImporter(bot)
    output = os.path.join(DEFAULT_MODELS_PATH, bot)
    return await train_model(
        data_importer,
        output,
        force_training,
        fixed_model_name,
        persist_nlu_training_data,
        additional_arguments,
    )


def train_model_for_bot(bot: str):
    """ Trains the rasa model, using the data that is loaded onto
            Mongo, through the bot files """
    processor = MongoProcessor()
    nlu = processor.load_nlu(bot)
    if not nlu.training_examples:
        raise AppException("Training data does not exists!")
    domain = processor.load_domain(bot)
    stories = processor.load_stories(bot)
    config = processor.load_config(bot)

    directory = Utility.save_files(
                nlu.nlu_as_markdown().encode(),
                domain.as_yaml().encode(),
                stories.as_story_string().encode(),
                yaml.dump(config).encode(),
            )

    output = os.path.join(DEFAULT_MODELS_PATH, bot)
    model = train(domain=os.path.join(directory,DEFAULT_DOMAIN_PATH),
                  config=os.path.join(directory,DEFAULT_CONFIG_PATH),
                  training_files=os.path.join(directory,DEFAULT_DATA_PATH),
                  output=output)
    Utility.delete_directory(directory)
    return model


def start_training(bot: str, user: str):
    """ Prevents training of the bot if the training session is in progress otherwise start training """
    exception = None
    model_file = None
    training_status = None

    ModelProcessor.set_training_status(
        bot=bot,
        user=user,
        status=MODEL_TRAINING_STATUS.INPROGRESS.value,
    )
    try:
        model_file = train_model_for_bot(bot)
        training_status = MODEL_TRAINING_STATUS.DONE.value
    except Exception as e:
        logging.exception(e)
        training_status = MODEL_TRAINING_STATUS.FAIL.value
        exception = str(e)
        raise AppException(exception)
    finally:
        ModelProcessor.set_training_status(
            bot=bot,
            user=user,
            status=training_status,
            model_path=model_file,
            exception=exception,
        )

    AgentProcessor.reload(bot)
    return model_file
