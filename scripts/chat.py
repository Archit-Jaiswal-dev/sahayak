"""Drive the Sahayak conversation loop from the terminal using typed Hindi.

This lets you test the slot-filling LLM behavior BEFORE any audio/STT exists.
Type your turns in Hindi (or Hinglish). Type `exit` to quit.

Requires LLM_PROVIDER + the matching key in .env (gemini or nim).

Usage:
    python -m scripts.chat
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers import get_llm_provider  # noqa: E402
from app.services.conversation import ConversationService  # noqa: E402

SESSION_ID = "cli-demo"


def _print_slots(filled: list, missing: list) -> None:
    status = []
    if filled:
        status.append(f"filled: {', '.join(filled)}")
    if missing:
        status.append(f"missing: {', '.join(missing)}")
    if status:
        print(f"  [{', '.join(status)}]")


async def main() -> None:
    llm = get_llm_provider()
    service = ConversationService(llm)
    service.create_session(SESSION_ID)

    print("=" * 60)
    print("SAHAYAK — Hindi grievance conversation demo (typed mode)")
    print("=" * 60)

    opener = await service.start(SESSION_ID)
    print(f"\nSahayak: {opener}")

    while True:
        reply = input("\nAap   : ").strip()
        if reply.lower() in ("exit", "quit", "band"):
            print("\nBye! Phir milenge.")
            break

        result = await service.process_turn(SESSION_ID, reply)
        _print_slots(result.filled, result.missing)

        if result.status == "closed":
            print(f"\nSahayak: {result.message}")
            break
        if result.status == "done":
            print(f"\nSahayak: Report confirm ho gayi. Filing ke liye taiyaar!")
            print(f"Report: {result.report_text}")
            break
        if result.question:
            print(f"Sahayak: {result.question}")


if __name__ == "__main__":
    asyncio.run(main())
