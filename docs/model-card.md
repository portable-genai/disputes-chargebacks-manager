# Model card: Disputes and Chargebacks Manager (F2)

This is a STARTER model card. It records the model boundary as built and the controls that must be
completed before a managed deployment. The deterministic engines are the system of record; the
model is a bounded, replaceable component that touches exactly two ports.

## What the model does, and does not do

- **Does** (both behind `ports/narration.py`): classify one intake conversation into the CLOSED
  `IntakeCategory` set (`domain/models.py`), and narrate a representment draft over facts an
  engine already fixed (`DisputeService.draft_representment`). A third port,
  `ports/document_extraction.py`, is a managed document-understanding edge rather than a
  generative one: it lifts labelled fields out of an evidence document, and the engine, never the
  extractor, decides what those fields mean.
- **Does NOT**: produce any number or verdict. Reason-code eligibility
  (`domain/eligibility_engine.py`), the refund-abuse score, band and outcome
  (`domain/abuse_engine.py`), lifecycle legality and the states a trigger sequence reaches
  (`domain/state_machine.py` over `domain/workflows.py`), the case deadlines, the severity, the
  `Decision` and the escalation itself (`domain/dispute_service.py`) are all pure stdlib and
  replayable. A classification outside the closed set, or an empty label, never opens a lifecycle
  case: it fails closed to human review.
- **Does not exist yet in the managed profile.** `adapters/gcp/narration.py` initialises Vertex AI
  and then raises `RuntimeError` from both `classify` and `narrate`: no model id is pinned, no
  prompt is written, and no live generation runs anywhere in this repo today. Everything the
  offline gate, the demo and the eval exercise is the deterministic `local` narrator.

## Boundary and validation

- The intake transcript is redacted with `pii-kit` BEFORE it reaches the narration port:
  `DisputeService.intake` calls `redact(transcript, PII_PATTERNS)` on the way in and redacts the
  citation snippet it keeps.
- The classifier's output is validated against the closed category list. `""` and any label
  outside `_INTAKE_CATEGORIES` are coerced to `IntakeCategory.UNKNOWN`, which routes to human
  review rather than opening a case. The model cannot invent a label that reaches the
  deterministic path.
- The narrator is fed a `facts` tuple and instructed to restate it. Groundedness is scored, not
  assumed: `eval/run_eval.py` `grounded_score` fails any draft carrying a digit run absent from
  the engine-sourced facts and the cited evidence, at a `0.99` bar.
- Every representment pack and every regulator draft sets `requires_human_review=True` and carries
  its citations; nothing auto-posts. Consequential dispositions are ROUTED to Hrz7 in the same call
  that produced them (rule R8), never left in a flag.
- `pii_safety` is scored two ways (the shared pack scan plus an independent planted-literal
  oracle) at a `0.99` bar, and `tests/unit/test_not_falsely_green.py` proves the metric can go red.

## Adapters and profiles

| Profile | Narration adapter | Document extraction adapter | Conversation channel adapter | Behaviour |
|---|---|---|---|---|
| `local` | `adapters/local/narration.py` | `adapters/local/document_extraction.py` | `adapters/local/conversation_channel.py` | SDK-free and deterministic. `LocalNarrator.classify` maps an ordered keyword table to one label from the supplied closed set and returns `""` when nothing matches; `narrate` templates the facts into one sentence and adds nothing. `LocalDocumentExtractor` parses `key: value` lines and cites each back to its line number. `LocalConversationChannel` returns scripted fictional turns. This is the profile the gate, the demo and the eval run. |
| `gcp` | `adapters/gcp/narration.py` | `adapters/gcp/document_extraction.py` | `adapters/gcp/conversation_channel.py` | Lazy SDK imports, so the other two profiles import these modules with no cloud SDK present. `CloudNarrator` initialises `google.cloud.aiplatform` at `settings.region` and then RAISES: the live path is not wired. `CloudDocumentExtractor` builds a Document AI `RawDocument` and calls `process_document`. `CloudConversationChannel` calls Dialogflow CX. Both cloud edges are call-shape scaffolding, not deployment-ready wiring (see below). |
| `onprem` | `adapters/onprem/narration.py` | `adapters/onprem/document_extraction.py` | `adapters/onprem/conversation_channel.py` | Fail-fast placeholders. Each raises `NotImplementedError` naming the client-hosted component to bind (a model gateway, a document-understanding stack, a contact-centre channel) rather than returning a blank string or empty fields a downstream engine would read as evidence. |

The `local` and `onprem` behaviours are held to the wall by
`tests/contract/test_behavioral_parity.py`: the offline family must ANSWER and the exit family must
RAISE, so a placeholder that quietly started returning something would fail the build.

## Remaining controls (TODO, repo owner)

- **Pin a model, write the prompts, and finish the managed narration adapter** (P-07, P-11).
  `adapters/gcp/narration.py` raises today. Record the exact model id and version here when it is
  wired. `eval/run_eval.py` names `gemini-2.5-flash` to the Hrz4 promotion client in `--mode gate`;
  that string is the promotion request's declaration, not a model this repo calls.
- **Finish the managed document-extraction call.** `CloudDocumentExtractor.extract_raw` builds a
  `ProcessRequest` with no processor resource name, so it cannot succeed against a live Document
  AI project as written; it also returns `citations=()`, losing the per-field provenance the local
  adapter produces. Supply the processor name from settings and carry citations through.
- **Finish the managed conversation-channel read.** `CloudConversationChannel.fetch_turns` calls
  `SessionsClient.get_session_entity_type` and maps the returned entities to turns, which is a
  placeholder shape rather than a transcript read. Bind the real transcript source before the
  intake path is used on the managed profile.
- **Extend redaction to the representment path** (P-04). The intake transcript is redacted before
  the narration port, but `DisputeService.draft_representment` passes the extracted evidence fields
  and the dispute facts to `narrate` unredacted, and the extractor's raw line snippets travel on
  the `Citation` set into the audit record's citation list. Redact the fact tuple and the snippets
  before they cross either boundary, as the review payload converter already does.
- **Prompt-injection screening** (rule R1). There is no `GuardrailPort` in `ports/`. An intake
  transcript is untrusted text; screen it through the Hrz1 gateway before the model sees it, and
  fail closed to deterministic-only when the screen is unavailable.
- **Budget, rate and kill switch** (P-10, P-11): a per-tenant token budget, a request rate limit,
  and a switch that forces deterministic-only operation with the model disabled.
- **Evaluate the live model** (P-08, rule R5). The offline eval scores the deterministic local
  narrator against the golden oracle. Register the metric bundle with Hrz4 and add a
  managed-profile run that scores real classification accuracy and real narration groundedness
  against the same golden cases.

Until these are complete the system is safe to run offline (deterministic engines plus the
deterministic local narrator) and the managed model path is not production-cleared. See
[`../COMPLIANCE.md`](../COMPLIANCE.md) for the full principle map and
[`practices-audit.md`](practices-audit.md) for the per-check verdicts.
