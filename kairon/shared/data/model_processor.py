from datetime import datetime
from typing import Text
from mongoengine.errors import DoesNotExist
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from .constant import (
    MODEL_TRAINING_STATUS
)
from .data_objects import (
    ModelTraining,
)


class ModelProcessor:
    """
    Class contains logic for model training history
    """

    @staticmethod
    def set_training_status(
            bot: Text,
            user: Text,
            status: Text,
            model_path: Text = None,
            exception: Text = None,
    ):
        """
        add or update bot training history

        :param bot: bot id
        :param user: user id
        :param status: InProgress, Done, Fail
        :param model_path: new model path
        :param exception: exception while training
        :return: None
        """
        try:
            doc = ModelTraining.objects(bot=bot).get(
                status=MODEL_TRAINING_STATUS.INPROGRESS
            )
            doc.status = status
            doc.end_timestamp = datetime.utcnow()
        except DoesNotExist:
            doc = ModelTraining()
            doc.status = status
            doc.start_timestamp = datetime.utcnow()
            if status in [MODEL_TRAINING_STATUS.FAIL, MODEL_TRAINING_STATUS.DONE]:
                doc.end_timestamp = datetime.utcnow()

        doc.bot = bot
        doc.user = user
        doc.model_path = model_path
        doc.exception = exception
        doc.save()

    @staticmethod
    def is_training_inprogress(bot: Text, raise_exception=True):
        """
        checks if there is any bot training in progress

        :param bot: bot id
        :param raise_exception: whether to raise an exception, default is True
        :return: None
        :raises: AppException
        """
        if ModelTraining.objects(
                bot=bot, status=MODEL_TRAINING_STATUS.INPROGRESS.value
        ).count():
            if raise_exception:
                raise AppException("Previous model training in progress.")
            else:
                return True
        else:
            return False

    @staticmethod
    def is_daily_training_limit_exceeded(bot: Text, raise_exception=True):
        """
        checks if daily bot training limit is exhausted

        :param bot: bot id
        :param raise_exception: whether to raise and exception
        :return: boolean
        :raises: AppException
        """
        today = datetime.today()

        today_start = today.replace(hour=0, minute=0, second=0)
        doc_count = ModelTraining.objects(
            bot=bot, start_timestamp__gte=today_start
        ).count()
        if doc_count >= Utility.environment['model']['train']["limit_per_day"]:
            if raise_exception:
                raise AppException("Daily model training limit exceeded.")
            else:
                return True
        else:
            return False

    @staticmethod
    def get_training_history(bot: Text):
        """
        fetches bot training history

        :param bot: bot id
        :return: yield dict of training history
        """
        for value in ModelTraining.objects(bot=bot).order_by("-start_timestamp"):
            item = value.to_mongo().to_dict()
            item.pop("bot")
            item["_id"] = item["_id"].__str__()
            yield item
