import pytest
from mongoengine import connect
from bot_trainer.utils import Utility


class TestHistory:
    @pytest.fixture(autouse=True)
    def init_connection(self):
        Utility.load_evironment()
        connect(Utility.environment["mongo_db"], host=Utility.environment["mongo_url"])
