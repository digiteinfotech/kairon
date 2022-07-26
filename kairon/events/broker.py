import dramatiq
from mongoengine import connect

from kairon import Utility
from kairon.events.executors.standalone import StandaloneExecutor
from kairon.shared.events.broker.factory import BrokerFactory

"""
Script to create broker and declare actor.
The intention here is to have multiple workers (each initialised using this script)
allowing event execution in parallel.
"""

Utility.load_environment()
config: dict = Utility.mongoengine_connection(Utility.environment['database']["url"])
connect(**config)
broker = BrokerFactory.get_instance()
dramatiq.set_broker(broker.get_broker())
broker.declare_actors({StandaloneExecutor().execute_task: Utility.environment['events']['queue']['name']})
