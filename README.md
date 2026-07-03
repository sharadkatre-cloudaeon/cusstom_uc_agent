# UCRG Agent — Use-Case Requirement Gathering Agent

A single, assistive agent that interviews a non-technical business user about an AI
use-case idea, silently classifies it against the AI Solutions Framework, asks adaptive
follow-ups, runs the decision gate, and produces a requirements document (SDD) plus a
framework scorecard for the development team.

## Quick start (no API key, no heavy installs)

```bash
cd ucrg-agent
python cli.py
```

That runs the full 7-segment interview in **offline mock mode**: canned plain-language
questions, keyword-based answer interpretation, the real JSON engine for follow-ups, the
real decision gate, and real SDD + scorecard output written to `./output/`. It exercises
everything except the LLM's linguistic finesse — enough to test the whole flow.

Say **"not sure"** to any follow-up to have it flagged for the technical team.

## Real model mode

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python cli.py --llm anthropic
```

Now question phrasing and answer extraction are done by Claude; the deterministic engine,
classifier, and gate are unchanged.

## Production orchestration (LangGraph)

```bash
pip install langgraph
python -m ucrg.graph
```

`ucrg/graph.py` is the same logic wired as a LangGraph `StateGraph` (the topology you
designed): `greet → ask_segment → advance_segment → decision_gate → compose`, with
`ask_segment` pausing via `interrupt()` and a checkpointer persisting state across turns.
The lightweight `ucrg/driver.py` and the graph share the same engine/classify/gate/compose
modules — one source of logic, two runtimes.

## How it maps to what was designed

| Concept | File |
|---|---|
| The 22 plain-language form questions + interview behaviour | `prompts/system_prompt.md` |
| The 176 baseline questions, routing, activation, gate triggers | `data/ucrg_engine.json` (compiled from the Excel workbook) |
| `lookup_followups`, `gate_rule`, `form_questions` | `ucrg/engine.py` |
| Silent 4×5 classification | `ucrg/classify.py` |
| Decision-gate ordered rule | `ucrg/gate.py` |
| SDD + scorecard output | `ucrg/compose.py` |
| Interview loop (start/send) | `ucrg/driver.py` |
| LangGraph version | `ucrg/graph.py` |

**The JSON is a generated artifact** — edit the Excel workbook, then re-export. Never hand-edit it.

## Layout

```
ucrg-agent/
├── cli.py                  # terminal runner
├── requirements.txt
├── .env.example
├── data/ucrg_engine.json   # the engine (compiled from Excel)
├── prompts/system_prompt.md
├── ucrg/
│   ├── state.py  engine.py  classify.py  gate.py  compose.py
│   ├── llm.py    driver.py  graph.py
├── tests/test_engine.py
└── output/                 # generated SDD + scorecard land here
```

## Tests

```bash
python tests/test_engine.py
python tests/test_classify.py
# or, after installing test deps:
python -m pytest -q
```

If you use `python -m pytest -q`, ensure dependencies are installed from
`requirements.txt` first.

## Requirements

Python 3.10+. Mock mode uses only the standard library.
