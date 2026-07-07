"""Deterministic engine accessors backed by data/ucrg_engine.json
(compiled from the Excel workbook). Loaded once; every call is a dict scan."""
import json
import os
from pathlib import Path

from .answer_options import parse_answer_options

_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "ucrg_engine.json"
_PATH = Path(os.environ["UCRG_ENGINE_PATH"]) if os.environ.get("UCRG_ENGINE_PATH") else _DEFAULT
ENGINE = json.loads(_PATH.read_text(encoding="utf-8"))

_ROUTE_BUCKET = {"Ask BU": "ask", "Auto-derived": "auto", "Tag Dev/Sec": "tag"}

DOMAIN_NAMES = ENGINE["classification"]["domains"]      # {"AU": "Automation", ...}
LEVEL_NAMES = ENGINE["classification"]["levels"]        # {"AU": [...5...], ...}


def lookup_followups(
    domain: str,
    level: int,
    *,
    answers: dict | None = None,
    signals: dict | None = None,
) -> dict:
    """Cumulative activated follow-ups for domain+level, split by how the agent uses them."""
    dom = domain.upper()
    ans = answers or {}
    sig = signals or {}
    out = {"ask": [], "auto": [], "tag": []}
    for q in ENGINE["baseline_questions"].values():
        if q["domain_code"] != dom or q["level"] > level:
            continue
        parent = q.get("parent")
        if parent and not parent_answer_satisfied(parent, ans, sig):
            continue
        b = _ROUTE_BUCKET[q["route"]]
        if b == "ask":
            out["ask"].append({"id": q["id"], "question": q["rephrase_or_note"],
                               "area": q["area"], "asked_in": q["asked_in"],
                               "parent": q["parent"]})
        elif b == "auto":
            out["auto"].append({"id": q["id"], "source": q["rephrase_or_note"],
                                "area": q["area"], "parent": q["parent"]})
        else:
            out["tag"].append({"id": q["id"], "open_item": q["original"],
                               "area": q["area"], "parent": q["parent"]})
    return out


def parent_answer_satisfied(parent_id: str, answers: dict, signals: dict) -> bool:
    """Gate baseline items on their parent form question when applicable."""
    if not parent_id or parent_id == "CLS":
        return True

    text = (answers.get(parent_id) or "").strip().lower()
    if not text and parent_id not in signals:
        return True  # parent not answered yet — keep in catalog

    from .llm import is_no, is_not_sure, is_yes

    if parent_id == "Q13":
        sens = signals.get("sensitivity")
        if sens in ("personal", "special"):
            return True
        if text and is_no(text):
            return False
        return is_yes(text) or sens not in (None, "none")
    if parent_id == "Q14":
        if signals.get("needs_knowledge") is True:
            return True
        if text and is_no(text):
            return False
        return is_yes(text)
    if parent_id == "Q16":
        if signals.get("sharing") is True:
            return True
        if text and is_no(text):
            return False
        return is_yes(text)
    if parent_id == "Q17":
        hitl = signals.get("hitl")
        if hitl == "auto":
            return True
        if text and any(w in text for w in ("own", "alone", "automatic", "without")):
            return True
        if text and is_no(text):
            return False
        return bool(text)
    if parent_id == "Q6":
        if signals.get("fairness_risk") is True:
            return True
        if text and is_no(text):
            return False
        return is_yes(text)
    if parent_id == "Q5":
        if signals.get("impact") == "high":
            return True
        if text and is_no(text):
            return False
        return is_yes(text) or any(
            w in text for w in ("customer", "eligibility", "pricing", "hiring", "complaint")
        )

    return bool(text) and not is_not_sure(text)


def gate_rule(domain: str, level: int) -> dict:
    return ENGINE["gate_triggers"].get(f"{domain.upper()}-L{level}", {})


def form_questions(segment: int | None = None) -> list:
    qs = [q for q in ENGINE["form_questions"] if q["id"] != "CLS"]
    if segment is not None:
        qs = [q for q in qs if str(q["segment"]).startswith(f"{segment} ")]
    return qs


def question_dict(fq: dict, *, kind: str = "standard") -> dict:
    """Normalise a form question into the shape used by driver/graph."""
    answer_type = fq.get("answer_type", "Text")
    out = {
        "id": fq["id"],
        "text": fq["question"],
        "kind": kind,
        "answer_type": answer_type,
        "options": parse_answer_options(answer_type),
        "gate_critical": bool(fq.get("gate_critical")),
    }
    if fq.get("additional_fields"):
        out["additional_fields"] = fq["additional_fields"]
    return out


def segment_label(segment: int) -> str:
    for q in ENGINE["form_questions"]:
        if str(q["segment"]).startswith(f"{segment} "):
            return q["segment"]
    return f"Segment {segment}"


TOTAL_SEGMENTS = 7


def segment_short_label(segment: int) -> str:
    full = segment_label(segment)
    return full.split(" · ", 1)[1] if " · " in full else full


def build_segment_progress(current_segment: int, *, done: bool = False) -> dict:
    """Structured stage metadata for a top-of-chat progress bar."""
    segments = []
    for seg in range(1, TOTAL_SEGMENTS + 1):
        if done or seg < current_segment:
            status = "complete"
        elif seg == current_segment:
            status = "current"
        else:
            status = "pending"
        segments.append({
            "id": seg,
            "label": segment_short_label(seg),
            "full_label": segment_label(seg),
            "status": status,
        })

    return {
        "current_segment": current_segment,
        "total_segments": TOTAL_SEGMENTS,
        "segment_label": segment_label(current_segment) if current_segment else "",
        "segments": segments,
    }
