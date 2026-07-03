#!/usr/bin/env python3
"""Terminal runner for the UCRG agent.

  python cli.py                 # offline mock mode (no API key needed)
  python cli.py --llm anthropic # real model (needs `pip install anthropic` + ANTHROPIC_API_KEY)

Type your answers at the prompt. Say "not sure" to have a question flagged for the
technical team. At the end, the SDD + scorecard are written to ./output/.
"""
import argparse
import os
import pathlib
import re

from ucrg import UCRGAgent

PROMPT = pathlib.Path(__file__).parent / "prompts" / "system_prompt.md"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", choices=["mock", "anthropic"], default="mock")
    ap.add_argument("--name", default="usecase", help="output file prefix")
    args = ap.parse_args()

    system_prompt = PROMPT.read_text(encoding="utf-8") if PROMPT.exists() else ""
    agent = UCRGAgent(backend=args.llm, system_prompt=system_prompt)

    print("=" * 70)
    print(f"UCRG agent  ·  backend={args.llm}")
    print("=" * 70)
    print("\nAgent:", agent.start(), "\n")

    while not agent.s.done:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[ended]")
            return
        if user.lower() in ("quit", "exit"):
            print("[ended]")
            return
        if not user:
            continue
        r = agent.send(user)
        print("\nAgent:", r["message"], "\n")

    out = agent.s.output
    outdir = pathlib.Path(__file__).parent / "output"
    outdir.mkdir(exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", args.name)
    (outdir / f"{safe}_SDD.md").write_text(out["sdd"], encoding="utf-8")
    (outdir / f"{safe}_scorecard.md").write_text(out["scorecard"], encoding="utf-8")
    print(f"\nWritten:\n  output/{safe}_SDD.md\n  output/{safe}_scorecard.md")


if __name__ == "__main__":
    main()
