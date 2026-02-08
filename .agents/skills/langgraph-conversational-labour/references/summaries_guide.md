# Status summaries guide (user-side + bot-side)

The scaffold maintains two summaries:

1) **User-facing status card** (Markdown appended to the assistant message)
2) **Bot memory object** (structured JSON stored in state and injected into prompts)

This achieves continuity without replaying full transcripts.

## 1) User-facing status card

Purpose:
- remind the user what is happening
- make next steps explicit
- reduce drift and forgetting

Recommended fields:
- goal (as currently understood)
- stage (intake/plan/execute/review or your domain phases)
- what we concluded this turn
- the next action we propose
- open questions (if any)
- how to correct the bot ("Say: 'update goal: ...'")

## 2) Bot memory object

Purpose:
- fast resumption of work
- stable state to condition analysis and action selection
- reproducible behaviour across turns

Recommended fields (domain-general):

```json
{
  "goal": "...",
  "stage": "intake|plan|execute|review",
  "constraints": ["..."],
  "commitments": ["..."],
  "facts": ["..."],
  "hypotheses": [{"text":"...","confidence":"low|medium|high","confirmed":false}],
  "signals": {"motivation": 3, "risk": 0, "clarity": 2},
  "open_questions": ["..."],
  "next_step": "...",
  "last_updated_utc": "2026-02-07T12:00:00Z"
}
```

## Update policy

This scaffold updates summaries **every turn** by default, without an extra LLM call:

- analysis node emits structured deltas (facts, hypotheses, open questions, signal updates)
- summary builder merges these into `status.*`

You can switch to:
- update only when something changes
- update every N turns
- LLM-based summarisation (more fluent, more cost)

## Where summaries are used

- `compose` prompt includes bot memory to maintain continuity.
- On "resume" (or at the start of a session), the system can show the user card immediately.

## Redaction and high-stakes domains

If you work in medicine/policing/legal:
- treat bot memory as sensitive
- implement redaction or encryption at rest
- avoid storing unnecessary PII
