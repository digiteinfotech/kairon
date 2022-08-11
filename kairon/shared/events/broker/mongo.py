from typing import Text

from dramatiq import Message, Actor
from dramatiq_mongodb import MongoDBBroker
from loguru import logger
from pymongo import MongoClient
from pymongo.database import Database

from kairon import Utility
from kairon.events.executors.standalone import StandaloneExecutor
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from kairon.shared.events.broker.base import BrokerBase


class MongoBroker(BrokerBase):

    @classmethod
    def create_instance(cls):
        """
        Initialize an instance of MongoBroker based on configuration
        and also declare queue.
        """
        queue_name = Utility.environment['events']['queue']['name']
        mongo_url = Utility.environment['events']['queue']['url']
        mongo_config = Utility.mongoengine_connection(mongo_url)
        if not cls._broker:
            client = MongoClient(mongo_url)
            broker_db = Database(client, mongo_config['db'])
            cls._broker = MongoDBBroker(database=broker_db)
            cls._broker.declare_queue(queue_name)
        return cls()

    def declare_actors(self, actors: dict):
        """
        Declare all the actors and on which queue they should be attached to.
        Only 1 queue per actor. Defining again will replace older definition.
        """
        execution_timeout = Utility.environment['events']['executor'].get('timeout', 60) * 60 * 1000
        for fn, queue in actors.items():
            actor = Actor(
                fn, broker=self._broker, actor_name=fn.__name__,
                queue_name=queue, priority=0, options={'max_retries': 0, 'time_limit': execution_timeout}
            )
            self._broker.declare_actor(actor)

    def enqueue(self, event_class: EventClass, actor_name: Text = None, queue: Text = None, **message_body):
        """
        Enqueue the message in the broker.
        """
        try:
            if Utility.check_empty_string(queue):
                queue = Utility.environment['events']['queue']['name']
            if Utility.check_empty_string(actor_name):
                actor_name = StandaloneExecutor.execute_task.__name__
            msg = Message(
                queue_name=queue, actor_name=actor_name, args=(event_class, message_body), kwargs={}, options={}
            )
            return self._broker.enqueue(msg)
        except Exception as e:
            logger.exception(e)
            raise AppException(f"Failed to add task to queue: {e}")
