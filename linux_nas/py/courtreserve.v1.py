"""
CourtReserve Automation
Goal for now: find "Reserve {TIME}" cell in the grid and open the booking popup.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

LOGIN_URL      = "https://app.courtreserve.com/Online/Account/LogIn/10738"
BOOKINGS_URL   = "https://app.courtreserve.com/Online/Reservations/Bookings/10738?sId=16007"
SCREENSHOT_DIR = Path("/config/scripts/py/screenshots")

EMAIL    = os.getenv("COURT_EMAIL", "")
PASSWORD = os.getenv("COURT_PASSWORD", "")
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"

_date_env = os.getenv("DATE", "").strip()
TARGET_DATE = datetime.strptime(_date_env, "%Y%m%d") if _date_env else datetime.now() + timedelta(weeks=1)
print(f"[config] Date: {TARGET_DATE.strftime('%B %d, %Y')}")

_time_env = os.getenv("TIME", "0800 PM").strip()
_t    = _time_env.replace(" ", "")
_ampm = _t[-2:].upper()
_hhmm = _t[:-2].zfill(4)
TARGET_TIME = f"{int(_hhmm[:2])}:{_hhmm[2:]} {_ampm}"
print(f"[config] Time: {TARGET_TIME}")

DURATION = int(os.getenv("DURATION", "1"))
print(f"[config] Duration: {DURATION}h")


def screenshot(page, name):
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=False, timeout=8000)
        print(f"[screenshot] → {path}")
    except Exception as e:
        print(f"[screenshot] SKIPPED: {e}")


def block_fonts(route):
    if "fonts.googleapis.com" in route.request.url or \
       "fonts.gstatic.com"    in route.request.url or \
       route.request.resource_type == "font":
        route.abort()
    else:
        route.continue_()


def login(page) -> bool:
    print(f"[login] → {LOGIN_URL}")
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
        print(f"[login] OK — {page.url}")
        return True
    except PlaywrightTimeout:
        print("[login] FAILED")
        return False


def select_date(page) -> bool:
    print(f"[date] Selecting {TARGET_DATE.strftime('%B %d, %Y')} ...")
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
                print(f"[date] Clicking via {sel!r}")
                el.click()
                page.wait_for_timeout(2000)
                return True
        except Exception:
            pass

    print("[date] ERROR: could not click target day")
    return False


def find_and_click_reserve_cell(page) -> bool:
    """
    The grid has rows = time slots, columns = courts.
    Each bookable cell contains text like "Reserve 8:00 PM".
    Find the first such cell for our target time and click it.
    """
    reserve_label = f"Reserve {TARGET_TIME}"
    print(f"\n[book] Looking for cell: {reserve_label!r}")

    # Wait for the schedule grid to be present
    try:
        page.wait_for_selector("table", timeout=10000)
    except PlaywrightTimeout:
        print("[book] ERROR: no table found on page")
        return False

    # Use Playwright's text locator to find the exact cell
    # This matches any element whose visible text is exactly our label
    candidates = page.locator(f'td:has-text("{reserve_label}")')
    count = candidates.count()
    print(f"[book] Cells matching {reserve_label!r}: {count}")

    if count == 0:
        # Fallback: try partial match
        candidates = page.locator(f':text("{TARGET_TIME}")')
        count = candidates.count()
        print(f"[book] Cells with partial match '{TARGET_TIME}': {count}")

    if count == 0:
        print("[book] ERROR: no matching cells found.")
        # Dump the first few rows to help debug
        rows = page.query_selector_all("tr")
        print(f"[book] Table rows found: {len(rows)}")
        for i, row in enumerate(rows[:30]):
            try:
                t = row.inner_text().replace("\t", " | ").replace("\n", " ").strip()
                if t:
                    print(f"  row[{i:2d}]: {t[:120]}")
            except Exception:
                pass
        return False

    # Walk through matches left→right (first available = leftmost court)
    for i in range(count):
        cell = candidates.nth(i)
        cell_text = cell.inner_text().strip()

        # Find which court column this cell belongs to by checking the column header
        # We use JavaScript to walk up to the row and get the cell index
        col_index = cell.evaluate("""el => {
            const row = el.closest('tr');
            if (!row) return -1;
            return Array.from(row.children).indexOf(el);
        }""")

        # Get the header cell at the same column index
        court_name = page.evaluate(f"""() => {{
            const headers = document.querySelectorAll('thead tr th, thead tr td');
            if (headers[{col_index}]) return headers[{col_index}].innerText.trim();
            return 'Unknown Court';
        }}""")

        print(f"[book] Cell[{i}]: col={col_index} court={court_name!r} text={cell_text!r}")

        # Skip if it's not actually clickable (double-check text)
        if "Reserve" not in cell_text:
            print(f"[book]   → Skipping (no 'Reserve' in text)")
            continue

        print(f"[book] → Clicking cell for court: {court_name!r}")

        # Click and wait for popup
        try:
            with page.context.expect_event("page", timeout=6000) as new_page_info:
                cell.click()
            popup = new_page_info.value
            popup.wait_for_load_state("networkidle", timeout=20000)
            print(f"[book] ✓ Popup opened: {popup.url}")
            screenshot(popup, "booking_popup")
            print(f"[book] Popup content preview:")
            print(popup.inner_text("body")[:800])
            # Keep popup open — next step will handle filling the form
            return True

        except PlaywrightTimeout:
            print(f"[book]   No popup — checking for inline modal ...")

        page.wait_for_timeout(1500)
        screenshot(page, "after_cell_click")

        # Check for inline modal
        for modal_sel in ['.ant-modal-content', '.k-window-content', '[role="dialog"]']:
            modal = page.query_selector(modal_sel)
            if modal and modal.is_visible():
                print(f"[book] ✓ Inline modal found: {modal_sel}")
                print(f"[book] Modal text:\n{modal.inner_text()[:800]}")
                screenshot(page, "booking_modal")
                return True

        print(f"[book]   No modal found after click — trying next cell")

    print("[book] ERROR: clicked all candidates but no popup/modal appeared")
    return False


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

        print(f"\n[nav] → {BOOKINGS_URL}")
        page.goto(BOOKINGS_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)
        screenshot(page, "bookings_loaded")

        if not select_date(page):
            browser.close()
            sys.exit(1)

        screenshot(page, "date_selected")
        find_and_click_reserve_cell(page)

        input("\n[done] Press Enter to close browser ...")
        browser.close()


if __name__ == "__main__":
    run()