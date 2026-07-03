"""Deterministic engine accessors backed by data/ucrg_engine.json
(compiled from the Excel workbook). Loaded once; every call is a dict scan."""
import json
import os
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "ucrg_engine.json"
_PATH = Path(os.environ["UCRG_ENGINE_PATH"]) if os.environ.get("UCRG_ENGINE_PATH") else _DEFAULT
ENGINE = json.loads(_PATH.read_text(encoding="utf-8"))

_ROUTE_BUCKET = {"Ask BU": "ask", "Auto-derived": "auto", "Tag Dev/Sec": "tag"}

DOMAIN_NAMES = ENGINE["classification"]["domains"]      # {"AU": "Automation", ...}
LEVEL_NAMES = ENGINE["classification"]["levels"]        # {"AU": [...5...], ...}


def lookup_followups(domain: str, level: int) -> dict:
    """Cumulative activated follow-ups for domain+level, split by how the agent uses them."""
    dom = domain.upper()
    out = {"ask": [], "auto": [], "tag": []}
    for q in ENGINE["baseline_questions"].values():
        if q["domain_code"] != dom or q["level"] > level:
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


def gate_rule(domain: str, level: int) -> dict:
    return ENGINE["gate_triggers"].get(f"{domain.upper()}-L{level}", {})


def form_questions(segment: int | None = None) -> list:
    qs = [q for q in ENGINE["form_questions"] if q["id"] != "CLS"]
    if segment is not None:
        qs = [q for q in qs if str(q["segment"]).startswith(f"{segment} ")]
    return qs


def segment_label(segment: int) -> str:
    for q in ENGINE["form_questions"]:
        if str(q["segment"]).startswith(f"{segment} "):
            return q["segment"]
    return f"Segment {segment}"
