# Adopting this repo as your base

This repository (F2, the Disputes and Chargebacks Manager) is a **common base** that a bank,
an acquirer, a payment service provider or a marketplace forks to build its own **dispute and
chargeback lifecycle service**: deterministic reason-code eligibility, a case lifecycle with
regulatory clocks, deterministic refund-abuse decisioning, in-channel intake classification and
an evidence-backed representment draft, all of it review-gated. It ships a reusable hexagonal
core (a pure-stdlib domain, typed ports, three swappable adapter profiles, a green offline gate)
plus a fully worked two-track vertical (card-scheme chargebacks and retail buyer disputes) that
you can keep, retune, or replace with your own scheme rules.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the layout, the port table and the
> request pipeline), [`CONTRIBUTING.md`](../CONTRIBUTING.md) (the file-by-file touch list for a
> new adapter and a new port), [`COMPLIANCE.md`](../COMPLIANCE.md) (the principle and rule map
> with its open rows), the [`faq/`](faq/) directory, and [`model-card.md`](model-card.md) for the
> model boundary.

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and this dispute vertical is a
physical module split with an enforced dependency direction (practices-audit check A7).
`domain/kernel.py` holds the vertical-neutral machinery and imports nothing from the vertical;
`domain/models.py` imports `kernel`, never the reverse. A fork building a different ops vertical
rewrites `models.py` and leaves `kernel.py` alone.

| Layer | Where | For a new vertical or scheme |
|---|---|---|
| **Kernel** (vertical-neutral) | `domain/kernel.py` (`Severity`, `Decision`, `Citation`, `AuditEvent`, `utcnow`, `parse_date`), every Protocol in `ports/` plus `ports/identity.py`, the `Settings` and `Container` wiring in `config.py`, the redacting review conversion in `adapters/_review_payload.py` | keep untouched |
| **Policy** (your numbers) | the reason-code packs and the refund-abuse thresholds in `config/policy_packs.yaml` (mirrored as the shipped default in `domain/policy_defaults.py`), the clock days in `domain/workflows.py`, the jurisdiction list in `domain/pii.py`, the metric bars in `eval/run_eval.py` `THRESHOLDS` | change deliberately (see section 4) |
| **Vertical** (the dispute artifacts) | the artifact models in `domain/models.py` (`Dispute`, `DisputeTrack`, `DisputeState`, `IntakeCategory`, `AbuseOutcome`, `CaseHandle`, `EligibilityOutcome`, `AbuseAssessment`, `IntakeClassification`, `ExtractedEvidence`, `RepresentmentPack`, `RegulatorDraft`, `DisputeDisposition`), the four engines (`eligibility_engine.py`, `abuse_engine.py`, `state_machine.py`, `workflows.py`), the `dispute_service.py` orchestrator, the worklist contract in `domain/ops_export.py` with `schema/ops_worklist_export.schema.json`, the local fixtures and the eval golden set | rewrite or reseed for your data |

If your product is another *case-and-clock* ops vertical (claims, complaints, collections,
recoveries), most of the hexagon, the three profiles, the deterministic-verdict pattern, the
anchored audit chain, the eval gate and the Hrz7 review routing transfer directly; you replace
the artifact models, the workflows and the engines, and you retune the policy numbers.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): `domain/kernel.py`, `ports/`, `tests/contract/`, the
  `Container` wiring in `config.py`, `adapters/_review_payload.py`, the eval harness mechanics in
  `eval/run_eval.py`, `scripts/check_docs_links.py`, the CI workflows, and the whole `ui/`
  security boundary (`ui/lib/embed-policy.mjs`, `ui/lib/identity-policy.mjs`,
  `ui/lib/server/identity.ts`).
- **Adopter-owned** (yours; expect to edit): the *values* in `config/settings.yaml`, all of
  `config/policy_packs.yaml` and `domain/policy_defaults.py`, `domain/models.py` and the four
  engines, `domain/workflows.py`, `domain/pii.py` (`JURISDICTIONS`), `adapters/onprem/*`, the
  scripted intake conversations in `adapters/local/conversation_channel.py`,
  `tests/fixtures/sample_cases.py`, `eval/datasets/golden_cases.jsonl`, UI theming, the
  jurisdiction rows in `COMPLIANCE.md`, and `infra/terraform/terraform.tfvars.example`.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously, so conflicts stay in files you were told to expect.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the python package (`disputes_chargebacks_manager`), the
