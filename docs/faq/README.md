# FAQ index

Answers to the questions different teams ask when evaluating, adopting or reviewing this
repository as a common base for a dispute and chargeback lifecycle service. Each file is written
for a specific audience; skim the one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec and security review | what the service processes, server-side identity, the exposure guard, PII redaction and its gaps, secrets, supply chain, the anchored audit chain, what is out of scope |
| [portability-faq.md](portability-faq.md) | Architecture, cloud and exit planning | the no-lock-in claim, the three profiles, how a sovereign or on-premises exit works, open-format export, what is honestly not portable |
| [features-faq.md](features-faq.md) | Product, ops and delivery | what the service produces, what is deterministic vs what the model touches, the five surfaces, and where this repo's responsibility stops |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | the rebrand script, taking upstream fixes, the extension touch lists, the policy numbers you own, whether the demo rots |
| [compliance-faq.md](compliance-faq.md) | Compliance, conduct and model risk | maker-checker, PII posture, auditability, residency enforcement, the eval and model-risk story, and every row still owed |

These FAQs deliberately do **not** re-document capabilities owned by sibling catalog systems.
Where a concern belongs to another repo (the guardrail gateway, the human-review console and case
spine, the knowledge base, the eval platform, the regulator-response module), the FAQ names the
owner and explains the boundary rather than duplicating it. See
[features-faq.md](features-faq.md) for the full "what this repo owns vs what it integrates" map,
and [`../ADOPTING.md`](../ADOPTING.md) section 5 for the honest wired-or-not column.
