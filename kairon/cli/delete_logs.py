from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.shared.data.processor import MongoProcessor


def delete_logs(args):
    logger.info("args: {}", args)
    MongoProcessor().delete_audit_logs()


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    delete_logs_parser = subparsers.add_parser(
        "delete-logs",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Delete audit logs"
    )
    delete_logs_parser.set_defaults(func=delete_logs)