console-script name (also `disputes_chargebacks_manager`, because in this base the two are the
same token), the `DISPUTES` env-var prefix, the Terraform `name_prefix` stem (`f2-svc`) and the
distribution / git id (`disputes-chargebacks-manager`) in ONE simultaneous pass, so no rule
can rewrite another rule's output. Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_disputes --cli acme-disputes \
    --env-prefix ACME --resource acme-disputes --dry-run

# Apply, including the Markdown prose:
python scripts/rename_fork.py --package acme_disputes --cli acme-disputes \
    --env-prefix ACME --resource acme-disputes --include-docs --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
make docs-check
```

`--dist` defaults to the package name with hyphens; pass it explicitly if your git id differs
from the hyphenated package name. `--resource` must satisfy the
same `^[a-z][a-z0-9-]{2,18}$` rule the Terraform `name_prefix` variable validates at plan time, so
a bad value fails in the script rather than at `terraform plan`. Without `--include-docs` the
Markdown is left alone; the script deliberately does NOT touch the human decisions below.

## 4. The human decisions (the script cannot make these)

1. **Region and residency.** The region is chosen once and shared: `GCP_REGION` feeds the
   `region:` key in `config/settings.yaml`, and Terraform takes `var.region` validated against
   `var.allowed_regions` at plan time (`infra/terraform/variables.tf`). The build defaults to
   `asia-southeast1`. Set both to your in-country region, and if your organisation's policy
   evaluation covers the location-less global edge objects, list the value it expects in
   `var.additional_resource_locations` rather than widening the regional allowlist. See
   [`runbook.md`](runbook.md).
2. **Identity and IdP.** This repo owns no login flow. `local` resolves seeded dev personas from
   `X-Dev-Persona` and refuses to construct unless `DISPUTES_PROFILE=local` was set deliberately;
   `gcp` verifies the IAP-injected assertion against `DISPUTES_IAP_AUDIENCE` (three-state: unset
   or emptied refuses every caller); `onprem` raises. Wire your issuer ON the deployed service:
   set `var.edge_iap_enabled`, grant `var.iap_members`, apply once, read the `iap_audience`
   output, set `var.iap_audience` and apply again. Until that second apply the service starts,
   stays health-checkable and answers every end-user route with a 503 naming the variable.
3. **The policy numbers.** These are the client's numbers, not a vendor default to inherit
   unexamined, and they already live as data so you change them without a code edit:
   - `config/policy_packs.yaml` `reason_code_packs`: per track and per reason code, the
     `filing_window_days`, the `response_deadline_days` and the `evidence_required` list. The
     shipped card-scheme and retail codes are illustrative synthetic values, not any real scheme's
     rulebook. An unknown reason code is INELIGIBLE by design; keep that fail-closed default.
   - `config/policy_packs.yaml` `abuse_policy`: the velocity, amount and refund-total thresholds,
     the per-signal points, and the `review_at` / `deny_at` bands over the additive score.
   - `domain/workflows.py`: the `ClockSpec` days per track and which clocks are `regulatory`.
   - `domain/pii.py` `JURISDICTIONS`: which national-ID pattern rows the redactor runs, and in
     what order.
   `domain/policy_defaults.py` mirrors the YAML and `tests/unit/test_policy_packs.py` holds the
   two equal, so change both together and add a test that pins your values.
4. **Reference data is fictional.** Every party, transcript and identifier in
   `tests/fixtures/sample_cases.py`, the scripted conversations in
   `adapters/local/conversation_channel.py` and `eval/datasets/golden_cases.jsonl` is obviously
   synthetic, and the one national id in the fixtures exists solely so the redaction check has an
   independent literal to look for. Replace them with your own synthetic data. **Do not run
   against real dispute records without your own security, privacy and model-risk sign-off.**
5. **Eval golden set.** Rebuild `eval/datasets/golden_cases.jsonl` for your scheme rules and
   retune `THRESHOLDS` in `eval/run_eval.py`: a fork inherits a green gate that measures the WRONG
   ruleset until you do. The structure is generic (the deterministic metrics are held at 1.0, the
   classification metric lower, the safety metric at 0.99); the golden cases are yours. Register
   your own bundle name with Hrz4 before `--mode gate` has an authority to ask.
6. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001,
   `HEALTHCHECK` on `/healthz`) and `infra/terraform/`: the Org Policy guardrails
   (`var.enable_org_policies`), the regional CMEK ring, the dry-run-first VPC-SC perimeter
   (`var.enable_vpc_sc`, `var.vpc_sc_enforce`), the locked WORM log bucket
   (`var.worm_locked`, and note the lock is irreversible) and the loopback-by-default API bind.
   Decide the WORM retention (`var.retention_days`, minimum 180) before the first apply.
   `var.human_review_url` is REQUIRED once the serving edge is enabled, because the managed review
   router refuses rather than swallowing an escalation.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches* are
owned by sibling systems, and a fork should integrate rather than rebuild them. Be honest about
which are actually wired today: the table below matches the `adapters:` block in
`config/settings.yaml` and the R1 to R8 rows in [`COMPLIANCE.md`](../COMPLIANCE.md).

| Concern | Owned by | Wired here today? |
|---|---|---|
| Human review and maker-checker console | **Hrz7** | **Yes.** `ports/review_router.py` with an adapter in all three families; the managed one submits over S2S to `review_url` (`HUMAN_REVIEW_URL`) and REFUSES when no console is configured. Rule R8. |
| Case spine (cases, states, clocks) | **Hrz7** | **Yes.** `ports/case_engine.py`; the managed adapter drives `/v1/cases` at `case_url` (`CASE_URL`) and refuses when unset. The offline adapter computes the same deadlines from the same `ClockSpec` data. |
| Regulator-response drafting for a regulatory-track complaint | **Doc6** (`complaints-review`) | **Yes.** `ports/regulator_response.py`; the managed adapter calls Doc6's A2A tools at `doc6_url` (`DOC6_A2A_URL`) and refuses when unset, so a regulatory complaint cannot silently skip that module. |
| Tracing and the immutable audit sink | **Hrz5** | **Partly.** The tracer port is bound in all three families and the managed adapter exports OTLP to the Hrz5 collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (Cloud Trace when it is not). The audit half is still local (hash-chained and anchored) or Cloud Logging; COMPLIANCE rule R2 carries the open half. |
| AI-quality and promotion gate | **Hrz4** | **Partly.** `eval/run_eval.py --mode gate` is the client half and refuses to run off the managed profile, but this repo's metric bundle is not registered with Hrz4 yet (COMPLIANCE P-08 and R5). |
| Agent registry, versioning, entitlements | **Hrz3** | **Partly.** The A2A card is published at `/.well-known/agent-card.json` from the same tool table the runtime binds, but nothing registers it with Hrz3 or takes the agent's identity from it (COMPLIANCE R4). |
| Runtime guardrail: prompt-injection defence and output filtering | **Hrz1** | **No.** There is no `GuardrailPort` in `ports/`. The redaction this repo does own runs before the audit write, before the review payload and before a tool result returns, but injection defence at the model boundary is Hrz1's job and is an open TODO (COMPLIANCE R1). |
| Governed retrieval and citations over a knowledge base | **Hrz2** | **No.** There is no retrieval port and nothing is grounded against a knowledge base, so COMPLIANCE P-05 and R3 are honestly unclaimed. Add a `KnowledgeBasePort` bound to Hrz2, and make empty retrieval a hard error, before claiming either. |
| Project intake validation | **Rsk3** | **No.** An intake action rather than a code control (COMPLIANCE R6). |
| Marketing and financial-promotions claim check | **Mkt6** | **n/a.** This service produces no customer-facing marketing output. |

One cross-repo contract runs the other way: `domain/ops_export.py` builds rows in the shared
ops-worklist shape that F5 (the control-room handover) consumes, with a backward-compatible
`signal` extension that Rgc15 reads. Keep the schema in `schema/ops_worklist_export.schema.json`
in step with the builder if you change it; `tests/unit/test_ops_export.py` validates every built
document against it.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py --include-docs`, recreated the venv, `make gate` and `make docs-check` green.
- [ ] Set `GCP_REGION` and the Terraform `region` / `allowed_regions` to your in-country region.
- [ ] Wired your IdP on the deployed service and completed the two-pass `iap_audience` apply.
- [ ] Replaced the reason-code packs with your scheme rules in `config/policy_packs.yaml` and `domain/policy_defaults.py`, and pinned them with a test.
- [ ] Owned the refund-abuse thresholds and bands with your fraud and conduct functions.
- [ ] Reviewed the lifecycle clocks in `domain/workflows.py` against your regulatory deadlines.
- [ ] Set `JURISDICTIONS` in `domain/pii.py` to the markets this deployment serves.
- [ ] Replaced every synthetic fixture, transcript and golden case.
- [ ] Rebuilt the eval golden set and registered your metric bundle with Hrz4.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform toggles, WORM retention, bind address).
- [ ] Wired your Hrz7 review and case endpoints, and decided which other sibling systems you integrate vs stub.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
