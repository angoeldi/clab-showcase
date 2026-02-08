# Install in Codex (or similar coding agents)

## 1) Place the skill

Unzip this archive and copy the folder:

- `langgraph-conversational-labour/`

into your repo at:

- `.agents/skills/langgraph-conversational-labour/`

So you end up with:

- `.agents/skills/langgraph-conversational-labour/SKILL.md`

## 2) Invoke it

In Codex, reference the skill by name, or ask it to run the scaffold script.

## 3) Scaffold the template project

From the repo root:

```bash
python .agents/skills/langgraph-conversational-labour/scripts/scaffold.py
```

Then edit:
- `configs/domain.yaml`
- `configs/tutorial.yaml`
