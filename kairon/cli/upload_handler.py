from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List
from loguru import logger
from rasa.cli import SubParsersAction
from kairon.events.definitions.upload_handler import UploadHandler
from kairon.shared.constants import UploadHandlerClass


def import_file_content(args):
    """
    CLI command handler to import File content.
    """
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("collection_name: {}", args.collection_name)
    upload_type = getattr(args, "upload_type", UploadHandlerClass.crud_data.value)
    logger.info("upload_type: {}", upload_type)
    logger.info("overwrite: {}", args.overwrite)

    UploadHandler(
        bot=args.bot,
        user=args.user,
        collection_name=args.collection_name,
        upload_type=upload_type,
        overwrite=args.overwrite
    ).execute()


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    """
    Add subparser for the 'file-importer' CLI command.
    """
    file_importer_parser = subparsers.add_parser(
        "file-importer",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Validates and imports file content into Kairon."
    )
    file_importer_parser.add_argument('bot',
                                   type=str,
                                   help="Bot id for which command is executed",
                                   action='store')
    file_importer_parser.add_argument('user',
                                   type=str,
                                   help="Kairon user who is initiating the command",
                                   action='store')
    file_importer_parser.add_argument('collection_name',
                                   type=str,
                                   help="The collection name where data will be imported",
                                   action='store')
    file_importer_parser.add_argument('upload_type',
                                      type=str,
                                      action='store',
                                      help="The upload type of the data provided")
    file_importer_parser.add_argument('--overwrite',
                                      default=False,
                                      action='store_true',
                                      help="Overwrites existing data if true, else appends.")

    file_importer_parser.set_defaults(func=import_file_content)
