from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.events import EventsTrigger


def translate_multilingual_bot(args):
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("d_lang: {}", args.dlang)
    logger.info("translate_responses: {}", args.translate_responses)
    logger.info("translate_actions: {}", args.translate_actions)
    EventsTrigger.trigger_multilingual_translation(args.bot, args.user, args.dlang,
                                                   args.translate_responses, args.translate_actions)


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    data_parser = subparsers.add_parser(
        "multilingual",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Creates a new bot by translating the base bot into desired language.",
    )
    data_parser.add_argument('bot',
                             type=str,
                             help="Bot id for which command is executed", action='store')
    data_parser.add_argument('user',
                             type=str,
                             help="Kairon user who is initiating the command", action='store')
    data_parser.add_argument('dlang',
                             type=str,
                             help="Language of the translated bot", action='store')
    data_parser.add_argument('--translate-responses',
                             default=False,
                             help='Flag for translating responses', action='store_true')
    data_parser.add_argument('--translate-actions',
                             default=False,
                             help='Flag for translating actions', action='store_true')

    data_parser.set_defaults(func=translate_multilingual_bot)
