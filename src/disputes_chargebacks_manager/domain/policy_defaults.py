"""The shipped bank-owned policy numbers, as pure data (mirrored in ``config/policy_packs.yaml``).

The reason-code packs and the refund-abuse thresholds are the CLIENT's numbers. They live here as
the shipped default and, identically, in ``config/policy_packs.yaml`` so a deployment overrides
them without a code edit; ``config.load_policy`` reads the file and
``tests/unit/test_policy_packs.py`` drift-guards the two against each other and validates the file
shape. Every value is obviously illustrative and synthetic.
"""

from __future__ import annotations

from .abuse_engine import AbusePolicy
from .eligibility_engine import ReasonCodePack, ReasonCodeRule
from .models import DisputeTrack

DEFAULT_REASON_CODE_PACKS: tuple[ReasonCodePack, ...] = (
    ReasonCodePack(
        track=DisputeTrack.CARD_SCHEME,
        scheme="card-scheme-illustrative",
        rules=(
            ReasonCodeRule(
                code="10.4",
                description="Other fraud, card-absent environment",
                filing_window_days=120,
                response_deadline_days=20,
                evidence_required=("transaction_receipt", "avs_result"),
            ),
            ReasonCodeRule(
                code="13.1",
                description="Merchandise or services not received",
                filing_window_days=120,
                response_deadline_days=30,
                evidence_required=("proof_of_delivery",),
            ),
            ReasonCodeRule(
                code="13.3",
                description="Not as described or defective",
                filing_window_days=120,
                response_deadline_days=30,
                evidence_required=("item_description", "return_policy"),
            ),
        ),
    ),
    ReasonCodePack(
        track=DisputeTrack.RETAIL,
        scheme="retail-buyer-dispute-illustrative",
        rules=(
            ReasonCodeRule(
                code="R-REFUND",
                description="Buyer refund request",
                filing_window_days=30,
                response_deadline_days=14,
                evidence_required=("order_record",),
            ),
            ReasonCodeRule(
                code="R-INR",
                description="Item not received",
                filing_window_days=45,
                response_deadline_days=14,
                evidence_required=("tracking_record",),
            ),
        ),
    ),
)

DEFAULT_ABUSE_POLICY = AbusePolicy()
