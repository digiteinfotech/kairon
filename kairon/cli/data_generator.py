from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.definitions.data_generator import DataGenerationEvent
from kairon.shared.constants import DataGeneratorCliTypes


def generate_training_data(args):
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("path: {}", args.path)
    if hasattr(args, "from_document"):
        logger.info("from_document: {}", args.from_document)
        # implementation TBD
    if hasattr(args, "from_website") and args.from_website:
        logger.info("from_website: {}", args.from_website)
        DataGenerationEvent(args.bot, args.user, website_url=args.path, depth=args.depth).execute()


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    data_parser = subparsers.add_parser(
        "generate-data",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Generates bot training data by parsing a website or document",
    )
    data_parser.add_argument('bot',
                             type=str,
                             help="Bot id for which command is executed", action='store')
    data_parser.add_argument('user',
                             type=str,
                             help="Kairon user who is initiating the command", action='store')
    group = data_parser.add_mutually_exclusive_group(required=True)
    group.add_argument(DataGeneratorCliTypes.from_website.value,
                       default=False,
                       help="Indicate if source is a website", action='store_true')
    group.add_argument(DataGeneratorCliTypes.from_document.value,
                       default=False,
                       help="Indicate if source is a document", action='store_true')
    data_parser.add_argument('path',
                             type=str,
                             help="Path of document or website to generate data from",
                             action='store')
    data_parser.add_argument('depth',
                             type=int,
                             help="depth upto which url on website need to be parsed",
                             action='store')
    data_parser.set_defaults(func=generate_training_data)
