from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.events import EventsTrigger


def website_qna_generator(args):
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("website_url: {}", args.url)
    logger.info("depth: {}", args.depth)
    EventsTrigger.trigger_qna_generator_for_website(args.bot, args.user, args.url, args.depth)


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    train_parser = subparsers.add_parser(
        "generate-training-data",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Generate question and answers from a website."
    )
    train_parser.add_argument('bot', type=str, help="Bot id for which command is executed", action='store')
    train_parser.add_argument('user', type=str, help="Kairon user who is initiating the command", action='store')
    train_parser.add_argument('url', type=str, help="website url for which QnA should be generated", action='store')
    train_parser.add_argument(
        '--depth', type=int, help="Number of levels we want to traverse down on each url on website",
        nargs='?', const=2, default=2, action='store'
    )
    train_parser.set_defaults(func=website_qna_generator)
