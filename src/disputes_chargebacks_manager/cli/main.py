"""Minimal stdlib CLI: open a dispute, assess abuse, classify intake, verify the chain.

Thin argparse wrappers on the same services the API and the agent use, so rule R8 routing and the
deterministic engines are identical across every surface. No extra dependencies.
"""

from __future__ import annotations

import argparse
import sys

from ..config import build_container, build_service
from ..domain.kernel import parse_date
from ..domain.models import CustomerHistory, Dispute, DisputeTrack


def _add_dispute_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("dispute_id")
    parser.add_argument("track", choices=[t.value for t in DisputeTrack])
    parser.add_argument("reason_code")
    parser.add_argument("amount_minor", type=int)
    parser.add_argument("currency")
    parser.add_argument("transaction_date", help="ISO date of the transaction.")
    parser.add_argument("intake_date", help="ISO date the dispute was filed.")
    parser.add_argument("--actor", default="cli-user@bank.example")
    parser.add_argument(
        "--tenant", default="", help="Tenant partition asserted to human-review-console."
    )


def _dispute_from(args: argparse.Namespace) -> Dispute:
    return Dispute(
        id=args.dispute_id,
        tenant=args.tenant,
        track=DisputeTrack(args.track),
        reason_code=args.reason_code,
        amount_minor=args.amount_minor,
        currency=args.currency,
        transaction_date=parse_date(args.transaction_date),
        intake_date=parse_date(args.intake_date),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="disputes_chargebacks_manager")
    sub = parser.add_subparsers(dest="command", required=True)

    open_cmd = sub.add_parser("open", help="Assess eligibility and open a dispute case.")
    _add_dispute_args(open_cmd)
    open_cmd.add_argument("--as-of", required=True, help="ISO date to assess eligibility as of.")

    abuse_cmd = sub.add_parser("abuse", help="Score a dispute for refund abuse.")
    _add_dispute_args(abuse_cmd)
    abuse_cmd.add_argument("--disputes-90d", type=int, default=0)
    abuse_cmd.add_argument("--prior-abuse", type=int, default=0)
    abuse_cmd.add_argument("--refund-total", type=int, default=0)

    intake_cmd = sub.add_parser("intake", help="Classify an intake conversation.")
    intake_cmd.add_argument("conversation_ref")
    intake_cmd.add_argument("--actor", default="cli-user@bank.example")
    intake_cmd.add_argument("--tenant", default="")

    args = parser.parse_args(argv)
    service = build_service(build_container())

    if args.command == "open":
        result = service.open_dispute(
            _dispute_from(args), actor=args.actor, as_of=parse_date(args.as_of)
        )
        state = result.case.state.value
        print(f"{args.dispute_id}: eligible={result.eligibility.eligible} state={state}")
        for reason in result.eligibility.reasons:
            print(f"  reason: {reason}")
        if result.review_ref:
            print(f"  routed to human review: {result.review_ref}")
        return 0

    if args.command == "abuse":
        history = CustomerHistory(
            dispute_count_90d=args.disputes_90d,
            prior_abuse_count=args.prior_abuse,
            refund_total_minor_90d=args.refund_total,
        )
        decision = service.assess_abuse(_dispute_from(args), history, actor=args.actor)
        a = decision.assessment
        print(f"{args.dispute_id}: {a.outcome.value} (score {a.score})")
        print(f"  signals: {', '.join(a.signals)}")
        if decision.review_ref:
            print(f"  routed to human review: {decision.review_ref}")
        return 0

    if args.command == "intake":
        result = service.intake(args.conversation_ref, tenant=args.tenant, actor=args.actor)
        c = result.classification
        print(f"{args.conversation_ref}: {c.category.value} (opened={result.opened})")
        if result.review_ref:
            print(f"  routed to human review: {result.review_ref}")
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
