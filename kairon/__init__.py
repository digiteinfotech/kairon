from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

from mongoengine import connect

from kairon.cli import data_importer, training
from kairon.utils import Utility


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
    data_importer.add_subparser(subparsers, parents=parent_parsers)
    return parser


def cli():
    parser = create_argument_parser()
    print(type(parser.parse_args()))
    print(parser.parse_args())
    arguments = parser.parse_args()
    Utility.load_evironment()
    connect(host=Utility.environment["database"]['url'])
    arguments.func(arguments)
