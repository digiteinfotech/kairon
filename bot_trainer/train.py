from loguru import logger as logging
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
from subprocess import Popen, PIPE

async def train_model(
    data_importer: TrainingDataImporter,
    output_path: Text,
    force_training: bool = False,
    fixed_model_name: Optional[Text] = None,
    persist_nlu_training_data: bool = False,
    additional_arguments: Optional[Dict] = None,
):
    """
    trains the bot, overridden the function from rasa

    :param data_importer: TrainingDataImporter object
    :param output_path: model output path
    :param force_training: w
    :param fixed_model_name:
    :param persist_nlu_training_data:
    :param additional_arguments:
    :return: model path
    """
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
    """
    trains the bot from loading the data from mongo

    :param bot:
    :param force_training:
    :param fixed_model_name:
    :param persist_nlu_training_data:
    :param additional_arguments:
    :return: model path

    :todo loading data directly from mongo, bot is not able to idetify stories properly
    """
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
    """
    loads bot data from mongo into individual files for training

    :param bot: bot id
    :return: model path

    """
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
    #model = train(
    #    domain=os.path.join(directory, DEFAULT_DOMAIN_PATH),
    #    config=os.path.join(directory, DEFAULT_CONFIG_PATH),
    #    training_files=os.path.join(directory, DEFAULT_DATA_PATH),
    #    output=output,
    #)
    data_directory = os.path.join(directory,DEFAULT_DATA_PATH)
    domain_file = os.path.join(directory, DEFAULT_DOMAIN_PATH)
    config_file = os.path.join(directory, DEFAULT_CONFIG_PATH)
    data = Popen(f"rasa train --data {data_directory} --domain {domain_file} --config {config_file} --out {output}", stdout=PIPE).communicate()
    Utility.delete_directory(directory)
    del processor
    del nlu
    del domain
    del stories
    del config
    model = os.path.join(DEFAULT_MODELS_PATH, bot)
    return model


def start_training(bot: str, user: str):
    """
    prevents training of the bot,
    if the training session is in progress otherwise start training

    :param bot: bot id
    :param user: user id
    :return: model path
    """
    exception = None
    model_file = None
    training_status = None

    ModelProcessor.set_training_status(
        bot=bot, user=user, status=MODEL_TRAINING_STATUS.INPROGRESS.value,
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
