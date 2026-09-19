"""Link / check / use a persisted CPGRAMS session, then file grievances.

Modes:
    --link              One-time assisted login (human CAPTCHA + OTP), persists the
                        encrypted session for reuse.
    --check-session     Verify the stored session is valid/unexpired.
    (default)           File a grievance using the stored session.

Usage:
    python -m scripts.file_grievance --link --account-key alice
    python -m scripts.file_grievance --check-session --account-key alice
    python -m scripts.file_grievance --grievance-file g.json --account-key alice
    python -m scripts.file_grievance --grievance path/to/grievance.json --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rpa.human import CliHumanVerifier  # noqa: E402
from app.rpa.models import GrievancePayload  # noqa: E402
from app.rpa.session_store import EncryptedSessionStore  # noqa: E402
from app.rpa.submitter import CPGRAMSSubmitter, SessionNotLinked  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_ATTEMPTS = 3
BACKOFF_BASE_S = 5.0


def _store() -> EncryptedSessionStore:
    try:
        return EncryptedSessionStore()
    except ValueError as e:
        raise SystemExit(str(e))


async def _link(account_key: str, headless: bool) -> None:
    store = _store()  # fail fast if no encryption key before opening a browser
    human = CliHumanVerifier()
    submitter = CPGRAMSSubmitter(headless=headless, human=human, store=store)
    record = await submitter.link_session(account_key)
    print(f"LINKED account '{account_key}'. Session valid until {record.expires_at:%Y-%m-%d %H:%M} UTC.")
    print("Note: session is encrypted at rest (AES-GCM) and short-lived.")
    print("Replaying the stored session into a fresh browser to verify it is reusable...")
    reuse = await submitter.probe_reuse(record)
    print("REUSE PROBE:", "PASS - persisted session authenticates in a fresh context" if reuse
          else "FAIL - portal rejected the stored session in a fresh context")


async def check(account_key: str, headless: bool) -> int:
    store = _store()  # check needs the encrypted store too
    submitter = CPGRAMSSubmitter(headless=headless, store=store)
    result = await submitter.check_session(account_key)
    print(json.dumps(result, indent=2))
    return 0 if result.get("valid") else 1


PREP_STATE = Path("/tmp/sahayak_prep_state.json")
PREP_CAPTCHA_IMG = Path("/tmp/sahayak_captcha_current.png")


async def prepare_link() -> None:
    """Screenshot today's CAPTCHA and save the tied session state, then exit."""
    from app.rpa.selectors import SELECTORS
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(SELECTORS["signin_url"], wait_until="domcontentloaded")
            await page.locator(SELECTORS["captcha"]).first.screenshot(path=str(PREP_CAPTCHA_IMG))
            PREP_STATE.write_text(json.dumps(await context.storage_state()))
            print(f"Captcha image saved to {PREP_CAPTCHA_IMG}")
            print("Tell me the characters shown there and I will finish the login.")
        finally:
            await browser.close()


async def complete_link(account_key: str, captcha: str, headless: bool) -> None:
    """Finish the login: restore the prepared state, submit, persist, probe."""
    from datetime import datetime, timedelta, timezone

    from app.config import settings
    from app.rpa.selectors import SELECTORS
    from app.rpa.session_store import SessionRecord
    from playwright.async_api import async_playwright

    store = _store()
    state = json.loads(PREP_STATE.read_text())
    submitter = CPGRAMSSubmitter(headless=headless, store=store)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(storage_state=state)
            page = await context.new_page()
            await page.goto(SELECTORS["signin_url"], wait_until="domcontentloaded")

            await page.fill(SELECTORS["login_username"], settings.cpgrams_email)
            await page.fill(SELECTORS["login_password"], settings.cpgrams_password)
            await page.wait_for_timeout(350)
            if await page.input_value(SELECTORS["login_password"]) == "":
                await page.fill(SELECTORS["login_password"], settings.cpgrams_password)

            await page.locator(SELECTORS["captcha_input"]).first.fill(captcha)
            await page.locator(SELECTORS["login_submit"]).first.click()
            await page.wait_for_load_state("domcontentloaded")

            storage_state = await context.storage_state()
            await page.goto(SELECTORS["desk_url"], wait_until="domcontentloaded")
            if await page.locator(SELECTORS["welcome_text"]).count() == 0:
                print("LOGIN REJECTED: /Desk did not welcome the user "
                      "(wrong credentials or a stale captcha).")
                return

            now = datetime.now(timezone.utc)
            ttl = settings.sahayak_session_ttl_hours or 24.0
            record = SessionRecord(
                account_key=account_key,
                storage_state=storage_state,
                created_at=now,
                expires_at=now + timedelta(hours=ttl),
            )
            store.save(record)
            print(f"LINKED account '{account_key}'. Valid until {record.expires_at:%Y-%m-%d %H:%M} UTC.")
            reuse = await submitter.probe_reuse(record)
            print("REUSE PROBE:", "PASS - persisted session authenticates in a fresh context"
                  if reuse else "FAIL - portal rejected the stored session in a fresh context")
        finally:
            await browser.close()


