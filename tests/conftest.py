from kairon.shared.concurrency.actors.factory import ActorFactory
import pytest
import os


def pytest_sessionfinish(session, exitstatus):
    """ Run when the whole test run finishes. """
    for _, proxy in ActorFactory._ActorFactory__actors.items():
        proxy[1].stop()


@pytest.fixture(scope='session', autouse=True)
def rasa_log():
    os.environ['LOG_LEVEL_LIBRARIES'] = 'INFO'