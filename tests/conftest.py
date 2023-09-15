from kairon.shared.concurrency.actors.factory import ActorFactory


def pytest_sessionfinish(session, exitstatus):
    """ Run when the whole test run finishes. """
    for _, proxy in ActorFactory._ActorFactory__actors.items():
        proxy[1].stop()
