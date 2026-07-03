"""Production orchestration as a LangGraph StateGraph.

This mirrors the topology diagram exactly and reuses the SAME deterministic
modules as the lightweight driver (engine / classify / gate / compose). The only
difference is that ask_segment uses interrupt() to pause for the user and a
checkpointer persists state across turns.

Requires:  pip install langgraph
Run:       python -m ucrg.graph        (interactive, mock interpretation)
"""
from __future__ import annotations
import re

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver

from .state import UCRGState
from .engine import form_questions, segment_label, lookup_followups
from .classify import classify_use_case, is_firm
from .gate import gate_inputs_from, run_decision_gate
from .compose import compose_output
from .llm import make_llm, keyword_signals, is_not_sure

_LLM = make_llm("mock")  # swap to make_llm("anthropic", system_prompt) in production


def _segs(asked_in: str) -> set:
    return set(int(n) for n in re.findall(r"Seg\s*(\d)", asked_in or ""))


def _queue_for_segment(state: UCRGState) -> list:
    """Standard questions for the current segment + activated follow-ups (ask) for it."""
    q = [{"id": fq["id"], "text": fq["question"], "kind": "standard"}
         for fq in form_questions(state.current_segment)]
    if is_firm(state.classification):
        p = state.classification["primary"]
        act = lookup_followups(p["domain"], p["level"])
        for it in act["ask"]:
            if it["id"] not in state.asked_followup_ids and state.current_segment in _segs(it["asked_in"]):
                state.asked_followup_ids.add(it["id"])
                q.append({"id": it["id"], "text": it["question"], "kind": "followup"})
        seen = {o["id"] for o in state.open_items}
        for it in act["tag"]:
            if it["id"] not in seen:
                state.open_items.append(it); seen.add(it["id"])
    return q


def greet(state: UCRGState):
    state.current_segment = 1
    return state


def ask_segment(state: UCRGState):
    """Ask every queued question for the current segment, pausing at each via interrupt."""
    for q in _queue_for_segment(state):
        reply = interrupt({"question": _LLM.phrase(q["text"])})
        if q["kind"] == "followup" and is_not_sure(reply):
            state.open_items.append({"id": q["id"], "open_item": q["text"], "area": "—"})
            continue
        state.answers[q["id"]] = reply
        state.signals.update(_LLM.extract_signals(q["id"], q["text"], reply))
        state.classification = classify_use_case(state.signals)
    return state


def advance_segment(state: UCRGState) -> Command:
    nxt = state.current_segment + 1
    if nxt > 7:
        return Command(goto="decision_gate")
    state.current_segment = nxt
    return Command(goto="ask_segment")


def decision_gate(state: UCRGState):
    state.gate_verdict = run_decision_gate(gate_inputs_from(state.signals, state.classification))
    return state


def compose(state: UCRGState):
    state.output = compose_output(state)
    state.done = True
    return state


def build_graph():
    g = StateGraph(UCRGState)
    g.add_node("greet", greet)
    g.add_node("ask_segment", ask_segment)
    g.add_node("advance_segment", advance_segment)
    g.add_node("decision_gate", decision_gate)
    g.add_node("compose", compose)

    g.add_edge(START, "greet")
    g.add_edge("greet", "ask_segment")
    g.add_edge("ask_segment", "advance_segment")   # advance_segment routes via Command(goto=...)
    g.add_edge("decision_gate", "compose")
    g.add_edge("compose", END)
    return g.compile(checkpointer=MemorySaver())


if __name__ == "__main__":
    app = build_graph()
    cfg = {"configurable": {"thread_id": "demo"}}
    state = app.invoke({"current_segment": 0}, cfg)
    while "__interrupt__" in state:
        q = state["__interrupt__"][0].value["question"]
        ans = input(f"\nAgent: {q}\nYou: ")
        state = app.invoke(Command(resume=ans), cfg)
    print("\nAgent: done. Verdict:", state["gate_verdict"]["verdict"])
    print("\n" + state["output"]["scorecard"])
