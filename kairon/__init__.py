from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

from mongoengine import connect

from kairon.cli import importer, training, testing, website_qna_generator
from kairon.shared.utils import Utility

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
        
    Generate QnA:
        kairon generate-training-data <botid> <userid> <website_url>
        kairon generate-training-data <botid> <userid> <website_url> <depth>
"""


def create_argument_parser():
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
    website_qna_generator.add_subparser(subparsers, parents=parent_parsers)
    return parser


def cli():
    parser = create_argument_parser()
    arguments = parser.parse_args()
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
    arguments.func(arguments)
