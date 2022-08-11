from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.definitions.model_training import ModelTrainingEvent


def train(args):
    arguments_dict = args.__dict__
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("token exists: {}", str("token" in arguments_dict))
    ModelTrainingEvent(args.bot, args.user).execute(token=arguments_dict.get("token"))


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    train_parser = subparsers.add_parser(
        "train",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Initiate model training"
    )
    train_parser.add_argument('bot', type=str, help="Bot id for which command is executed", action='store')
    train_parser.add_argument('user', type=str, help="Kairon user who is initiating the command", action='store')
    train_parser.add_argument('token', help="JWT token for the user", action='store')
    train_parser.set_defaults(func=train)
