from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from mongoengine import connect
from kairon.shared.utils import Utility
from loguru import logger
from kairon.shared.otel import instrument

"""
CLI to train or import(and validate) data into kairon.

Usage:
    Train:
        kairon train <botid> <userid>
        kairon train <botid> <userid> <token>
    
    Import data:
        kairon data-importer <botid> <userid>
        kairon data-importer <botid> <userid> --import-data
        kairon data-importer <botid> <userid> --import-data --overwrite
        
    Test model:
        kairon test <bot-id> <user-id>
    
    Conversations Deletion:
        kairon delete-conversation <botid> <userid> <month>
        kairon delete-conversation <botid> <userid>
        
    Bot Translation:
        kairon multilingual <botid> <userid> <dlang>
        kairon multilingual <botid> <userid> <dlang> --translate-responses
        kairon multilingual <botid> <userid> <dlang> --translate-actions
        kairon multilingual <botid> <userid> <dlang> --translate-responses --translate-actions
    
    Training Data generation:
        kairon generate-data <botid> <userid> --from-website
        kairon generate-data <botid> <userid> --from-document
        
    Message broadcast:
        kairon broadcast <botid> <userid> <eventid> <is_resend>
    
    Delete audit logs:
        kairon delete-logs

"""


def create_argument_parser():
    from kairon.cli import importer, training, testing, conversations_deletion, translator, delete_logs,\
        message_broadcast,content_importer, mail_channel_read

    parser = ArgumentParser(
        prog="kairon",
        formatter_class=ArgumentDefaultsHelpFormatter,
        description="Kairon command line interface."
    )
    parent_parser = ArgumentParser(add_help=False)
    parent_parsers = [parent_parser]
    subparsers = parser.add_subparsers(help="Kairon commands")
    training.add_subparser(subparsers, parents=parent_parsers)
    importer.add_subparser(subparsers, parents=parent_parsers)
    testing.add_subparser(subparsers, parents=parent_parsers)
    conversations_deletion.add_subparser(subparsers, parents=parent_parsers)
    translator.add_subparser(subparsers, parents=parent_parsers)
    delete_logs.add_subparser(subparsers, parents=parent_parsers)
    message_broadcast.add_subparser(subparsers, parents=parent_parsers)
    content_importer.add_subparser(subparsers, parents=parent_parsers)
    mail_channel_read.add_subparser(subparsers, parents=parent_parsers)
    return parser


@instrument
def cli():
    parser = create_argument_parser()
    arguments = parser.parse_args()
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
    logger.debug(arguments)
    arguments.func(arguments)
