"""
CourtReserve Automation
Login → select date → find reserveBtn buttons → open modal → fill → screenshot → close
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

LOGIN_URL    = "https://app.courtreserve.com/Online/Account/LogIn/10738"
BOOKINGS_URL = "https://app.courtreserve.com/Online/Reservations/Bookings/10738?sId=16007"
SCREENSHOT_DIR = Path("/config/scripts/py/screenshots")

EMAIL    = os.getenv("COURT_EMAIL", "")
PASSWORD = os.getenv("COURT_PASSWORD", "")
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"

_date_env = os.getenv("DATE", "").strip()
TARGET_DATE = datetime.strptime(_date_env, "%Y%m%d") if _date_env else datetime.now() + timedelta(weeks=1)

_time_env = os.getenv("TIME", "0800 PM").strip()
_t    = _time_env.replace(" ", "")
_ampm = _t[-2:].upper()
_hhmm = _t[:-2].zfill(4)
TARGET_TIME = f"{int(_hhmm[:2])}:{_hhmm[2:]} {_ampm}"

DURATION = float(os.getenv("DURATION", "1"))

# Map config duration to exact dropdown option text
DURATION_LABELS = {
    0.25: "15 minutes",
    0.5:  "30 minutes",
    0.75: "45 minutes",
    1.0:  "1 hour",
    1.25: "1 hour & 15 minutes",
    1.5:  "1 hour & 30 minutes",
    2.0:  "2 hours",
}
DURATION_LABEL = DURATION_LABELS.get(DURATION, "1 hour")

print(f"[config] Date     : {TARGET_DATE.strftime('%B %d, %Y')}")
print(f"[config] Time     : {TARGET_TIME}")
print(f"[config] Duration : {DURATION}h → {DURATION_LABEL!r}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def screenshot(page, name):
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=False, timeout=8000)
        print(f"[screenshot] {path.name}")
    except Exception as e:
        print(f"[screenshot] SKIPPED: {e}")


def block_fonts(route):
    if "fonts.googleapis.com" in route.request.url or \
       "fonts.gstatic.com"    in route.request.url or \
       route.request.resource_type == "font":
        route.abort()
    else:
        route.continue_()


def click_kendo_option(page, dropdown_span, option_text: str) -> bool:
    """Click a Kendo <span> dropdown and select the matching option."""
    try:
        dropdown_span.click()
        page.wait_for_timeout(600)
        # Options appear in a Kendo popup list outside the modal
        for sel in [
            f'.k-list-content li:has-text("{option_text}")',
            f'.k-popup li:has-text("{option_text}")',
            f'li.k-item:has-text("{option_text}")',
            f'li:has-text("{option_text}")',
        ]:
            opts = page.query_selector_all(sel)
            for opt in opts:
                if opt.is_visible() and opt.inner_text().strip() == option_text:
                    opt.click()
                    page.wait_for_timeout(400)
                    print(f"[modal] Selected: {option_text!r}")
                    return True
        # Print visible options for debug
        all_opts = page.query_selector_all('.k-list-content li, .k-popup li, li.k-item')
        visible = [o.inner_text().strip() for o in all_opts if o.is_visible()]
        print(f"[modal] Visible options: {visible}")
        page.keyboard.press("Escape")
        return False
    except Exception as e:
        print(f"[modal] click_kendo_option error: {e}")
        return False


# ── Login ─────────────────────────────────────────────────────────────────────

def login(page) -> bool:
    print(f"\n[login] Logging in ...")
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
    try:
        page.wait_for_selector('input[name="email"]', state="visible", timeout=30000)
    except PlaywrightTimeout:
        print("[login] ERROR: form never appeared")
        return False
    page.fill('input[name="email"]', EMAIL)
    page.fill('input[name="password"]', PASSWORD)
    page.wait_for_timeout(500)
    for sel in ['button[type="submit"]', 'button:has-text("Log In")', '.ant-btn-primary']:
        el = page.query_selector(sel)
        if el and el.is_visible():
            el.click()
            break
    try:
        page.wait_for_url(lambda url: "LogIn" not in url, timeout=20000)
        print(f"[login] OK")
        return True
    except PlaywrightTimeout:
        print("[login] FAILED")
        return False


# ── Date selection ────────────────────────────────────────────────────────────

def select_date(page) -> bool:
    print(f"\n[date] Selecting {TARGET_DATE.strftime('%B %d, %Y')} ...")
    try:
        page.wait_for_selector('.k-nav-current', state="visible", timeout=10000)
        page.click('.k-nav-current')
        page.wait_for_timeout(800)
    except Exception as e:
        print(f"[date] Could not open calendar: {e}")
        return False
    for sel in [
        f'[data-date="{TARGET_DATE.strftime("%Y-%m-%d")}"]',
        f'td[title*="{TARGET_DATE.strftime("%B %-d,")}"]',
        f'td[title*="{TARGET_DATE.strftime("%B %d,")}"]',
        f'[aria-label*="{TARGET_DATE.strftime("%B %-d, %Y")}"]',
        f'.k-calendar td:has-text("{TARGET_DATE.day}")',
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(2000)
                print(f"[date] OK")
                return True
        except Exception:
            pass
    print("[date] ERROR: could not click target day")
    return False


# ── Get reserve buttons from the correct time row ─────────────────────────────

def get_reserve_buttons(page) -> list:
    print(f"\n[book] Finding reserve buttons for: {TARGET_TIME!r}")
    row = page.query_selector(f'tr[data-testid="{TARGET_TIME}"]')
    if not row:
        print(f"[book] ERROR: no row with data-testid='{TARGET_TIME}'")
        return []
    buttons = row.query_selector_all('button[data-testid="reserveBtn"]')
    print(f"[book] Reserve buttons: {len(buttons)}")
    result = []
    for btn in buttons:
        court = (btn.get_attribute("data-courtlabel") or
                 btn.get_attribute("courtlabel") or "Unknown").strip()
        print(f"[book]   → {court!r}")
        result.append((btn, court))
    return result


# ── Fill the booking modal ────────────────────────────────────────────────────

def fill_modal(page, court: str) -> bool:
    print(f"\n[modal] Filling modal ...")
    try:
        page.wait_for_selector('[role="dialog"]', state="visible", timeout=6000)
    except PlaywrightTimeout:
        print("[modal] ERROR: modal not visible")
        return False

    modal = page.query_selector('[role="dialog"]')
    if not modal:
        print("[modal] ERROR: modal not found")
        return False

    # Dump all dropdowns once for reference
    all_dd = modal.query_selector_all('.k-dropdownlist, .k-dropdown-wrap, select, span[aria-haspopup]')
    print(f"[modal] Dropdowns in modal: {len(all_dd)}")
    for i, dd in enumerate(all_dd):
        tag  = dd.evaluate("e => e.tagName").lower()
        text = dd.inner_text().strip().replace("\n", " ")[:70]
        print(f"[modal]   [{i}] <{tag}> '{text}'")

    # ── 1. Duration — dropdown[1] is the Kendo span for duration ─────────────
    # From debug: dropdown[1] tag=span text='1 hour & 30 minutes'
    print(f"\n[modal] Setting duration: {DURATION_LABEL!r}")
    dur_set = False
    # Find the span that currently shows a duration value
    for dd in all_dd:
        tag  = dd.evaluate("e => e.tagName").lower()
        text = dd.inner_text().strip()
        if tag == "span" and any(x in text for x in ["hour", "minute"]):
            print(f"[modal] Duration dropdown current value: {text!r}")
            dur_set = click_kendo_option(page, dd, DURATION_LABEL)
            break
    if not dur_set:
        print(f"[modal] WARNING: duration not set")

    page.wait_for_timeout(400)

    # ── 2. Court — find the visible Kendo multiselect/dropdown for Court(s) ───
    # The Court field is a Kendo widget. Find it by looking for the
    # element near the "Court(s)" label, click it, screenshot options,
    # then pick the first available one.
    print(f"\n[modal] Selecting court ...")
    court_set = False

    # The court widget is a k-multiselect or k-dropdownlist near "Court(s)" text.
    # Try several selectors for the clickable input area of that widget.
    court_widget_selectors = [
        '.k-multiselect',
        '.k-multiselect-wrap',
        '[data-role="multiselect"]',
        '[data-role="dropdownlist"]',
        # Fallback: find by proximity to "Court" label
        'label:has-text("Court") + div',
        'label:has-text("Court") ~ div .k-input',
    ]

    court_widget = None
    for sel in court_widget_selectors:
        el = modal.query_selector(sel)
        if el:
            print(f"[modal] Found court widget via: {sel!r}")
            court_widget = el
            break

    if court_widget:
        # Click it to open the dropdown list
        court_widget.click()
        page.wait_for_timeout(800)
        screenshot(page, "court_dropdown_open")
        print(f"[modal] Court dropdown opened — screenshot saved")

        # Now look for the options that appeared
        option_selectors = [
            'li.k-item',
            '.k-list li',
            '.k-popup li',
            '[role="option"]',
        ]
        for opt_sel in option_selectors:
            opts = page.query_selector_all(opt_sel)
            visible = [(o.inner_text().strip(), o) for o in opts if o.is_visible() and o.inner_text().strip()]
            if visible:
                print(f"[modal] Court options ({opt_sel}):")
                for text, _ in visible:
                    print(f"[modal]   → {text!r}")
                # Click the first one
                first_text, first_el = visible[0]
                first_el.click()
                page.wait_for_timeout(500)
                print(f"[modal] Court selected: {first_text!r}")
                court_set = True
                break

        if not court_set:
            print(f"[modal] WARNING: court dropdown opened but no options found")
            page.keyboard.press("Escape")
    else:
        # Last resort: find hidden <select> and set via Kendo JS API
        print(f"[modal] No visible court widget found — trying Kendo JS API ...")
        for dd in all_dd:
            tag = dd.evaluate("e => e.tagName").lower()
            if tag == "select":
                options = dd.evaluate("""el => Array.from(el.options).map(o => ({
                    value: o.value, text: o.text, disabled: o.disabled
                }))""")
                print(f"[modal] Hidden select options: {[o['text'] for o in options]}")
                chosen = next((o for o in options if o['value'] and not o['disabled']), None)
                if chosen:
                    page.evaluate("""([el, val]) => {
                        const w = kendo.widgetInstance($(el).closest('[data-role]')[0]);
                        if (w) { w.value(val); w.trigger('change'); }
                        else {
                            el.value = val;
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""", [dd, chosen['value']])
                    page.wait_for_timeout(500)
                    print(f"[modal] Court set via JS: {chosen['text']!r}")
                    court_set = True
                break

    if not court_set:
        print(f"[modal] WARNING: court not selected")

    page.wait_for_timeout(400)

    # ── 3. "I understand" — dropdown[5] is Kendo span ────────────────────────
    # From debug: dropdown[5] tag=span text='Select I understand...'
    print(f"\n[modal] Setting 'I understand' to Yes ...")
    understand_set = False
    for dd in all_dd:
        tag  = dd.evaluate("e => e.tagName").lower()
        text = dd.inner_text().strip()
        if tag == "span" and "understand" in text.lower():
            print(f"[modal] Found 'I understand' dropdown: {text[:60]!r}")
            understand_set = click_kendo_option(page, dd, "Yes")
            break
    if not understand_set:
        print(f"[modal] WARNING: 'I understand' not set")

    page.wait_for_timeout(500)

    # ── Screenshot ────────────────────────────────────────────────────────────
    screenshot(page, "modal_filled")

    # ── Close ─────────────────────────────────────────────────────────────────
    print(f"\n[modal] Clicking Close ...")
    for sel in ['button:has-text("Close")', 'button:has-text("Cancel")']:
        el = page.query_selector(sel)
        if el and el.is_visible():
            el.click()
            page.wait_for_timeout(600)
            print(f"[modal] Closed.")
            return True
    page.keyboard.press("Escape")
    return True


# ── Try to open modal for each court ─────────────────────────────────────────

def try_open_modal(page, btn, court: str) -> bool:
    print(f"\n[book] Clicking court: {court!r}")
    try:
        with page.context.expect_event("page", timeout=4000) as new_page_info:
            btn.click()
        popup = new_page_info.value
        popup.wait_for_load_state("networkidle", timeout=20000)
        print(f"[book] Popup window: {popup.url}")
        fill_modal(popup, court)
        return True
    except Exception:
        pass

    page.wait_for_timeout(1500)
    modal = page.query_selector('[role="dialog"]')
    if modal and modal.is_visible():
        print(f"[book] Inline modal opened")
        fill_modal(page, court)
        return True

    print(f"[book] No modal — trying next")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    return False


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        context.route("**/*", block_fonts)
        page = context.new_page()

        if not login(page):
            browser.close()
            sys.exit(1)

        print(f"\n[nav] Loading bookings page ...")
        page.goto(BOOKINGS_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        if not select_date(page):
            browser.close()
            sys.exit(1)

        screenshot(page, "date_selected")

        buttons = get_reserve_buttons(page)
        if not buttons:
            print("[book] No reserve buttons found.")
            browser.close()
            sys.exit(1)

        for btn, court in buttons:
            if try_open_modal(page, btn, court):
                break
        else:
            print("\n[book] All courts failed.")

        browser.close()
        print("\n[done]")


if __name__ == "__main__":
    run()