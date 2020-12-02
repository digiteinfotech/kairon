from argparse import ArgumentParser
from mongoengine import connect
from kairon.cli.training_data_generator import parse_document_and_generate_training_data
from kairon.utils import Utility
from kairon.train import start_training
from loguru import logger


def create_arg_parser():
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(help='functions')
    data_generation = subparsers.add_parser('generate-training-data', help="Initiate training data generation")
    data_generation.add_argument('bot', help="Bot id for which training data is to be generated", action='store',
                           nargs=1, type=str)
    data_generation.add_argument('user', help="User who is initiating training data generation", action='store', nargs=1,
                           type=str)
    data_generation.add_argument('token', help="JWT token for updating processing status", action='store', nargs=1, type=str)
    data_generation.set_defaults(which='data_generation')

    training = subparsers.add_parser('train', help="Initiate model training")
    training.add_argument('bot', help="Bot id for which training needs to trigger", action='store', nargs=1,
                                 type=str)
    training.add_argument('user', help="User who is training", action='store', nargs=1, type=str)
    training.add_argument('token', help="JWT token for remote agent reload", action='store', nargs=1, type=str)
    training.set_defaults(which='training')
    return parser


def main():
    parser = create_arg_parser()
    arguments = parser.parse_args()
    Utility.load_evironment()
    connect(host=Utility.environment['database']['url'])
    logger.info(arguments.bot)
    logger.info(arguments.user)
    if arguments.which == 'training':
        logger.info(arguments.token)
        start_training(arguments.bot, arguments.user, arguments.token)
    elif arguments.which == 'data_generation':
        parse_document_and_generate_training_data(arguments.bot, arguments.user, arguments.token)


if __name__ == "__main__":
    main()
