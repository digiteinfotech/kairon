from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.definitions.content_importer import DocContentImporterEvent


def import_doc_content(args):
    """
    CLI command handler to import document content.
    """
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("table_name: {}", args.table_name)
    logger.info("overwrite: {}", args.overwrite)

    DocContentImporterEvent(
        args.bot,
        args.user,
        table_name=args.table_name,
        overwrite=args.overwrite
    ).execute()


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    """
    Add subparser for the 'doc-importer' CLI command.
    """
    doc_import_parser = subparsers.add_parser(
        "doc-importer",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Validates and imports document content into Kairon."
    )
    doc_import_parser.add_argument('bot',
                                   type=str,
                                   help="Bot id for which command is executed",
                                   action='store')
    doc_import_parser.add_argument('user',
                                   type=str,
                                   help="Kairon user who is initiating the command",
                                   action='store')
    doc_import_parser.add_argument('table_name',
                                   type=str,
                                   help="The table name where data will be imported",
                                   action='store')
    doc_import_parser.add_argument('--overwrite',
                                   default=False,
                                   action='store_true',
                                   help="Overwrites existing data if true, else appends.")

    doc_import_parser.set_defaults(func=import_doc_content)