async def probe_grievance_form(account_key: str, headless: bool) -> None:
    """Read-only: walk the authenticated desk to the grievance form and dump
    its fields, without submitting anything."""
    import json as _json

    store = _store()
    record = store.load(account_key)
    if record is None:
        raise SystemExit(f"No valid stored session for '{account_key}'. Run --link first.")
    submitter = CPGRAMSSubmitter(headless=headless, store=store)
    from app.rpa.selectors import SELECTORS
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(storage_state=record.storage_state)
            page = await context.new_page()
            await page.goto(SELECTORS["desk_url"], wait_until="domcontentloaded")
            if await page.locator(SELECTORS["welcome_text"]).count() == 0:
                print("DESK: not logged in (stored session stale). Re-link first.")
                return
            print("DESK: logged in OK")
            await page.locator("a[href*='NewGrievance']").click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(800)
            print(f"FORM url: {page.url} (status title: {await page.title()})")
            if await page.locator("#termscondition").count() and await page.locator("#submit").count():
                print("terms page: accepting terms to reveal the real form...")
                await page.locator("#termscondition").check()
                await page.locator("#submit").click()
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(1200)
                print(f"  -> now at {page.url} (title: {await page.title()})")
            print("--- select options (first page) ---")
            sel = page.locator("select").first
            if await sel.count():
                opts = await sel.locator("option").evaluate_all("els => els.map(e => e.text).filter(t => t.trim())")
                print("  select:", await sel.get_attribute("name") or await sel.get_attribute("id"),
                      f"({len(opts)} options)")
                print("  label_by_id:", await page.locator("label[for='moreOrg']").first.inner_text() if await page.locator("label[for='moreOrg']").count() else "(no label)")
                for o in opts[:40]:
                    print("     -", o)
            print("--- buttons ---")
            btns = await page.eval_on_selector_all("button, input[type=submit]", """
                els => els.map(e => ({t:(e.innerText||'').trim(), id:e.id||'', type:e.type||''})).filter(b => b.t || b.id)
            """)
            for b in btns[:20]:
                print("   ", b)

            print("--- walking the guided form (never clicking 'Submit') ---")
            for step in range(1, 6):
                selects = page.locator("select")
                n = await selects.count()
                print(f"[step {step}] url={page.url} title={await page.title()} selects={n}")
                if n == 0:
                    print("  no selects -> stopping (form may collect text next)")
                    break
                for i in range(n):
                    s = selects.nth(i)
                    name = await s.get_attribute("name") or await s.get_attribute("id") or f"sel{i}"
                    count = await s.locator("option").count()
                    first_two = await s.locator("option").evaluate_all("els => els.slice(0,2).map(e => e.text)")
                    print(f"   <select {name!r}> options={count} first={first_two}")
                # advance using the deepest select that still has unsaid options
                adv = None
                for i in reversed(range(n)):
                    s = selects.nth(i)
                    if await s.locator("option").count() > 1:
                        opts = await s.locator("option").evaluate_all("els => els.map(e => ({v:e.value,t:e.text}))")
                        for o in opts:
                            if o["t"].strip() and "select" not in o["t"].lower() and "-select-" not in o["t"].lower():
                                adv = (i, o)
                                break
                        if adv:
                            break
                if adv is None:
                    print("   no advanceable select; stopping")
                    break
                idx, chosen = adv
                print(f"   -> choosing '{chosen['t']}' in select[{idx}]")
                await selects.nth(idx).select_option(chosen["v"])
                await page.wait_for_timeout(1500)
                await page.wait_for_load_state("domcontentloaded")
            print("--- clicking 'Next' (never the final Submit) to map the details step ---")
            if await page.locator("#btnNext").count():
                if await page.locator("#Remarks").count():
                    await page.locator("#Remarks").fill("SAHAYAK PROBE - DO NOT FILE")
                await page.locator("#btnNext").click()
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(1500)
                print(f"DETAILS url: {page.url} (title: {await page.title()})")
                for f in await page.eval_on_selector_all(
                    "input, select, textarea, button",
                    """els => els.map(e => ({
                        tag: e.tagName, type: e.type||'', name: e.name||'', id: e.id||'',
                        ph: e.placeholder||'', required: !!e.required
                    }))""",
                ):
                    if f["name"] or f["id"]:
                        print("   ", f)
                await page.wait_for_timeout(500)
                # Just identify a final submit button, do NOT click it.
                subs = await page.eval_on_selector_all(
                    "button, input[type=submit]",
                    """els => els.map(e => ({t:(e.innerText||e.value||'').trim(), id:e.id||''}))
                        .filter(b => /submit|preview|back/i.test(b.t))""",
                )
                print("   submit-ish controls:", subs)

            print("--- final page fields ---")
            fields = await page.eval_on_selector_all(
                "input, select, textarea, button",
                """els => els.map(e => ({
                    tag: e.tagName, type: e.type||'', name: e.name||'', id: e.id||'',
                    ph: e.placeholder||'', required: !!e.required
                }))""",
            )
            seen = set()
            print("--- form fields ---")
            for f in fields:
                key = (f["tag"], f["type"], f["name"], f["id"])
                if key in seen or not (f["name"] or f["id"]):
                    continue
                seen.add(key)
                print("  ", f)
        finally:
            await browser.close()


