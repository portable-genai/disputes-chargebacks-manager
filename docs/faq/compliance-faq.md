# Compliance FAQ

For compliance, conduct and model-risk teams assessing the repo's regulatory posture.
Cross-references: [`../../COMPLIANCE.md`](../../COMPLIANCE.md) (the full P-01 to P-13 and R1 to R8
map with its evidence files and its open rows), [`../../SPEC.md`](../../SPEC.md),
[`../practices-audit.md`](../practices-audit.md) (the per-check verdicts).

### Is this deciding disputes autonomously?

No. It is a decision-support service. Every consequential outcome (an ineligible rejection, an
abuse REVIEW or DENY, a representment draft, a regulator draft, an unclassifiable or regulatory
intake) sets `requires_human_review` AND is routed to the `human-review-console` in the SAME
call that produced it, through the shared `review-kit` (dependency rule R8). The flag alone
is not the escalation, and `tests/unit/test_review_routing.py` asserts the ROUTING rather than the
flag on the API, CLI and agent paths alike. A CRITICAL band demands two approvals. The managed
router refuses to run with no console configured rather than swallowing an escalation, and
Terraform makes `human_review_url` required whenever the serving edge is enabled, so a deploy that
would ship R8 unwired fails at plan time.

### Can a decision be reconstructed by a reviewer?

Yes, without the model. Eligibility is a day-count comparison against a named reason-code rule;
the abuse verdict is a transparent additive score whose every firing signal carries a citation
naming the datum that fired it; lifecycle legality and the states a trigger sequence reaches are a
pure function of the workflow definition. All of it is stdlib and replayable
(`tests/unit/test_determinism.py`). An unknown reason code is INELIGIBLE with a stated reason
rather than assumed eligible, and an unknown trigger raises rather than being ignored: the engines
fail closed.

### How is customer PII handled?

