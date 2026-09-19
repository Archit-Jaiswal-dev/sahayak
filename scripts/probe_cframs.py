"""Probe the live CPGRAMS portal (pgportal.gov.in) to VERIFY RPA selectors.

READ-ONLY: opens the site, navigates to the login view, and dumps the actual
DOM (inputs, buttons, captcha images) so the selectors in app/rpa/selectors.py
can be confirmed/updated against reality. Submits nothing.

Usage:
    python -m scripts.probe_cprams
"""

from __future__ import annotations

import asyncio
import json

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("=" * 70)
        print("STEP 1: homepage + locate login control")
        print("=" * 70)
        try:
            resp = await page.goto(
                "https://pgportal.gov.in", wait_until="domcontentloaded", timeout=45_000
            )
        except Exception as e:
            print(f"REACHABLE? no — {e!r}")
            await browser.close()
            return
        print(f"REACHABLE: HTTP {resp.status if resp else '?'} | title: {await page.title()}")

        candidates = {
            "a[href*='ogin']": await page.locator("a[href*='ogin']").count(),
            "a:text('Login')": await page.locator("a:has-text('Login')").count(),
            "button:has-text('Login')": await page.locator("button:has-text('Login')").count(),
            "a:has-text('Lodge Public Grievance')": await page.locator("a:has-text('Lodge Public Grievance')").count(),
        }
        for sel, n in candidates.items():
            print(f"  {sel:28} -> {n}")

        # Try clicking the most specific login control (link to login page).
        clicked = False
        for sel in ("a:has-text('Login')", "a[href*='ogin']"):
            loc = page.locator(sel)
            if await loc.count() > 0:
                first = loc.first
                href = await first.get_attribute("href")
                print(f"  clicking '{sel}' (href={href})")
                await first.click(timeout=10_000)
                await page.wait_for_load_state("domcontentloaded")
                clicked = True
                break

        if not clicked or "ogin" not in page.url:
            for url in ["https://pgportal.gov.in/Login", "https://pgportal.gov.in/UserLogin"]:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    if "ogin" in page.url:
                        break
                except Exception as e:
                    print(f"  {url}: {e!r}")

        print("\n" + "=" * 70)
        print("STEP 2: login page DOM")
        print("=" * 70)
        result = {
            "url": page.url,
            "title": await page.title(),
            "inputs": await page.eval_on_selector_all(
                "input",
                "els => els.map(e => ({type: e.type, name: e.name, id: e.id, placeholder: e.placeholder, aria: e.getAttribute('aria-label')}))",
            ),
            "buttons": await page.eval_on_selector_all(
                "button",
                "els => els.map(e => ({text: (e.innerText||'').trim()}))",
            ),
            "captcha_imgs": await page.eval_on_selector_all(
                "img",
                "els => els.filter(e => /captcha/i.test((e.src||'') + ' ' + (e.alt||'') + ' ' + (e.id||''))).map(e => ({id: e.id, src: e.src, alt: e.alt}))",
            ),
        }
        print(json.dumps(result, indent=2))

        print("\n--- forms outerHTML (truncated) ---")
        forms = await page.eval_on_selector_all(
            "form",
            "els => els.map(e => e.outerHTML.slice(0, 2500))",
        )
        for i, html in enumerate(forms):
            print(f"\n-- form {i} --\n{html}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())