from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.definitions.data_importer import TrainingDataImporterEvent
from kairon.shared.constants import EventClass
from kairon.events.definitions.faq_importer import FaqDataImporterEvent


def validate_and_import(args):
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("import_data: {}", args.import_data)
    logger.info("overwrite: {}", args.overwrite)
    logger.info("event_type: {}", args.event_type)
    if args.event_type == EventClass.faq_importer.value:
        FaqDataImporterEvent(args.bot, args.user, overwrite=args.overwrite).execute()
    else:
        TrainingDataImporterEvent(args.bot, args.user, import_data=args.import_data, overwrite=args.overwrite).execute()


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    data_parser = subparsers.add_parser(
        "data-importer",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Validates and imports training data into kairon.",
    )
    data_parser.add_argument('bot',
                             type=str,
                             help="Bot id for which command is executed", action='store')
    data_parser.add_argument('user',
                             type=str,
                             help="Kairon user who is initiating the command", action='store')
    data_parser.add_argument('event_type',
                             type=str,
                             help="Event type: faq_importer/data_importer", action='store')
    data_parser.add_argument('--import-data',
                             default=False,
                             action='store_true',
                             help="Imports training data into kairon.")
    data_parser.add_argument('--overwrite',
                             default=False,
                             action='store_true',
                             help="Overwrites, if true, else appends to existing data."
                                  "True, by default.")

    data_parser.set_defaults(func=validate_and_import)
