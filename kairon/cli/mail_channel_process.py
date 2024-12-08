import json
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List
from rasa.cli import SubParsersAction

from kairon.events.definitions.mail_channel import MailProcessEvent


def process_channel_mails(args):
    mails = json.loads(args.mails)
    if not isinstance(mails, list):
        raise ValueError("Mails should be a list")
    MailProcessEvent(args.bot, args.user).execute(mails=mails)


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    mail_parser = subparsers.add_parser(
        "mail-channel-process",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Mail channel process mails"
    )
    mail_parser.add_argument('bot',
                             type=str,
                             help="Bot id for which command is executed", action='store')

    mail_parser.add_argument('user',
                            type=str,
                            help="Kairon user who is initiating the command", action='store')

    mail_parser.add_argument('mails',
                            type=str,
                            help="json representing List of mails to be processed", action='store')

    mail_parser.set_defaults(func=process_channel_mails)