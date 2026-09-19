"""Capture the full CPGRAMS ministry/department catalog into a repo data file.

Read-only: logs into the portal via the stored encrypted session, walks the
authenticated grievance form, and dumps every option from the Organisation
(#moreOrg) select. Submits nothing.

Usage:
    python -m scripts.capture_orgs --account-key default
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.async_api import async_playwright  # noqa: E402

from app.config import settings  # noqa: E402
from app.rpa.session_store import EncryptedSessionStore  # noqa: E402

OUT = Path("data/cpgrams_orgs.json")


async def main(account_key: str) -> None:
    store = EncryptedSessionStore()
    record = store.load(account_key)
    if record is None:
        raise SystemExit(f"No valid stored session for '{account_key}'. Run --link first.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(storage_state=record.storage_state)
            page = await context.new_page()
            await page.goto("https://pgportal.gov.in/Desk", wait_until="domcontentloaded")
            if await page.locator("text=Welcome").count() == 0:
                print("DESK: not logged in (stored session stale). Re-link first.")
                return
            print("DESK: logged in OK")
            await page.locator("a[href*='NewGrievance']").click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(800)
            if await page.locator("#termscondition").count() and await page.locator("#submit").count():
                print("terms page: accepting terms...")
                await page.locator("#termscondition").check()
                await page.locator("#submit").click()
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(1200)

            org = page.locator("#moreOrg").first
            if await org.count() == 0:
                print("Organisation select (#moreOrg) not found. Dumping available selects:")
                for i in range(await page.locator("select").count()):
                    s = page.locator("select").nth(i)
                    print("  -", await s.get_attribute("name") or await s.get_attribute("id") or f"sel{i}")
                return

            options = await org.locator("option").evaluate_all(
                "els => els.map(e => ({value: e.value, label: e.text.trim()}))"
            )
            meaningful = [o for o in options if o["label"] and "select" not in o["label"].lower()]

            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(
                json.dumps(
                    {"source": "pgportal.gov.in #moreOrg (2026-08-14)", "ministries": meaningful},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"Captured {len(meaningful)} ministries -> {OUT}")
            for o in meaningful:
                print("   -", o["label"])
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "default"))
