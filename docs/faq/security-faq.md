# Security FAQ

For an AppSec reviewer sizing up this repo. It explains what the attack surface is, what is
deliberately out of scope, where the evidence lives, and which controls are honestly still owed.
Cross-references: [`../../COMPLIANCE.md`](../../COMPLIANCE.md),
[`../practices-audit.md`](../practices-audit.md).

## What does this system actually process?

Dispute and chargeback records: a dispute id, a tenant, a track (card scheme or retail), a reason
code, an amount in integer minor units, a currency, transaction and intake dates, optional
product, market, channel, customer and merchant references and a free-text narrative
(`domain/models.py::Dispute`). It also reads intake conversation transcripts through the
conversation-channel port and chargeback-evidence documents through the document-extraction port.
So unlike a planning service, this one DOES have a personal-data surface, and the redaction
controls below are load-bearing rather than declared not-applicable.

## How is identity handled? Can a caller spoof the actor?

No. The request models in `api/schemas.py` carry no actor field; the audit actor and the review
maker are both the server-resolved `Principal`. Which adapter resolves it is the profile's choice:

- `local` resolves a seeded dev persona from `X-Dev-Persona`, and REFUSES to construct at all
  unless `DISPUTES_PROFILE=local` was set deliberately rather than inherited from an absent
  variable.
- `gcp` verifies the IAP-injected assertion with `id_token.verify_token`, passing the configured
  `DISPUTES_IAP_AUDIENCE` and IAP's own key set (not google-auth's OAuth2 default), and checking
  the issuer itself because `verify_token` does not. An unset or emptied audience refuses every
  caller, because `audience=None` means the audience is not verified at all.
- `onprem` is a client-IdP placeholder that raises.

`tests/unit/test_iap_identity.py` runs in every `make gate`, and
`tests/unit/test_iap_crypto_matrix.py` runs the REAL verifier over locally minted assertions in
the `iap-verifier` job, which fails if it skips.

## What stops the service being served to the network with no authentication?

A loopback exposure guard bound at MODULE scope in `api/app.py`, so it runs in the shipped process
(the Dockerfile `CMD` and `make run-api` serve the app object, and a bound that lived only in
`main()` would never run). Its posture is derived from the IDENTITY BINDING: an end-user route is
open only when the bound adapter declares it can produce a verified principal without trusting a
client-written header (`ports/identity.py`: `VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`,
defaulting to client-asserted when silent). `DISPUTES_S2S_TOKEN` takes no part in that decision:
it authenticates a calling SERVICE and no end user, and setting it closes the S2S routes without
relaxing anything else. `tests/unit/test_serving_path_exposure.py` and
`tests/unit/test_end_user_auth_posture.py` are the standing gates. `/docs`, `/redoc` and
`/openapi.json` are REGISTERED only under a deliberate `local` exposure profile, so an
uncredentialed peer on a fronted deployment does not receive the route inventory.

## Where is PII redacted, and where is it not?

Redacted, with the shared `pii-kit` and this deployment's jurisdiction row selection
(`domain/pii.py`):

- before every audit write (`DisputeService._record` redacts the summary);
- before the intake transcript reaches the narration port, and on the citation snippet the intake
  path keeps;
- before the dispute narrative reaches the Doc6 regulator-response module;
- before any review payload leaves the process, against EVERY jurisdiction's rows rather than only
  this deployment's, because the Hrz7 console is a shared sink
  (`adapters/_review_payload.py`);
- on every string of an agent tool result, however deeply nested, because a tool result becomes a
  model's context (`agent/tools.py`).

Not redacted today, and this is the honest gap: `DisputeService.draft_representment` hands the
extracted evidence fields and the dispute facts to the narration port unredacted, and the local
extractor's raw line snippets travel on the `Citation` set into the audit record's citation list
(only `redacted_summary` is masked, not `citations`). See the last section of
[`../model-card.md`](../model-card.md).

## Is the safety metric real, or can it be quietly disarmed?

Real, and it is scored two ways. `eval/run_eval.py::pii_clean_score` runs the shared pack scan AND
an independent planted-literal check, so a broken pack row cannot silently pass the metric.
`tests/unit/test_not_falsely_green.py` proves the metric can go red, and the eval harness calls
`agent_eval_kit.assert_each_can_go_red` before scoring: a metric that cannot fail proves nothing.

## What about outbound service-to-service calls?

