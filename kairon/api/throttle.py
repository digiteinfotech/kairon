from kairon.shared.data.data_objects import Intents, TrainingExamples, ModelTraining
from kairon.shared.account.data_objects import Account, Bot
from kairon.shared.models import User
from kairon.exceptions import AppException
from datetime import datetime
from kairon.shared.utils import Utility


def limit_intent(func):
    def wrapped(current_user: User, **kwargs):
        account = Account.objects().get(id=current_user.account)
        count = Intents.objects(bot=current_user.get_bot()).count()
        limit = account.license['intents'] if "intents" in account.license else 10
        if count >= limit:
            raise AppException("Intent limit exhausted!")

    return wrapped


def limit_training_examples(func):
    def wrapped(current_user: User, **kwargs):
        account = Account.objects().get(id=current_user.account)
        limit = account.license['examples'] if "examples" in account.license else 50
        count = TrainingExamples.objects(bot=current_user.get_bot()).count()
        if count >= limit:
            raise AppException("Training example limit exhausted!")

    return wrapped


def limit_training(func):
    def wrapped(current_user: User, **kwargs):
        today = datetime.today()
        today_start = today.replace(hour=0, minute=0, second=0)
        account = Account.objects().get(id=current_user.account)
        limit = account.license['training'] if "training" in account.license else Utility.environment['model']['train'][
            "limit_per_day"]
        count = ModelTraining.objects(bot=current_user.get_bot(), start_timestamp__gte=today_start).count()
        if count >= limit:
            raise AppException("Training limit exhausted!")

    return wrapped


def limit_augmentation(func):
    def wrapped(current_user: User, **kwargs):
        account = Account.objects().get(id=current_user.account)
        limit = account.license['augmentation'] if "augmentation" in account.license else 5
        count = ModelTraining.objects(bot=current_user.get_bot()).count()
        if count >= limit:
            raise AppException("Daily augmentation limit exhausted!")

    return wrapped


def limit_bot(func):
    def wrapped(current_user: User, **kwargs):
        account = Account.objects().get(id=current_user.account)
        limit = account.license['bots'] if "bots" in account.license else 2
        count = Bot.objects(account=current_user.account).count()
        if count >= limit:
            raise AppException("Bot limit exhausted!")

    return wrapped
