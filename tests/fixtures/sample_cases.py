"""Canonical synthetic disputes, shared by the unit and contract suites.

Every party is obviously fictional and every address is an ``.example`` domain or an RFC 5737 /
RFC 3849 literal. A small set of disputes covers the deterministic paths the suites assert:
eligible, ineligible (filed past the window), high-abuse, clean, and one carrying personal data
for the redact-before-anything proofs. One canonical disposition stands in for the R8 payload.
"""

from __future__ import annotations

from datetime import date

from disputes_chargebacks_manager.domain.kernel import Citation, Decision, Severity
from disputes_chargebacks_manager.domain.models import (
    CustomerHistory,
    Dispute,
    DisputeDisposition,
    DisputeTrack,
)

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "analyst@bank.example"

#: A tenant partition, so the outbound-review assertions are not all on the empty string.
TENANT = "demo-bank"

#: The date eligibility is assessed as of, across the suites.
AS_OF = date(2025, 6, 1)

#: A planted identifier, so a redaction assertion has an independent literal to look for.
PLANTED_NRIC = "S1234567D"

#: Eligible: a card-scheme 10.4 dispute filed nine days after the transaction (within 120 days).
ELIGIBLE_DISPUTE = Dispute(
    id="DSP-1001",
    tenant=TENANT,
    track=DisputeTrack.CARD_SCHEME,
    reason_code="10.4",
    amount_minor=42_000,
    currency="SGD",
    transaction_date=date(2025, 5, 1),
    intake_date=date(2025, 5, 10),
    product="credit_card",
    market="SG",
    channel="app",
    customer_ref="CUST-1",
    merchant_ref="MERCH-9",
    narrative="Cardholder reports a charge they did not make at an online shop.",
)

#: Ineligible: the SAME reason code filed well past its 120-day filing window (fail closed).
INELIGIBLE_DISPUTE = Dispute(
    id="DSP-1002",
    tenant=TENANT,
    track=DisputeTrack.CARD_SCHEME,
    reason_code="10.4",
    amount_minor=9_900,
    currency="SGD",
    transaction_date=date(2024, 1, 1),
    intake_date=date(2025, 5, 10),
    product="credit_card",
    market="SG",
)

#: A retail dispute with a high amount, paired with an abusive history below to force a DENY.
ABUSE_DISPUTE = Dispute(
    id="DSP-1003",
    tenant=TENANT,
    track=DisputeTrack.RETAIL,
    reason_code="R-REFUND",
    amount_minor=80_000,
    currency="SGD",
    transaction_date=date(2025, 5, 20),
    intake_date=date(2025, 5, 25),
    product="marketplace",
    market="SG",
)

#: A clean retail dispute paired with a clean history: the abuse engine must ALLOW.
CLEAN_DISPUTE = Dispute(
    id="DSP-1004",
    tenant=TENANT,
    track=DisputeTrack.RETAIL,
    reason_code="R-REFUND",
    amount_minor=1_500,
    currency="SGD",
    transaction_date=date(2025, 5, 20),
    intake_date=date(2025, 5, 25),
)

#: A dispute whose narrative carries personal data, for the redact-before-anything proofs.
PII_DISPUTE = Dispute(
    id="DSP-1005",
    tenant=TENANT,
    track=DisputeTrack.CARD_SCHEME,
    reason_code="13.1",
    amount_minor=60_000,
    currency="SGD",
    transaction_date=date(2025, 5, 1),
    intake_date=date(2025, 5, 3),
    customer_ref="CUST-5",
    narrative=f"Complaint from NRIC {PLANTED_NRIC}, mail ops@gamma.example, goods never arrived.",
)

#: The canonical dispute the contract suite drives every port with.
CANONICAL_DISPUTE = ELIGIBLE_DISPUTE

ABUSIVE_HISTORY = CustomerHistory(
    dispute_count_90d=9, prior_abuse_count=1, refund_total_minor_90d=300_000
)
CLEAN_HISTORY = CustomerHistory()

#: A sample evidence document in the ``key: value`` shape the local extractor reads.
EVIDENCE_TEXT = "proof_of_delivery: tracking SG9988\ncarrier: FictionalPost\nsigned_by: recipient"

#: A second planted identifier, differently shaped, so a redaction assertion is not one pattern.
PLANTED_EMAIL = "cardholder@delta.example"

#: Evidence carrying personal data. The extractor lifts every ``key: value`` line verbatim, so
#: this is the input that puts a raw identifier on the representment path (the model call, the
#: audit write and the pack handed back), which is where the redact-before-anything proof bites.
PII_EVIDENCE_TEXT = (
    f"cardholder_nric: {PLANTED_NRIC}\n"
    f"contact_email: {PLANTED_EMAIL}\n"
    "proof_of_delivery: tracking SG9988"
)

#: The escalated disposition the review-router contract case is handed (rule R8's payload).
CANONICAL_DISPOSITION = DisputeDisposition(
    subject=ELIGIBLE_DISPUTE.id,
    severity=Severity.HIGH,
    decision=Decision.ESCALATED,
    summary=f"{ELIGIBLE_DISPUTE.id}: ineligible rejection requires human sign-off",
    requires_human_review=True,
    dispute_id=ELIGIBLE_DISPUTE.id,
    outcome_label="ineligible rejection",
    citations=(Citation(source_id="pack:card", title="Reason-code pack", snippet="10.4"),),
)
