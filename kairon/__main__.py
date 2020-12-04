from argparse import ArgumentParser
from mongoengine import connect
from kairon.cli.training_data_generator import parse_document_and_generate_training_data
from kairon.utils import Utility
from kairon.train import start_training
from loguru import logger


def create_arg_parser():
    parser = ArgumentParser()
    parser.add_argument('--generate-training-data', '-g', action='store_const', const='-g', help="Initiate training data generation")
    parser.add_argument('--train', '-t', action='store_const', const='-t', help="Initiate model training")
    parser.add_argument('bot', help="Bot id for which command is executed", action='store',
                           nargs=1, type=str)
    parser.add_argument('user', help="Kairon user who is initiating the command", action='store', nargs=1,
                           type=str)
    parser.add_argument('token', help="JWT token for the user", action='store', nargs=1, type=str)
    return parser


def main():
    parser = create_arg_parser()
    arguments = parser.parse_args()
    Utility.load_evironment()
    connect(host=Utility.environment['database']['url'])
    logger.info(arguments.bot)
    logger.info(arguments.user)
    logger.info(arguments.token)
    logger.debug("-t: " + arguments.train)
    logger.debug("-g: " + arguments.generate_training_data)
    if (arguments.train.lower() == '--train' or arguments.train.lower() == '-t') and (arguments.generate_training_data.lower() == '--generate-training-data' or arguments.generate_training_data.lower() == '-g'):
        parser.error("You can use only one of '--train' and '--generate-training-data'")
    if arguments.train.lower() == '--train' or arguments.train.lower() == '-t':
        start_training(arguments.bot, arguments.user, arguments.token)
    elif arguments.generate_training_data.lower() == '--generate-training-data' or arguments.generate_training_data.lower() == '-g':
        parse_document_and_generate_training_data(arguments.bot, arguments.user, arguments.token)


if __name__ == "__main__":
    main()
