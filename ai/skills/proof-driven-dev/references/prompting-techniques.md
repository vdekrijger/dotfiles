# Pro Prompting Techniques

Adversarial/critical-thinking techniques for stress-testing decisions, designs, and implementations. Three are mandatory pipeline passes (defined in SKILL.md):

| Technique | Phase | What it does |
|---|---|---|
| **Inverse questioning** | 1 (Brainstorm) | "What's the strongest argument against this approach?" |
| **Challenge criteria** | 2 (Criteria) | "What assumptions could be wrong? What edge cases are we ignoring?" |
| **Adversarial verification** | 5 (Verify) | "If this were broken despite all tests passing, where would the bug hide?" |

## Ad-hoc Techniques

Not formal pipeline phases — apply when you hit ambiguous decisions or unexpectedly complex problems.

**Pre-mortem** — "Imagine this shipped and customers are filing bugs. What's the root cause?" Catches optimistic assumptions before they become production incidents.

**Steel-man alternatives** — Before dismissing a rejected approach, make the strongest possible case for it. If the case is genuinely weak after steel-manning, dismiss with confidence. If it surfaces something your chosen approach misses, reconsider.

**Constraint relaxation** — "What could we build if we removed constraint X?" Useful when a design feels forced — sometimes the constraint is self-imposed or outdated.

**Confidence calibration** — After making a claim ("this will handle 10k RPS"), ask: "How confident am I in this? What evidence supports it? What would prove me wrong?" Record the confidence level and evidence gap in the spec.

**Recursive decomposition** — When a task feels overwhelming or context won't fit, ask: "What's the smallest independent piece of this I can build and verify?" Repeat until atomic.

**Rubber-duck inversion** — Explain why the code works correctly, then explain why it might not. The gap between the two explanations is where bugs live.
