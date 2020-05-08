import tempfile
from contextlib import ExitStack
from typing import Text, Optional, Dict

from rasa.importers.importer import TrainingDataImporter
from rasa.train import DEFAULT_MODELS_PATH
from rasa.train import _train_async_internal, handle_domain_if_not_exists
from rasa.utils.common import TempDirectoryPath
import os
import logging
import asyncio
from bot_trainer.data_processor.importer import MongoDataImporter
from bot_trainer.data_processor.processor import AgentProcessor, ModelProcessor
from bot_trainer.data_processor.constant import MODEL_TRAINING_STATUS
from bot_trainer.exceptions import AppException
from datetime import datetime


async def train_model(
    data_importer: TrainingDataImporter,
    output_path: Text,
    force_training: bool = False,
    fixed_model_name: Optional[Text] = None,
    persist_nlu_training_data: bool = False,
    additional_arguments: Optional[Dict] = None,
):

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


def start_training(bot: str, user: str):
    exception = None
    model_file = None
    training_status = None

    ModelProcessor.set_training_status( bot=bot,
                                        user=user,
                                        status=MODEL_TRAINING_STATUS.INPROGRESS.value,
                                        start_timestamp=datetime.utcnow)
    try:
        loop = asyncio.new_event_loop()
        model_file = loop.run_until_complete(train_model_from_mongo(bot))
        training_status = MODEL_TRAINING_STATUS.DONE.value
    except Exception as e:
        logging.exception(e)
        training_status = MODEL_TRAINING_STATUS.FAIL.value
        exception = str(e)
        raise AppException(exception)
    finally:
        ModelProcessor.set_training_status( bot=bot,
                                            user=user,
                                            status=training_status,
                                            end_timestamp=datetime.utcnow,
                                            model_path=model_file,
                                            exception=exception)

    AgentProcessor.reload(bot)

    return model_file
