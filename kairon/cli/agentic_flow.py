from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List
from rasa.cli import SubParsersAction

from kairon.events.definitions.agentic_flow import AgenticFlowEvent


def exec_agentic_flow(args):
    AgenticFlowEvent(args.bot, args.user).execute(flow_name=args.flow_name, slot_data=args.slot_data)


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    agentic_fow_parser = subparsers.add_parser(
        "agentic-flow",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Mail channel initiate reading"
    )
    agentic_fow_parser.add_argument('bot',
                             type=str,
                             help="Bot id for which command is executed", action='store')

    agentic_fow_parser.add_argument('user',
                            type=str,
                            help="Kairon user who is initiating the command", action='store')

    agentic_fow_parser.add_argument('flow_name',
                             type=str,
                             help="Kairon flow name to execute", action='store')

    agentic_fow_parser.add_argument('slot_data',
                                    type=str,
                                    help="json containing slot values dictionary", action='store')

    agentic_fow_parser.set_defaults(func=exec_agentic_flow)