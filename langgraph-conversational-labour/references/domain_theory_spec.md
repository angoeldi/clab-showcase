# Domain theory spec (YAML contract)

This scaffold treats "domain theory" as *data*, not prompt poetry. You edit `configs/domain.yaml`, and the bot follows it.

## 1. Minimal fields

A domain must define:

- `meta`: name/version/description
- `stages`: ordered phases the bot can be in
- `constructs`: signals the bot tracks (as scores + qualitative notes)
- `interventions`: the action library (what the bot can do)
- `action_policy`: deterministic rules + LLM fallback policy
- `safety`: red flags and safe completion behaviour
- `writing_style`: constraints on the bot's language

## 2. Recommended shape

```yaml
meta:
  name: "Example: Coaching"
  version: "0.1"
  description: "Replace this with your domain theory."

runtime:
  model: "gpt-5.2"
  reasoning_effort:
    analyze: "low"
    act: "low"
    compose: "medium"
  store_responses: true

stages:
  - id: "intake"
    goal: "Elicit goal, context, constraints, and success criteria."
    entry_criteria: ["first_turn OR goal_unknown"]
    exit_criteria: ["goal_known AND constraints_known"]
  - id: "plan"
    goal: "Agree on a plan and next step."
  - id: "execute"
    goal: "Run stepwise work and keep user on track."
  - id: "review"
    goal: "Reflect, update plan, consolidate learning."

constructs:
  - id: "goal_clarity"
    scale: {min: 0, max: 5, anchor_min: "unclear", anchor_max: "crisp"}
  - id: "motivation"
    scale: {min: 0, max: 5, anchor_min: "low", anchor_max: "high"}
  - id: "risk"
    scale: {min: 0, max: 5, anchor_min: "none", anchor_max: "urgent"}

interventions:
  - id: "PROBE"
    purpose: "Ask targeted questions to fill missing info."
    constraints:
      must: ["one_question_at_a_time", "no leading questions unless domain allows"]
  - id: "REFLECT"
    purpose: "Mirror + validate + compress the user's content."
  - id: "CHALLENGE"
    purpose: "Gently test assumptions; offer alternative framing."
  - id: "INSTRUCT"
    purpose: "Teach/explain step-by-step; check understanding."
  - id: "REDIRECT"
    purpose: "Bring user back to goal, plan, or constraints."
  - id: "SUMMARISE"
    purpose: "Create an explicit status card + next step."

action_policy:
  rules:
    - when:
        stage_in: ["intake"]
        missing_any: ["goal", "constraints"]
      then:
        action: "PROBE"
        params:
          question_style: "short"
    - when:
        risk_gte: 4
      then:
        action: "SAFETY"
        params:
          mode: "de_escalate_and_refer"

  llm_fallback:
    enabled: true
    allowed_actions: ["PROBE","REFLECT","CHALLENGE","INSTRUCT","REDIRECT","SUMMARISE"]
    disallowed_actions: ["DIAGNOSE","PRESCRIBE"]

safety:
  red_flags:
    - id: "self_harm"
      patterns: ["suicide", "kill myself", "self harm"]
      response_mode: "crisis"
    - id: "medical_emergency"
      patterns: ["chest pain", "can't breathe"]
      response_mode: "emergency"
  policies:
    crisis:
      instruction: "Provide crisis resources; encourage contacting local emergency services."
    emergency:
      instruction: "Encourage immediate medical attention; avoid diagnosis."

writing_style:
  tone: "clear, direct, non-judgmental"
  formatting:
    max_bullets: 8
    include_status_card: true
```

## 3. Non-factive reasoning (required)

Any inference that is not directly stated by the user must be emitted as a hypothesis:

- hypothesis: "User may be overwhelmed by scope."
- confidence: low/medium/high
- ask_confirmation: true

Never present hypotheses as facts.

## 4. Action selection

The scaffold uses:

1) **Rule-first** mapping (structured intervention) for reliability.
2) **LLM fallback** (adaptive generation) only when no rule matches.

## 5. How this maps to code

- The analyzer produces a structured `AnalysisResult` with:
  - `stage`, `signals`, `facts`, `hypotheses`, `open_questions`, `risks`
- The policy selects an `ActionPlan` (action + params).
- The composer writes the user message implementing the action.
- The summariser updates:
  - `status.user_card_md`
  - `status.bot_memory` (machine-parseable)
