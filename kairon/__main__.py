from argparse import ArgumentParser

from mongoengine import connect
from kairon.utils import Utility
from kairon.train import start_training
from loguru import logger


def create_arg_parser():
    parser = ArgumentParser()
    parser.add_argument('bot', help="Bot id for which training needs to trigger")
    parser.add_argument('user', help="User who is training")
    parser.add_argument('token', help="JWT token for remote agent reload")
    return parser


def main():
    parser = create_arg_parser()
    arguments = parser.parse_args()
    Utility.load_evironment()
    connect(host=Utility.environment['database']['url'])
    logger.info(arguments.bot)
    logger.info(arguments.user)
    start_training(arguments.bot, arguments.user, arguments.token)


if __name__ == "__main__":
    main()