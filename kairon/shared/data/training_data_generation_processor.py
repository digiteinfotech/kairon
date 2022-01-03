from datetime import datetime
from typing import Text

from loguru import logger
from markdown.util import deprecated
from mongoengine import Q
from mongoengine.errors import DoesNotExist
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from .constant import EVENT_STATUS, TRAINING_DATA_GENERATOR_DIR
from .data_objects import TrainingDataGenerator, TrainingDataGeneratorResponse, TrainingExamplesTrainingDataGenerator


class TrainingDataGenerationProcessor:
    """
    Class contains logic for adding/updating training data generator status and history
    """
    @staticmethod
    def validate_history_id(doc_id):
        try:
            history = TrainingDataGenerator.objects().get(id=doc_id)
            if not history.response:
                logger.info("response field is empty.")
                raise AppException("No Training Data Generated")
        except DoesNotExist as e:
            logger.error(str(e))
            raise AppException("Matching history_id not found!")

    @staticmethod
    def format_data_and_set_status(
            response: dict, bot: Text, user: Text,
            status: EVENT_STATUS = EVENT_STATUS.SAVE.value, exception: Text = None
    ):
        training_data_list = None
        if response:
            training_data_list = []
            for training_data in response:
                training_examples = []
                for example in training_data['training_examples']:
                    training_examples.append(
                        TrainingExamplesTrainingDataGenerator(
                            training_example=example
                        )
                    )

                training_data_list.append(
                    TrainingDataGeneratorResponse(
                        intent=training_data.get('intent'),
                        training_examples=training_examples,
                        response=training_data.get('response')
                    ))
        TrainingDataGenerationProcessor.set_status(
            status=status,
            response=training_data_list,
            exception=exception,
            bot=bot,
            user=user
        )

    @staticmethod
    def set_status(
            bot: Text,
            user: Text,
            status: Text,
            document_path: Text = None,
            generator_type: Text = None,
            response: dict = None,
            exception: Text = None,
    ):
        """
        add or update training data generator status

        :param bot: bot id
        :param user: user id
        :param status: InProgress, Done, Fail
        :param document_path: location on disk where document is saved
        :param generator_type: document/website_url
        :param response: data generation response
        :param exception: exception while training
        :return: None
        """
        try:
            doc = TrainingDataGenerator.objects(bot=bot, user=user).filter(
                    Q(status=EVENT_STATUS.TASKSPAWNED.value) |
                    Q(status=EVENT_STATUS.INITIATED.value) |
                    Q(status=EVENT_STATUS.INPROGRESS.value)).get()
            doc.status = status
        except DoesNotExist as e:
            logger.error(str(e))
            doc = TrainingDataGenerator(
                status=EVENT_STATUS.INITIATED.value, generator_type=generator_type,
                document_path=document_path,
                start_timestamp=datetime.utcnow(), bot=bot
            )
        if status in [EVENT_STATUS.FAIL, EVENT_STATUS.COMPLETED]:
            doc.end_timestamp = datetime.utcnow()
            doc.last_update_timestamp = doc.end_timestamp
        doc.user = user
        doc.response = response
        doc.exception = exception
        doc.save()

    @staticmethod
    def fetch_latest_workload(
            bot: Text,
            user: Text,
    ):
        """
        fetch latest training data generator task

        :param bot: bot id
        :param user: user id
        :return: None
        """
        try:
            doc = TrainingDataGenerator.objects(bot=bot, user=user).filter(
                Q(status=EVENT_STATUS.TASKSPAWNED.value) |
                Q(status=EVENT_STATUS.INITIATED.value) |
                Q(status=EVENT_STATUS.INPROGRESS.value)).get().to_mongo().to_dict()
            doc.pop('_id')
        except DoesNotExist as e:
            logger.error(str(e))
            doc = None
        return doc

    @staticmethod
    def is_in_progress(bot: Text, raise_exception=True):
        """
        checks if there is any training data generation in progress

        :param bot: bot id
        :param raise_exception: whether to raise an exception, default is True
        :return: None
        :raises: AppException
        """
        if TrainingDataGenerator.objects(bot=bot).filter(
                Q(status=EVENT_STATUS.INITIATED) |
                Q(status=EVENT_STATUS.INPROGRESS) |
                Q(status=EVENT_STATUS.TASKSPAWNED)).count():
            if raise_exception:
                raise AppException("Previous data generation process not completed")
            else:
                return True
        else:
            return False

    @staticmethod
    def get_training_data_generator_history(bot: Text):
        """
        fetches training data generator history

        :param bot: bot id
        :return: yield dict of training history
        """
        return list(TrainingDataGenerationProcessor.__get_all_history(bot))

    @staticmethod
    def __get_all_history(bot: Text):
        """
        fetches training data generator history

        :param bot: bot id
        :return: yield dict of training history
        """
        for value in TrainingDataGenerator.objects(bot=bot).order_by("-start_timestamp"):
            item = value.to_mongo().to_dict()
            if item.get('document_path'):
                item['document_path'] = item['document_path'].replace(TRAINING_DATA_GENERATOR_DIR + '/', '').__str__()
            item.pop("bot")
            item.pop("user")
            item["_id"] = item["_id"].__str__()
            yield item

    @staticmethod
    def check_data_generation_limit(bot: Text, raise_exception=True):
        """
        checks if daily training data generation limit is exhausted

        :param bot: bot id
        :param raise_exception: whether to raise and exception
        :return: boolean
        :raises: AppException
        """
        today = datetime.today()

        today_start = today.replace(hour=0, minute=0, second=0)
        doc_count = TrainingDataGenerator.objects(
            bot=bot, start_timestamp__gte=today_start
        ).count()
        if doc_count >= Utility.environment['data_generation']["limit_per_day"]:
            if raise_exception:
                raise AppException("Daily file processing limit exceeded.")
            else:
                return True
        else:
            return False

    @staticmethod
    def update_is_persisted_flag(doc_id: Text, persisted_training_data: dict):
        training_examples_added = sum(persisted_training_data.values(), [])
        TrainingDataGenerator.objects(
            id=doc_id,
            response__training_examples__training_example__in=training_examples_added
        ).update(set__response__S__training_examples__is_persisted=True)

    @staticmethod
    @deprecated('This method has been rewritten above as mongoengine query')
    def update_is_persisted_flag(doc_id: Text, persisted_training_data: dict):
        history = TrainingDataGenerator.objects().get(id=doc_id)
        updated_training_data_with_flag = []
        for training_data in history.response:
            intent = training_data.intent
            response = training_data.response
            existing_training_examples = [example.training_example for example in training_data.training_examples]
            training_examples = []

            if persisted_training_data.get(intent):
                examples_added = persisted_training_data.get(training_data.intent)
                examples_not_added = list(set(existing_training_examples) - set(examples_added))

                for example in examples_not_added:
                    training_examples.append(
                        TrainingExamplesTrainingDataGenerator(
                            training_example=example
                        )
                    )

                for example in examples_added:
                    training_examples.append(
                        TrainingExamplesTrainingDataGenerator(
                            training_example=example,
                            is_persisted=True
                        )
                    )
            else:
                training_examples = training_data.training_examples

            updated_training_data_with_flag.append(
                TrainingDataGeneratorResponse(
                    intent=intent,
                    training_examples=training_examples,
                    response=response
                ))
        history.response = updated_training_data_with_flag
        history.save()
