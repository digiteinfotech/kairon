import json
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List
from rasa.cli import SubParsersAction

from kairon.events.definitions.mail_channel import MailProcessEvent, MailReadEvent


def read_channel_mails(args):
    MailReadEvent(args.bot, args.user).execute()


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    mail_parser = subparsers.add_parser(
        "mail-channel-read",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Mail channel initiate reading"
    )
    mail_parser.add_argument('bot',
                             type=str,
                             help="Bot id for which command is executed", action='store')

    mail_parser.add_argument('user',
                            type=str,
                            help="Kairon user who is initiating the command", action='store')

    mail_parser.set_defaults(func=read_channel_mails)