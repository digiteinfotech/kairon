import asyncio
import json
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction

from kairon.events.definitions.catalog_sync import CatalogSync


def sync_catalog_content(args):
    """
    CLI command handler to sync catalog content.
    """
    logger.info("bot: {}", args.bot)
    logger.info("user: {}", args.user)
    logger.info("provider: {}", args.provider)
    logger.info("sync_type: {}", args.sync_type)
    logger.info("token: {}", args.token)
    logger.info("data: {}", args.data)

    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON provided in --data: {}", e)
        return

    event = CatalogSync(
        bot=args.bot,
        user=args.user,
        provider=args.provider,
        sync_type=args.sync_type,
        token=args.token
    )

    asyncio.run(event.execute(data=data))


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    """
    Add subparser for the 'catalog-sync' CLI command.
    """
    catalog_sync_parser = subparsers.add_parser(
        "catalog-sync",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="Sync catalog content from POS(e.g., Petpooja) to Meta"
    )

    catalog_sync_parser.add_argument('bot',
                                     type=str,
                                     help="Bot ID for which the sync is performed",
                                     action='store')
    catalog_sync_parser.add_argument('user',
                                     type=str,
                                     help="Kairon user triggering the sync",
                                     action='store')
    catalog_sync_parser.add_argument('provider',
                                     type=str,
                                     help="Catalog provider name (e.g., petpooja)",
                                     action='store')
    catalog_sync_parser.add_argument('--sync_type',
                                     default="item_toggle",
                                     type=str,
                                     help="Type of sync to perform (default: item_toggle)",
                                     action='store')
    catalog_sync_parser.add_argument('--token',
                                     default="",
                                     type=str,
                                     help="Token for authentication",
                                     action='store')
    catalog_sync_parser.add_argument('--data',
                                     type=str,
                                     required=True,
                                     help="JSON-formatted catalog data to be synced",
                                     action='store')

    catalog_sync_parser.set_defaults(func=sync_catalog_content)