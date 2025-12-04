from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.definitions.analytic_pipeline_handler import AnalyticsPipelineEvent


def trigger_pipeline(args):
    from kairon.shared.concurrency.actors.factory import ActorFactory

    logger.info("args: {}", args)
    bot = args.bot
    user = args.user
    event_id = args.event_id
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("event_id: {}", args.event_id)

    try:
        AnalyticsPipelineEvent(bot, user).execute(event_id=event_id)
    finally:
        ActorFactory.stop_all()



def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    notifier = subparsers.add_parser(
        "analytics_pipeline",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Executes Analytics Pipeline",
    )
    notifier.add_argument('bot',
                          type=str,
                          help="Bot id for which command is executed", action='store')
    notifier.add_argument('user',
                          type=str,
                          help="Kairon user who is initiating the command", action='store')
    notifier.add_argument('event_id',
                          type=str,
                          help="Analytics Pipeline Config document id", action='store')
    notifier.set_defaults(func=trigger_pipeline)
