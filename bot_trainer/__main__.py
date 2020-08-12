from bot_trainer.train import start_training
from argparse import ArgumentParser
from smart_config import ConfigLoader
from mongoengine import connect
import asyncio


def create_arg_parser():
    parser = ArgumentParser()
    parser.add_argument('bot', help="Bot id for which training needs to trigger")
    parser.add_argument('user', help="User who is training")
    return parser


def main():
    parser = create_arg_parser()
    arguments = parser.parse_args()
    config = ConfigLoader('./system.yaml').get_config()
    connect(host=config['database']['url'])
    loop = asyncio.new_event_loop()
    loop.run_until_complete(start_training(arguments.bot, arguments.user, reload=False))


if __name__ == "__main__":
    main()