async def file_grievance(payload: GrievancePayload, *, account_key: str, attempts: int, headless: bool, dry_run: bool) -> str:
    if dry_run:
        print("DRY-RUN: flow would be (load session -> dept -> fill -> submit -> scrape id)")
        print(f"  subject     : {payload.subject}")
        print(f"  ministry    : {payload.routed_ministry}")
        print(f"  department  : {payload.routed_department}")
        print(f"  location    : {payload.location}")
        return "CPGRAMS-DRY-RUN-0000000000000000"

    submitter = CPGRAMSSubmitter(headless=headless)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            logger.info("Attempt %d/%d", attempt, attempts)
            reg_id = await submitter.submit(payload, account_key=account_key)
            print(f"REGISTRATION_ID: {reg_id}")
            return reg_id
        except SessionNotLinked as e:
            print(f"SESSION NOT LINKED: {e}", file=sys.stderr)
            print(f"Run: python -m scripts.file_grievance --link --account-key {account_key}")
            return ""
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.error("Attempt %d failed: %r", attempt, exc)
            if attempt < attempts:
                backoff = BACKOFF_BASE_S * (2 ** (attempt - 1))
                logger.info("Backing off %.0fs before retry", backoff)
                await asyncio.sleep(backoff)

    print(f"FAILED after {attempts} attempts: {last_error!r}", file=sys.stderr)
    return ""


def _load_payload(raw: str | None, path: Path | None) -> GrievancePayload:
    if path:
        data = json.loads(path.read_text(encoding="utf-8"))
    elif raw:
        data = json.loads(raw)
    else:
        raise SystemExit("Provide --grievance (JSON string) or --grievance-file (path).")
    return GrievancePayload.model_validate(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sahayak CPGRAMS RPA: link, check, file")
    parser.add_argument("--grievance", help="grievance JSON string")
    parser.add_argument("--grievance-file", type=Path, help="path to grievance JSON file")
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--headful", action="store_true", help="run with visible browser")
    parser.add_argument("--dry-run", action="store_true", help="validate + plan only")
    parser.add_argument("--link", action="store_true", help="one-time session link")
    parser.add_argument("--prepare-link", action="store_true", help="capture CAPTCHA + state for me to finish with --complete-link")
    parser.add_argument("--complete-link", help="finish login with a CAPTCHA (pass the characters)")
    parser.add_argument("--probe-form", action="store_true", help="read-only dump of the authenticated grievance form fields")
    parser.add_argument("--check-session", action="store_true", help="validate stored session")
    parser.add_argument("--account-key", default="default", help="account identity for the session")
    args = parser.parse_args()

    if args.link:
        asyncio.run(_link(args.account_key, not args.headful))
        return
    if args.prepare_link:
        asyncio.run(prepare_link())
        return
    if args.complete_link:
        asyncio.run(complete_link(args.account_key, args.complete_link, not args.headful))
        return
    if args.probe_form:
        asyncio.run(probe_grievance_form(args.account_key, not args.headful))
        return
    if args.check_session:
        sys.exit(asyncio.run(check(args.account_key, not args.headful)))

    payload = _load_payload(args.grievance, args.grievance_file)
    asyncio.run(
        file_grievance(
            payload,
            account_key=args.account_key,
            attempts=args.attempts,
            headless=not args.headful,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()