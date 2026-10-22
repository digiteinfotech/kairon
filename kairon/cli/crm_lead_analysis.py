from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List

from loguru import logger
from rasa.cli import SubParsersAction


def run_analysis(args):
    """One cycle in this process. Intended for an ECS scheduled task or a manual run; safe to overlap."""
    from kairon.events.definitions.crm_lead_analysis import CRMLeadAnalysisEvent

    summary = CRMLeadAnalysisEvent().execute()
    logger.info("crm lead analysis summary: {}", summary)


def schedule_analysis(args):
    """Registers the five-minute job on the event server (idempotent)."""
    from kairon.events.definitions.crm_lead_analysis import CRMLeadAnalysisEvent

    CRMLeadAnalysisEvent.register_schedule(cron_exp=args.cron, timezone=args.timezone)
    logger.info("crm lead analysis scheduled: {}", args.cron)


def check_deployment(args):
    """Read-only readiness report; exit status 1 when a required check fails."""
    import json
    import sys
    from kairon.crm.deployment_check import run_checks, summarize

    report = summarize(run_checks())
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ready"] else 1)


def add_subparser(subparsers: SubParsersAction, parents: List[ArgumentParser]):
    parser = subparsers.add_parser(
        "crm_lead_analysis",
        conflict_handler="resolve",
        formatter_class=ArgumentDefaultsHelpFormatter,
        parents=parents,
        help="CRM lead analysis job",
    )
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run", help="Run one analysis cycle now")
    run.set_defaults(func=run_analysis)
    check = sub.add_parser("check", help="Read-only deployment readiness check (exit 1 if a required check fails)")
    check.set_defaults(func=check_deployment)
    sched = sub.add_parser("schedule", help="Register the recurring job on the event server")
    sched.add_argument("--cron", default="*/5 * * * *", help="Cron expression")
    sched.add_argument("--timezone", default="UTC")
    sched.set_defaults(func=schedule_analysis)