This service DOES process personal data (narratives, transcripts, evidence documents, customer and
merchant references), so redaction is a live control rather than a not-applicable row. The shared
`pii-kit` is applied with a per-vertical row selection and ORDER (`domain/pii.py`, jurisdictions
`SG`, `HK`, `JP`, `AU` as shipped): before every audit write, before the intake transcript reaches
the narration port, before the narrative reaches the `complaints-review` module, before any review payload leaves
the process (against EVERY jurisdiction's rows, because the console is a shared sink), and on
every string of an agent tool result. The `pii_safety` eval metric is scored two ways and proved
able to go red.

The honest exception: the representment path passes extracted evidence fields and dispute facts to
the narration port unredacted, and the extractor's raw line snippets travel on the citation set
into the audit record's citation list. That is recorded in
[`../model-card.md`](../model-card.md) and must be closed before this path handles real evidence.

### How is the work auditable?

Every interaction writes an already-redacted, immutable `AuditEvent` with the action, the verified
actor, the decision, the severity and the citation set. The offline sink is append-only,
hash-chained AND externally anchored, so a truncated tail (which a hash chain alone cannot detect,
because the shorter chain still verifies) is caught; once store and anchor disagree the service
refuses to append rather than re-anchoring. In the managed profile the trail is a locked Cloud
Logging WORM bucket with CMEK, and `DATA_READ` audit logging is enabled so a read of the evidence
is itself recorded. The audit actor is always the server-verified principal, never the request
body.

### Is data residency enforced, or only documented?

Enforced at deploy time, in four layers, all present in `infra/terraform/`:

- **Plan-time validation**: `var.region` is checked against `var.allowed_regions` (default: the
  single region this repo was rendered for, `asia-southeast1`), so an unapproved region fails at
  `terraform plan`.
- **Org Policy**: `constraints/gcp.resourceLocations` restricted to the selected region's location
  group, plus `iam.disableServiceAccountKeyCreation` and `storage.uniformBucketLevelAccess`, all
  gated on `var.enable_org_policies`.
- **Regional CMEK**: a REGIONAL key ring and key with 90-day rotation, bound per service agent
  because CMEK does not cascade; the log bucket and the Cloud Run revision each name it.
- **VPC Service Controls**: a perimeter around the AI and control-plane APIs, created when
  `var.enable_vpc_sc` is true and DRY-RUN first (`var.vpc_sc_enforce = false` by default) so
  nobody enforces blind on a path they have not watched.

The honest caveat: none of that is guarded by the offline gate. `make gate` never runs
`terraform test`, and `infra/terraform/production_edge.tftest.hcl` (which asserts the residency and
fail-closed claims with a mocked provider and no credentials) has to be run deliberately. Treat
the residency posture as shipped-and-parameterised, not as regression-proof.

### What is the model-risk story?

`eval/run_eval.py --mode smoke` is the offline pre-merge gate and runs in `make gate`. It scores
six metrics, each against the dataset's OWN `expected_*` label rather than the pipeline's own
verdict: `eligibility_accuracy` and `abuse_accuracy` and `lifecycle_trace` at 1.0 (any single
divergence fails), `intake_accuracy` at 0.80, `groundedness` and `pii_safety` at 0.99. Before
scoring it PROVES every metric can go red. `--mode gate` delegates the promotion verdict to the
`model-quality-gate` authority and refuses to run off the managed profile.

Two open items: this repo's metric bundle is not registered with `model-quality-gate` yet, so gate mode has no
authority to ask (COMPLIANCE P-08 and R5); and the managed narration adapter is not wired, so the
eval measures the deterministic local narrator rather than a live model. There is a starter model
card at [`../model-card.md`](../model-card.md) recording the boundary and the controls still owed.

### Which rows does this repo still owe?

Read [`../../COMPLIANCE.md`](../../COMPLIANCE.md) for the authoritative list; the substantive ones
today are:

- **P-05 and R3 (grounding, knowledge base)**: no retrieval port and nothing grounded against
  `enterprise-knowledge-base`. Deliberately unclaimed rather than asserted.
- **R1 (guardrail)**: no `GuardrailPort`. Injection defence and output filtering at the model
  boundary are `agent-guardrail-gateway`'s job and are not wired.
- **R2 (shared audit and trace sink)**: spans reach the `agent-observability` collector when the OTLP endpoint is
  set; the audit record does not land in the shared sink.
- **R4 (agent registry)**: the A2A card is published but not registered with `agent-registry`.
- **R6 (intake validation)**: an `architecture-validator` validation reference has not been recorded.
- **P-10 (resilience)**: no timeouts, circuit breaker or documented kill switch per outbound
  dependency, and the CPS 230 recovery objectives are not yet in the runbook.
- **P-11 (cost and latency)**: nothing to route, cache or budget until a model call exists.
- **Tenant isolation**: the tenant partition rides every outbound review, but object-level
  authorisation from data tags waits on this service gaining a queryable store.

### Which regulators does this map to?

`COMPLIANCE.md` is aligned to MAS TRM, APRA CPS 234 and CPS 230, HKMA and PDPA-class regimes, and
it maps the catalog's own P-01 to P-13 principles and R1 to R8 rules to a control with a named
evidence file. The mapping from those to a SPECIFIC regulation, and the judgement that a control
is sufficient for it, is explicitly adopter-owned: it depends on the institution's risk appetite,
its regulator, its licence conditions and its existing control library. No row in that document
should be quoted as regulatory assurance. An adopter is expected to add the crosswalk to their own
control ids, the risk acceptance for every row still Partial or TODO at go-live, a second-line
review of the deterministic policy in `domain/` (which is bank-owned logic, not a vendor default
to inherit unexamined), and the retention schedule and legal basis for the audit trail.

### Can we run it against real dispute data today?

Not without your own legal, security and model-risk sign-off. Every fixture, transcript and golden
case is obviously synthetic. The adoption checklist in [`../ADOPTING.md`](../ADOPTING.md) lists
what must precede any live use: your scheme rules in the reason-code packs, your abuse thresholds,
your regulatory clocks, your jurisdictions, your IdP, your region, your golden set, and the
redaction gap on the representment path closed.
