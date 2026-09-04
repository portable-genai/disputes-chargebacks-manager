# Features FAQ

For product, operations and delivery teams: what this service does, what is deterministic vs what
the model touches, and where its responsibilities **stop** and a sibling catalog system takes
over. Cross-references: [`../../README.md`](../../README.md), [`../../SPEC.md`](../../SPEC.md),
[`../../DEMO.md`](../../DEMO.md), [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).

### What does F2 actually produce?

Five cited artifacts across the dispute lifecycle, all of them replayable and all of them
review-gated where they are consequential:

1. **An eligibility verdict and an opened case.** `open_dispute` assesses a dispute against the
   reason-code pack for its track, opens a case on the spine, and advances it. Eligible goes to
   `EVIDENCE_REVIEW`; INELIGIBLE goes to `REJECTED` and is routed to human review, because a
   machine-rejected customer dispute must be signed off. Each case carries computed deadlines,
   marked regulatory or operational.
2. **A refund-abuse assessment.** A transparent additive score over velocity, single-amount,
   trailing refund-total and prior-abuse signals, each firing signal carrying a citation naming
   the datum that fired it, resolving to ALLOW, REVIEW or DENY. REVIEW and DENY are consequential
   and route to sign-off. The engine never auto-closes anything.
3. **An intake classification.** One intake conversation is classified into the CLOSED
   `IntakeCategory` set. A clean card or retail category is eligible to open a lifecycle case; an
   unclassifiable intake and a regulatory complaint both fail closed to human review.
4. **A representment draft.** Evidence documents are parsed at the edge into labelled fields, each
   cited back to the document; the draft narrates over those fields and the dispute facts. It
   always requires human review and never posts to a scheme.
5. **A regulator-response draft**, delegated to the `complaints-review` module with a redacted narrative, also
   always review-gated.

There is also a deterministic **ops worklist export** (`domain/ops_export.py`) in the shared
cross-repo contract shape, validated against `schema/ops_worklist_export.schema.json`.

### Which lifecycles ship?

Two tracks, as DATA rather than code paths (`domain/workflows.py`): **card scheme** (banking
chargebacks, with representment, pre-arbitration and arbitration) and **retail** buyer disputes
(refund-oriented and shorter). A deployment adds a third by appending a definition and registering
it, never by editing the state machine.

### What is deterministic vs done by the model?

Deterministic, pure stdlib, unit-tested and replayable: reason-code eligibility
(`domain/eligibility_engine.py`), the refund-abuse score, bands and outcome
(`domain/abuse_engine.py`), transition legality and lifecycle replay
(`domain/state_machine.py`), the clocks and deadlines (`domain/workflows.py` plus the case
engine), the severity, the `Decision` and the escalation itself
(`domain/dispute_service.py`), and the worklist export.

The model has exactly two jobs, both behind `ports/narration.py`: classify an intake into the
closed category set, and narrate a draft over facts the engine already fixed. It may restate
facts; it may never add one. Note the honest caveat: the managed narration adapter is not wired
yet (it initialises Vertex AI and raises), so everything the gate, the demo and the eval exercise
runs on the deterministic local narrator. See [`../model-card.md`](../model-card.md).

### Is anything auto-approved? Does it close a dispute or move money?

No. Every consequential outcome sets `requires_human_review` AND is ROUTED to the `human-review-console` in
the same call that produced it (rule R8), with the payload redacted before the wire and the
verified principal threaded as maker; a CRITICAL band demands two approvals. The response carries
a `review_ref`, so a caller can tell a routed escalation from one that stopped here, and the
managed router REFUSES when no console is configured rather than swallowing the escalation.
Representment packs and regulator drafts are marked draft and never sent. The agent proposes; a
human disposes.

### How many surfaces are there, and do they behave the same?

Five, and they share the domain service rather than reimplementing it: the FastAPI app
(`/v1/disputes/open`, `/v1/disputes/abuse`, `/v1/intake`, `/v1/disputes/representment`,
`/v1/disputes/regulator`), the argparse CLI (`open`, `abuse`, `intake`), the agent tools
(`open_dispute`, `assess_refund_abuse`, `classify_intake`, `verify_audit_trail`, advertised on the
A2A card at `/.well-known/agent-card.json`), the embeddable `ui/` micro-frontend, and the eval
harness. Each routes an escalated result in the same call that produced it, so rule R8 does not
hold on four surfaces out of five. `tests/unit/test_review_routing.py` asserts the routing rather
than the flag.

Agent tool results are additionally masked for personal data before they return, which an API
response to the caller who supplied the text is not: a tool result becomes a model's context, and
principle P-04 is about what reaches the model.

### Which capabilities does this repo own vs integrate from the catalog?

It **owns** the dispute lifecycle domain logic and its artifacts. It **integrates** cross-cutting
concerns owned by sibling systems, and a fork should not rebuild them. The honest state today:

| Concern | Owner | State here |
|---|---|---|
| Human-review and maker-checker console | `human-review-console` | Integrated. `ports/review_router.py`, adapter in every profile, `HUMAN_REVIEW_URL`. |
| Case spine (cases, states, clocks) | `human-review-console` | Integrated. `ports/case_engine.py` against `/v1/cases` at `CASE_URL`; the offline adapter computes the same deadlines. |
| Regulator-response drafting for a complaint | `complaints-review` | Integrated. `ports/regulator_response.py` calls `complaints-review`'s A2A tools at `DOC6_A2A_URL` and refuses when unset. |
| Tracing and the shared observability sink | `agent-observability` | Partly. Spans go OTLP to the `agent-observability` collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; the audit record does not land in the shared sink yet (rule R2). |
| AI-quality and promotion gate | `model-quality-gate` | Partly. `eval/run_eval.py --mode gate` is the client half; the metric bundle is not registered with `model-quality-gate` yet. |
| Agent registry, versioning, entitlements | `agent-registry` | Partly. The A2A card is published; nothing registers it. |
| Prompt-injection defence, output filtering | `agent-guardrail-gateway` | Not integrated. No `GuardrailPort` exists (rule R1). |
| Governed retrieval with citations | `enterprise-knowledge-base` | Not integrated. No retrieval port and nothing grounded against a knowledge base. |
| Downstream ops worklist and handover | **F5**, with the shared contract owned by **F1** | This repo CONFORMS to the export contract and adds a `signal` extension that `consumer-duty-monitoring` reads. |

### Where does the dispute lifecycle stop being this repo's job?

At the console and at the scheme. F2 decides eligibility, scores abuse, drives the lifecycle
states and drafts the representment; a human in `human-review-console` approves or rejects, and posting to a card
scheme or a marketplace is an integration the adopter owns. F2 also does not do the conduct or
complaints investigation itself: a regulatory-track intake fails closed and is handed to `complaints-review`.

### How do I see it working?

`make demo` runs the presenter-paced walkthrough: it starts its own loopback server, narrates each
of the eight steps on your terminal (never on the page), waits for you, then ASSERTS the service
really reached the state the narration claimed. `make demo-selftest` is the same script headless
and unattended, `make demo-static` writes static audit-first HTML for screenshots, and
`make portability` runs the executable portability claim. Everything is offline, stdlib-only, with
no browser engine, no cloud and no API key, on obviously synthetic data.