Three, all plain stdlib `urllib` rather than a cloud SDK: the Hrz7 review submission and the Hrz7
case spine, and the Doc6 A2A regulator-response call. The review path uses the shared
`review-kit` client, which refuses a plaintext non-loopback URL and a missing bearer at
construction. Outbound credentials (`HUMAN_REVIEW_S2S_TOKEN`, `HUMAN_REVIEW_S2S_SIGNING_KEY`) are deliberately
distinct variables from the inbound `DISPUTES_S2S_TOKEN`. Each managed adapter REFUSES when its
endpoint is unset rather than silently succeeding.

## Are there secrets in the repo?

No secret value. `config/settings.yaml` and `.env.example` hold variable NAMES and non-secret
defaults; `.env.secrets.example` holds placeholders; `.gitignore` excludes the real files. In
Terraform, `var.additional_secret_env` maps an environment variable name to an existing Secret
Manager secret pinned to an exact numeric version, and names this stack sets itself are reserved
so a secret cannot shadow the residency, identity or routing wiring.

## Does an emptied environment variable fall back to the permissive default?

No, and that rule is enforced in both languages. Every security-relevant read resolves three
states (unset, set-and-empty, set-and-valid). `tests/unit/test_three_state_env_reads.py` walks the
AST of `src/`, `scripts/` and `eval/` and fails the build on any two-state `os.environ.get` or
`os.getenv` read that is neither an exact-match comparison nor listed with a written reason;
`ui/tests/three-state-env-reads.test.mjs` applies the same rule to every shipped `.mjs`, `.ts` and
`.tsx` in `ui/`.

## What is the browser boundary worth?

`ui/` never asserts identity. Every client-supplied actor, tenant, role, ACL and authorization
header is discarded before forwarding (`ui/lib/embed-policy.mjs`), identity is resolved
server-side (`ui/lib/server/identity.ts`), and the service credential is read from the server
environment so it never reaches a bundle. Framing and CORS are per-tenant allowlists that refuse a
wildcard however it is written, and `UI_FRAME_ANCESTORS` / `UI_TENANT_ORIGINS` refuse from
`next.config.mjs`, so an emptied allowlist is a boot refusal rather than a surprise on a later
request. Run `make drop-ui` if your fork has no user-facing surface;
`tests/unit/test_ui_surface.py` holds the repo consistent in both directions.

## Is the audit trail tamper-evident?

Yes, with a stated limit closed. The local sink is append-only and hash-chained AND externally
anchored: `audit_anchor_path` (`DISPUTES_AUDIT_ANCHOR`) points at a file on a different volume
that every append writes the chain head to. The chain alone catches an edit, a deletion or a
reorder; only the anchor catches a truncated tail, because a shorter chain still verifies. Once
store and anchor disagree the service refuses to append rather than re-anchoring.
`tests/unit/test_audit_anchor.py` proves both halves plus the control case that goes undetected
without an anchor. In the managed profile the trail is a locked Cloud Logging WORM bucket
(`infra/terraform/logging_worm.tf`), which provides non-rewritability itself.

## What is the supply-chain posture?

Committed `requirements-dev.lock` and `requirements-gcp.lock`, installed with `--no-deps` by
`make install`, CI and the Dockerfile, with the four catalog commons pinned to 40-character COMMIT
shas rather than tags (a tag can be moved, so a tag pin lets what installs change with no diff);
a digest-pinned non-root base image; SHA-pinned Actions; dependabot per ecosystem; `pip-audit`
over both locks and `npm audit --audit-level=high` as hard failures.
`tests/unit/test_repo_artifacts.py` asserts each of these from inside the offline gate.

## What is explicitly out of scope for this repo?

- **Prompt-injection defence and output filtering** at the model boundary: **Hrz1**. There is no
  `GuardrailPort` here yet, and an intake transcript is untrusted text (COMPLIANCE rule R1).
- **The WORM audit store and the shared trace sink**: **Hrz5**. The tracer port exports OTLP to
  the Hrz5 collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, but the audit record itself does
  not yet land in the shared sink (rule R2).
- **The human-review console and the case spine**: **Hrz7**. This repo produces and routes; it
  does not implement the console.
- **The agent registry** (**Hrz3**), **the promotion gate** (**Hrz4**), **the knowledge base**
  (**Hrz2**) and **regulator-response drafting** (**Doc6**).
- **Object-level authorisation and per-tenant data-tag isolation**: not built, because this
  service has no queryable store yet. The tenant partition is carried on every outbound review.
  Add ACL matchers with the first store (COMPLIANCE cross-cutting row, practices check C2).
- **Resilience controls**: timeouts, a circuit breaker and a documented kill switch per outbound
  dependency are not implemented (COMPLIANCE P-10). The review path degrades correctly (the
  offline outbox retains an escalation the console could not take); nothing else does.
