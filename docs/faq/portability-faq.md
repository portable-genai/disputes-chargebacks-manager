# Portability FAQ

For architecture, cloud and exit-planning reviewers who want to know how real the "no lock-in"
claim is and how an off-cloud or sovereign exit would work. Cross-references:
[`../onprem-migration.md`](../onprem-migration.md),
[`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).

## What is the no-lock-in claim, concretely?

`src/disputes_chargebacks_manager/domain/` is pure standard library plus the stdlib-only commons:
no web framework, no cloud SDK, no HTTP client. Every boundary is a `@runtime_checkable`
`Protocol` in `ports/`, re-exported once from `ports/__init__.py` with the `PORT_PROTOCOLS` map,
and every adapter is selected by one setting. `tests/unit/test_core_purity.py` is the standing
gate on the domain's import surface.

## What are the three profiles?

`DISPUTES_PROFILE` selects the whole adapter stack for all ten registered ports (`audit`,
`identity`, `review_router`, `case_engine`, `document_extraction`, `conversation_channel`,
`regulator_response`, `narration`, `tracer`, `evaluation`):

- **`local`** is a real, working, SDK-free offline stack: hash-chained anchored WORM audit, seeded
  dev personas, a deterministic case recorder that computes the same deadlines from the same
  `ClockSpec` data, a scripted intake channel, a stdlib evidence parser, a deterministic narrator
  and a review outbox that actually enqueues. This is the dev, test, CI and demo default and the
  working proof that the domain runs entirely off-cloud.
- **`gcp`** is the managed stack: Cloud Logging WORM, IAP identity, Hrz7 over S2S for reviews and
  the case spine, Doc6 over A2A, Document AI, Dialogflow CX, Vertex AI, OpenTelemetry. Every cloud
  import is LAZY, inside the method, so the other two profiles import these modules with no SDK
  installed.
- **`onprem`** is the exit scaffold: placeholders that satisfy the same Protocols and RAISE
  `NotImplementedError` naming the client-hosted component to bind. Tracing is the one deliberate
  exception: `OnPremTracerAdapter` satisfies the port and records nothing, because tracing carries
  no compliance claim and forcing an operator to bind a trace backend before the service will
  serve a request is a portability barrier invented for a diagnostic.

Unset is a fourth state rather than a silent `local`: the offline adapters still bind, but the
seeded personas are refused, no service-to-service scheme is selected and the exposure guard
refuses every non-loopback peer. Set-and-empty and set-and-unknown both raise AT IMPORT.

## Is the portability claim tested, or just asserted?

Tested and bounded. `make portability` (`scripts/portability_demo.py`) runs eight named checks
offline and exits non-zero on any failure: port map complete, adapters construct and conform,
offline family answers, exit family refuses, rewrite detected, truncation detected when anchored,
record leaves intact, no cloud SDK imported. It also PRINTS what it does not prove. The contract
suite carries the same claim into `make gate`: `tests/contract/test_port_parity.py` asserts set
equality across all FIVE homes of a port (`PORT_PROTOCOLS`, `DEFAULT_BINDINGS`, the `Container`
accessor, `config/settings.yaml`, the canonical-call table) and that every Protocol member is
declared on each adapter class; `tests/contract/test_behavioral_parity.py` proves the offline
family ANSWERS, the exit family RAISES and the managed family REFUSES rather than silently
succeeding.

## How is the "no cloud SDK" claim proved, given the SDK is simply absent from the machine?

By BLOCKING the import in a fresh interpreter (`tests/contract/_sdk_free_probe.py`), not by the
SDK happening not to be installed. That is the difference between a claim and a coincidence.

## How would a sovereign or on-premises exit actually go?

Each `adapters/onprem/*` placeholder marks a seam where a client supplies their own component:
their audit store, their IdP, their case system, their contact-centre channel, their
document-understanding stack, their model gateway, their review console. Because the domain never
changes, the exit is an adapter exercise rather than a rewrite. The placeholders RAISE rather than
returning empty results, which is deliberate: a review router that silently returned would convert
every consequential result into an unreviewed one, and an extractor that returned empty fields
would be read downstream as "no evidence". See
[`../onprem-migration.md`](../onprem-migration.md) for the migration guide and
[`../runbook.md`](../runbook.md) for operations.

## Can the data be exported in an open format?

Yes. The audit trail exports to and restores from self-describing JSON Lines: one anchor header
naming the chain head, then one record per line each carrying its `entry_hash`. The portability
check reloads the export into a foreign store and re-verifies the chain, so the exit is a file
copy rather than a migration project. The ops worklist export is a separate open contract
(`domain/ops_export.py`) validated against `schema/ops_worklist_export.schema.json`.

## How is data residency handled?

One region, chosen once and shared. `region:` in `config/settings.yaml` (default
`asia-southeast1`) is what the runtime reports on `/healthz` and prints on the agent card;
Terraform takes `var.region` and validates it against `var.allowed_regions` at PLAN time, so an
unapproved region fails before anything is created. On top of that: a `gcp.resourceLocations` Org
Policy allowlist pinned to the selected region's location group, a REGIONAL CMEK key ring (never
global or multi-region) with 90-day rotation, a regional WORM log bucket, and a dry-run-first
VPC-SC perimeter. A second region is a tfvars change plus a residency review, not a fork.

## What is honestly NOT portable, or not yet real?

- The managed narration adapter initialises Vertex AI and then raises: no model is wired, so the
  "the model narrates" half of the pipeline runs only on the deterministic local narrator today.
  See [`../model-card.md`](../model-card.md).
- The managed Document AI and Dialogflow CX calls are call-shape scaffolding rather than
  deployment-ready wiring (same file).
- `portability_demo.py` proves nothing about the managed profile's live behaviour, which needs a
  cloud project and lives in `tests/integration/`; it does not prove that an on-premises
  deployment exists, nor anything about infrastructure, model, network or whole-system
  portability.
- Production tamper evidence in the managed profile is the locked Cloud Logging bucket's job, not
  the hash chain's. The chain plus anchor is the offline stand-in with its limits written down.
