from argparse import ArgumentParser
from mongoengine import connect
from kairon.utils import Utility
from kairon.train import start_training
from loguru import logger


def create_arg_parser():
    parser = ArgumentParser()
    parser.add_argument('--train', '-t', action='store_const', const='-t', help="Initiate model training")
    parser.add_argument('bot', type=str, help="Bot id for which command is executed", action='store')
    parser.add_argument('user', type=str, help="Kairon user who is initiating the command", action='store')
    parser.add_argument('token', help="JWT token for the user", action='store')
    return parser


def cli():
    parser = create_arg_parser()
    arguments = parser.parse_args()
    arguments_dict = arguments.__dict__
    Utility.load_evironment()
    connect(host=Utility.environment['database']['url'])
    logger.info(arguments.bot)
    logger.info(arguments.user)
    logger.info("token exists " + str("token" in arguments_dict))
    logger.debug("-t: " + arguments.train)
    if arguments.train.lower() == '--train' or arguments.train.lower() == '-t':
        start_training(arguments.bot, arguments.user, arguments_dict.get("token"))