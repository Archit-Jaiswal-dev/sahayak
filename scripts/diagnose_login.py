"""Diagnose the real CPGRAMS login: response headers, landing URL, cookies.

Runs the same login steps as `file_grievance --link` but captures evidence of
what actually happened, to figure out why no authenticated cookie appears in
the persisted session.

Usage:
    python -m scripts.verify_login_flow
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.rpa.human import CliHumanVerifier  # noqa: E402
from app.rpa.selectors import SELECTORS  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

human = CliHumanVerifier()


async def main() -> None:
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    submit_responses: list = []

    async def on_response(resp):
        loc = resp.headers.get("location")
        if resp.status in (301, 302, 303, 307):
            submit_responses.append((resp.status, resp.url, loc))
        elif "signin" in (resp.url or "").lower() or "home" in (resp.url or "").lower():
            sc = resp.headers.get("set-cookie", "")
            if sc:
                submit_responses.append((resp.status, resp.url, sc[:200]))

    page.on("response", on_response)

    print("1) goto", SELECTORS["signin_url"])
    await page.goto(SELECTORS["signin_url"], wait_until="domcontentloaded")
    print("   cookies before login:", [(c["name"], c["domain"]) for c in await context.cookies()])

    await page.fill(SELECTORS["login_username"], settings.cpgrams_email)
    await page.fill(SELECTORS["login_password"], settings.cpgrams_password)
    await page.wait_for_timeout(350)
    if await page.input_value(SELECTORS["login_password"]) == "":
        await page.fill(SELECTORS["login_password"], settings.cpgrams_password)

    solved = await human.solve_captcha(await page.locator(SELECTORS["captcha"]).screenshot())
    await page.locator(SELECTORS["captcha_input"]).fill(solved)

    print("2) clicking submit ...")
    await page.locator(SELECTORS["login_submit"]).click()
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1500)

    print(f"3) final url after submit: {page.url}")
    print(f"   title: {await page.title()}")
    landing = (await page.locator("body").inner_text())[:400].replace("\n", " | ")
    print(f"   landing body: {landing}")
    print(f"   cookies after login: {[(c['name'], c['domain'], c.get('httpOnly'), c.get('secure')) for c in await context.cookies()]}")
    print("   responses seen:")
    for s in submit_responses:
        print("        ", s)

    print("4) goto lodge page, wait")
    await page.goto(SELECTORS["lodge_grievance_url"], wait_until="networkidle")
    await page.wait_for_timeout(1000)
    gate = await page.locator(SELECTORS["login_required_text"]).count()
    print(f"   gate text present: {gate}   forms on page: {await page.locator('form').count()}")
    body = (await page.locator("body").inner_text())[:500].replace("\n", " | ")
    print("   body:", body)
    for t in ["Lodge Public Grievance", "Sign In", "Logout", "Log Out", "My Dashboard", "submit", "Subject", "Ministry"]:
        n = await page.get_by_text(t, exact=False).count()
        if n:
            print(f"     '{t}': {n}")

    print("5) storage_state cookie names:")
    ss = await context.storage_state()
    print("   ", [(c["name"], c["domain"]) for c in ss.get("cookies", [])])

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())