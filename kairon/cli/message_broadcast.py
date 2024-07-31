from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.definitions.message_broadcast import MessageBroadcastEvent


def send_notifications(args):
    from kairon.shared.concurrency.actors.factory import ActorFactory

    logger.info("args: {}", args)
    bot = args.bot
    user = args.user
    event_id = args.event_id
    is_resend = args.is_resend
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("event_id: {}", args.event_id)
    logger.info("is_resend: {}", args.is_resend)
    try:
        MessageBroadcastEvent(bot, user).execute(event_id=event_id, is_resend=is_resend)
    finally:
        ActorFactory.stop_all()


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    notifier = subparsers.add_parser(
        "broadcast",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Sends message broadcast",
    )
    notifier.add_argument('bot',
                          type=str,
                          help="Bot id for which command is executed", action='store')
    notifier.add_argument('user',
                          type=str,
                          help="Kairon user who is initiating the command", action='store')
    notifier.add_argument('event_id',
                          type=str,
                          help="Broadcast config document id or broadcast log reference id", action='store')
    notifier.add_argument('--is_resend',
                          type=str,
                          default="False",
                          help="Specify if the broadcast is a resend (True) or a normal broadcast (False).",
                          action='store')
    notifier.set_defaults(func=send_notifications)
