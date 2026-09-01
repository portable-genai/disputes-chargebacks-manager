# Adoption FAQ

For an engineering lead forking this repo as their institution's dispute and chargeback base. The
step-by-step is [`../ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?"
questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites the python package (`disputes_chargebacks_manager`), the
console-script name (the same token in this base, because `[project.scripts]` names the package),
the `DISPUTES` env prefix, the Terraform `name_prefix` stem (`f2-svc`) and the distribution id
(`disputes-chargebacks-manager`) in ONE simultaneous pass over each file, so no rule can
rewrite another rule's output. Preview with `--dry-run`, apply with `--yes`, add `--include-docs`
to sweep the Markdown too. Then recreate the venv, `make install`, and run `make gate` and
`make docs-check`. The script does the mechanical rename; the human decisions (region, IdP, the
policy numbers, fixtures, the eval golden set) are the checklist in `ADOPTING.md`.

### If several institutions fork this, how does each take upstream fixes?

Track upstream by git tag and rebase, rather than merging `main` continuously. The repo declares a
core-vs-adopter-owned boundary ([`../ADOPTING.md`](../ADOPTING.md) section 2): upstream owns
`domain/kernel.py`, `ports/`, `tests/contract/`, the `Container` wiring, the redacting review
payload converter, the eval harness mechanics and CI; you own the settings and policy VALUES, the
artifact models and engines, the workflows, `adapters/onprem/*`, the fixtures, the golden set and
the jurisdiction rows in `COMPLIANCE.md`. Conflicts then stay in files you were told to expect.

### Is there a separate kernel module I keep untouched?

Yes, and the direction is enforced. `domain/kernel.py` holds the vertical-neutral machinery
(`Severity`, `Decision`, `Citation`, `AuditEvent`, `utcnow`, `parse_date`); `domain/models.py`
holds this vertical's artifacts and imports `kernel`, never the reverse. A fork building a
different ops vertical rewrites `models.py` and the engines and leaves `kernel.py` alone
(practices check A7).

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list and a contract test enforces it in BOTH directions. A port must be
registered in FIVE places or it runs with no enforcement at all: `ports/__init__.py`
(`PORT_PROTOCOLS`), `config.DEFAULT_BINDINGS`, a `Container` accessor, `config/settings.yaml`, and
a `PortCase` in `tests/contract/canonical.py`. Then bind it in all three families.
`tests/contract/test_port_parity.py` asserts set equality across the five, so a bound but
unregistered port fails the build rather than running untested. Full walkthrough in
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).

### How do I add a new adapter?

The class under `adapters/<family>/` with the one constructor shape `Adapter(settings)` and cloud
imports INSIDE the method, the same `module:Class` target in `config.DEFAULT_BINDINGS` AND
`config/settings.yaml` (`tests/unit/test_settings_file.py` fails if the two disagree), plus any
new variable in `.env.example`. The lazy-import rule is proved by BLOCKING the import in a fresh
interpreter, not by the SDK being absent.

### How do I change the taxonomy (tracks, states, categories, outcomes)?

`DisputeTrack`, `DisputeState`, `IntakeCategory` and `AbuseOutcome` are `LenientStrEnum`s from the
commons, so a member IS its wire value and an unknown value from a future release does not crash
the reader. Extend or replace them in `domain/models.py`. A new lifecycle is a new
`WorkflowDefinition` in `domain/workflows.py` plus its registration; the state machine reads the
definition and needs no edit. Remember the closed intake set is what the model is allowed to
choose from: widening it widens the model's reach.

### Can I retune the policy numbers without touching code?

Yes, for the two that matter most. `config/policy_packs.yaml` carries the reason-code packs (per
track and code: `filing_window_days`, `response_deadline_days`, `evidence_required`) and the
`abuse_policy` thresholds, points and bands; `config.load_policy` reads the file, and
`domain/policy_defaults.py` mirrors it as the shipped default with
`tests/unit/test_policy_packs.py` drift-guarding the two and validating the file shape. Change
both together and add a test that pins YOUR values. The lifecycle clock days
(`domain/workflows.py`), the jurisdiction list (`domain/pii.py`) and the eval bars
(`eval/run_eval.py` `THRESHOLDS`) are still code-level and are the next things to lift if your
compliance function must own them as configuration.

### What must I replace before running against anything real?

Every fixture and transcript: `tests/fixtures/sample_cases.py`, the scripted conversations in
`adapters/local/conversation_channel.py`, and `eval/datasets/golden_cases.jsonl`. All parties are
obviously fictional and the one national id in the fixtures exists solely so the redaction check
has an independent literal to look for. Rebuild the golden set for your scheme rules too: a fork
inherits a green gate that measures the WRONG ruleset until you do.

### Will the demo rot after I diverge?

It is guarded from inside the gate. A step exists in exactly two places (`demo.STEPS` and
`walkthrough.CHECKS`) and `tests/unit/test_demo_surface.py` holds the two equal, drives the whole
arc against the real local adapters, and asserts the tamper step actually goes red. The same
README index test fails if a script in `scripts/` stops being listed. `make demo-selftest` runs
the arc headless. Keep the pattern when you add a step: put the numbers a check reads in the
step's `facts` dict, never only in the rendered prose, because a check that parses prose breaks on
a wording change.

### Does the gate run for my fork out of the box?

`make gate` does, immediately: it is offline, SDK-free and credential-free (ruff, `ruff format
--check`, `mypy src`, `pytest -m 'not integration'`, then the eval smoke run), and nothing in it
needs a cloud project or a network. `make audit` is the one step that needs a vulnerability feed
and is deliberately separate. Note two things about the shipped CI: the hosted Cloud Build check is
a thin caller of a shared reusable hard-gate workflow pinned to a tag of the template repository,
so a fork either keeps access to that repository or inlines the workflow; and nothing in the
offline gate runs `terraform test`, so `infra/terraform/production_edge.tftest.hcl` is a set of
plan-time posture assertions you must run deliberately.

### What is the versioning story?

`pyproject.toml` carries the version, and you track upstream by git tag. The practice that would
require a hand-maintained release narrative is retired fleet-wide (see the G4 row in
[`../practices-audit.md`](../practices-audit.md)): a tag and a version bump already state what a
narrative would restate, and the two drift the moment anyone forgets one of them. If your
institution needs one, starting it at your fork point is an adoption step.
