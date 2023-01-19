from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.definitions.model_testing import ModelTestingEvent


def run_tests_on_model(args):
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("augment_data: {}", args.augment)
    ModelTestingEvent(args.bot, args.user, augment_data=args.augment).execute()


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    test_parser = subparsers.add_parser(
        "test",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Tests model on existing stories or test stories.",
    )
    test_parser.add_argument('bot',
                             type=str,
                             help="Bot id for which command is executed", action='store')
    test_parser.add_argument('user',
                             type=str,
                             help="Kairon user who is initiating the command", action='store')
    test_parser.add_argument('--augment',
                             default=True,
                             action='store_false',
                             help="Augment training data and test against the model.")
    test_parser.set_defaults(func=run_tests_on_model)
