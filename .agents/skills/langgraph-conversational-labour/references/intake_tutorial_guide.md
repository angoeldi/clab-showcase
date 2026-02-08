# Intake tutorial guide (visual cycle)

The intake tutorial is not "help text". It is an interaction design that calibrates:

- what the system does,
- what it will not do,
- how the user should interact to get value,
- how to correct the system,
- how session summaries enable resumption.

## Design principles

1) **Short**: 4-7 steps, each under ~120 words.
2) **Visually distinct**: each step has a title + a diagram/snippet.
3) **Interactive**: user can type `next`, `back`, `skip`.
4) **Expectation management**: explain hypotheses vs facts; explain safety limits.
5) **Agency**: user can edit goal, constraints, and success criteria at any time.
6) **Resume-ready**: explain that each turn ends with a status card and that the bot keeps a machine summary.

## The canonical cycle (include a diagram)

Use a stable conceptual loop the user can remember. Default:

```
Goal -> Sensemaking -> Action -> Reflection -> (update Goal)
```

Alternative loops by domain:

- Diagnostic: `Presenting problem -> Clarify -> Differential -> Plan -> Follow-up`
- Tutoring: `Topic -> Diagnose gap -> Explain -> Practice -> Feedback -> Next topic`
- Interview: `Agenda -> Question -> Probe -> Confirm -> Transition -> Wrap-up`

## Recommended tutorial steps

1) **What this is**
   - One sentence promise.
   - One sentence limit (what it cannot do).

2) **The cycle (diagram)**
   - Show the loop.
   - Name each step in 1 line.

3) **How to talk to it**
   - "Give goal + constraints."
   - "Answer one question at a time."
   - "Say 'pause' if you want a summary or to change direction."

4) **Hypotheses vs facts**
   - Explain non-factive reasoning.
   - Teach the user to confirm/deny.

5) **Status summaries and resuming**
   - Explain the user card at the end of each message.
   - Explain that the bot stores a machine summary for continuity.

6) **Safety + escalation**
   - Explain high-stakes boundaries.
   - Provide the domain-specific escalation instruction.

## YAML template (`configs/tutorial.yaml`)

```yaml
enabled: true
start_when:
  - first_turn
  - user_says: ["how does this work", "help", "tutorial"]
steps:
  - id: "what"
    title: "What this system does"
    body_md: |
      I help you reach **your goal** by running a repeatable cycle:
      sensemaking -> action -> reflection.
      I will ask for missing information instead of guessing.
    cta: "Type `next` or `skip`."
  - id: "cycle"
    title: "The cycle"
    body_md: |
      ```
      Goal -> Sensemaking -> Action -> Reflection -> (update Goal)
      ```
      - Sensemaking: I summarise + test hypotheses.
      - Action: I propose one next step.
      - Reflection: we check what changed.
    cta: "Type `next`."
  - id: "talk"
    title: "How to interact"
    body_md: |
      Best results when you:
      - state goal + constraints
      - answer one question at a time
      - correct me when I'm wrong
    cta: "Type `next`."
  - id: "hypotheses"
    title: "Hypotheses are not facts"
    body_md: |
      If I infer something, I label it as a hypothesis and ask you to confirm.
      You can reply: "yes", "no", or "partly".
    cta: "Type `next`."
  - id: "resume"
    title: "Status and resuming"
    body_md: |
      Every turn ends with a short **Status** card.
      I also keep a machine-readable summary so you can resume later.
    cta: "Type `next` to start."
```

## Implementation hooks in the scaffold

- `clab_bot/tutorial.py` loads and renders the steps.
- The graph routes into tutorial mode until `completed=true`.
- The tutorial's state is persisted by the checkpointer, so it won't re-run unnecessarily.
