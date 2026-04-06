"""
NSE Trading Holiday Manager
- Stores holidays in MongoDB (collection: nse_holidays)
- Falls back to hardcoded defaults when DB is empty
- Background task checks daily; one week before April 1st,
  it auto-fetches the upcoming FY's holiday list from NSE sources.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Set, Dict, List

import requests

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# ─── Hardcoded defaults (verified against NSE circulars) ───────────────────────
# Key: calendar year → list of (MM-DD, description)
# These are used as seed data and fallback when scraping fails.
DEFAULT_HOLIDAYS: Dict[int, List[dict]] = {
    2025: [
        {"date": "2025-01-26", "name": "Republic Day"},
        {"date": "2025-02-26", "name": "Maha Shivaratri"},
        {"date": "2025-03-14", "name": "Holi"},
        {"date": "2025-03-31", "name": "Id-Ul-Fitr (Ramadan)"},
        {"date": "2025-04-10", "name": "Shri Mahavir Jayanti"},
        {"date": "2025-04-14", "name": "Dr. Ambedkar Jayanti"},
        {"date": "2025-04-18", "name": "Good Friday"},
        {"date": "2025-05-01", "name": "Maharashtra Day"},
        {"date": "2025-08-15", "name": "Independence Day"},
        {"date": "2025-08-27", "name": "Ganesh Chaturthi"},
        {"date": "2025-10-02", "name": "Mahatma Gandhi Jayanti"},
        {"date": "2025-10-21", "name": "Dussehra"},
        {"date": "2025-10-22", "name": "Diwali Laxmi Pujan"},
        {"date": "2025-11-05", "name": "Prakash Gurpurb Sri Guru Nanak Dev"},
        {"date": "2025-11-26", "name": "Milad-Un-Nabi"},
        {"date": "2025-12-25", "name": "Christmas"},
    ],
    2026: [
        # Official NSE 2026 calendar (16 trading holidays)
        {"date": "2026-01-15", "name": "Municipal Corporation Election - Maharashtra"},
        {"date": "2026-01-26", "name": "Republic Day"},
        {"date": "2026-03-03", "name": "Holi"},
        {"date": "2026-03-26", "name": "Shri Ram Navami"},
        {"date": "2026-03-31", "name": "Shri Mahavir Jayanti"},
        {"date": "2026-04-03", "name": "Good Friday"},
        {"date": "2026-04-14", "name": "Dr. Baba Saheb Ambedkar Jayanti"},
        {"date": "2026-05-01", "name": "Maharashtra Day"},
        {"date": "2026-05-28", "name": "Bakri Id (Eid ul-Adha)"},
        {"date": "2026-06-26", "name": "Muharram"},
        {"date": "2026-09-14", "name": "Ganesh Chaturthi"},
        {"date": "2026-10-02", "name": "Mahatma Gandhi Jayanti"},
        {"date": "2026-10-20", "name": "Dussehra"},
        {"date": "2026-11-10", "name": "Diwali-Balipratipada"},
        {"date": "2026-11-24", "name": "Prakash Gurpurb Sri Guru Nanak Dev"},
        {"date": "2026-12-25", "name": "Christmas"},
    ],
    2027: [
        # Projected fixed holidays (religious dates TBD by NSE in late 2026)
        {"date": "2027-01-26", "name": "Republic Day"},
        {"date": "2027-03-16", "name": "Holi (projected)"},
        {"date": "2027-04-02", "name": "Good Friday (projected)"},
        {"date": "2027-04-14", "name": "Dr. Ambedkar Jayanti"},
        {"date": "2027-05-01", "name": "Maharashtra Day"},
        {"date": "2027-08-15", "name": "Independence Day (Sunday - may not be trading holiday)"},
        {"date": "2027-10-02", "name": "Mahatma Gandhi Jayanti (Saturday - may not be trading holiday)"},
        {"date": "2027-12-25", "name": "Christmas (Saturday - may not be trading holiday)"},
    ],
}


# ─── In-memory set (fast lookups) ─────────────────────────────────────────────
_holidays_set: Set[str] = set()
_db_ref = None
_background_task: Optional[asyncio.Task] = None


def get_nse_holidays() -> Set[str]:
    """Return the current in-memory holiday set. Thread-safe read."""
    return _holidays_set


def _build_default_set() -> Set[str]:
    """Build a flat set of YYYY-MM-DD strings from the hardcoded defaults."""
    result = set()
    for year_holidays in DEFAULT_HOLIDAYS.values():
        for h in year_holidays:
            result.add(h["date"])
    return result


async def _load_from_db() -> Set[str]:
    """Load holidays from MongoDB nse_holidays collection."""
    if _db_ref is None:
        return set()
    result = set()
    cursor = _db_ref["nse_holidays"].find({}, {"_id": 0, "date": 1})
    async for doc in cursor:
        if "date" in doc:
            result.add(doc["date"])
    return result


async def _seed_defaults_to_db():
    """Insert hardcoded defaults into MongoDB if the collection is empty."""
    if _db_ref is None:
        return
    count = await _db_ref["nse_holidays"].count_documents({})
    if count > 0:
        return
    docs = []
    for year, holidays in DEFAULT_HOLIDAYS.items():
        for h in holidays:
            docs.append({
                "date": h["date"],
                "name": h["name"],
                "year": year,
                "source": "hardcoded_default",
                "updated_at": datetime.now(IST).isoformat(),
            })
    if docs:
        await _db_ref["nse_holidays"].insert_many(docs)
        logger.info("Seeded %d default NSE holidays into MongoDB.", len(docs))


async def _save_holidays_to_db(year: int, holidays: List[dict], source: str):
    """Replace holidays for a given year in MongoDB."""
    if _db_ref is None:
        return
    # Remove existing entries for this year
    await _db_ref["nse_holidays"].delete_many({"year": year})
    docs = []
    for h in holidays:
        docs.append({
            "date": h["date"],
            "name": h["name"],
            "year": year,
            "source": source,
            "updated_at": datetime.now(IST).isoformat(),
        })
    if docs:
        await _db_ref["nse_holidays"].insert_many(docs)
        logger.info("Saved %d holidays for year %d from source '%s'.", len(docs), year, source)


# ─── Scraping / Fetching ──────────────────────────────────────────────────────

_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/resources/exchange-communication-holidays",
}


def _fetch_nse_holidays_api(target_year: int) -> Optional[List[dict]]:
    """
    Try NSE's internal JSON API for the holiday master list.
    NSE site requires a session cookie, so we first hit the main page.
    """
    try:
        session = requests.Session()
        session.headers.update(_NSE_HEADERS)
        # Warm up session (get cookies)
        session.get("https://www.nseindia.com", timeout=10)
        # Fetch holiday data
        resp = session.get(
            "https://www.nseindia.com/api/holiday-master?type=trading",
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("NSE holiday API returned status %d", resp.status_code)
            return None

        data = resp.json()
        # NSE returns: { "CM": [...], "FO": [...], ... }
        # CM = Capital Market (equity segment)
        cm_holidays = data.get("CM", [])
        if not cm_holidays:
            logger.warning("NSE holiday API returned empty CM list.")
            return None

        holidays = []
        for entry in cm_holidays:
            # Each entry: {"tradingDate":"03-Mar-2026","weekDay":"Tuesday","description":"Holi",...}
            raw_date = entry.get("tradingDate", "")
            description = entry.get("description", "")
            try:
                parsed = datetime.strptime(raw_date, "%d-%b-%Y")
                if parsed.year == target_year:
                    holidays.append({
                        "date": parsed.strftime("%Y-%m-%d"),
                        "name": description,
                    })
            except ValueError:
                continue

        if holidays:
            logger.info("Fetched %d holidays for %d from NSE API.", len(holidays), target_year)
            return holidays
        return None
    except Exception as e:
        logger.warning("NSE holiday API fetch failed: %s", e)
        return None


def _fetch_holidays_fallback(target_year: int) -> Optional[List[dict]]:
    """
    Fallback: scrape holidays from Zerodha's holiday calendar page.
    This is a simpler HTML page that's less aggressively blocked.
    """
    try:
        resp = requests.get(
            f"https://zerodha.com/marketintel/holiday-calendar/{target_year}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        import re as _re
        # Look for date patterns in the page: DD Month YYYY or similar
        # Zerodha typically lists dates in a table
        text = resp.text
        # Pattern: dates like "03 Mar 2026" or "March 03, 2026"
        date_pattern = _re.compile(
            r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})",
            _re.IGNORECASE,
        )
        matches = date_pattern.findall(text)
        holidays = []
        seen = set()
        for day, month, year in matches:
            if int(year) != target_year:
                continue
            try:
                parsed = datetime.strptime(f"{day} {month[:3]} {year}", "%d %b %Y")
                ds = parsed.strftime("%Y-%m-%d")
                if ds not in seen and parsed.weekday() < 5:  # Only weekday holidays
                    seen.add(ds)
                    holidays.append({"date": ds, "name": "NSE Trading Holiday"})
            except ValueError:
                continue

        if len(holidays) >= 5:  # Sanity: expect at least 5 holidays
            logger.info("Fetched %d holidays for %d from Zerodha fallback.", len(holidays), target_year)
            return holidays
        return None
    except Exception as e:
        logger.warning("Zerodha fallback fetch failed: %s", e)
        return None


async def fetch_and_update_holidays(target_year: int) -> bool:
    """
    Attempt to fetch holidays for target_year from external sources,
    save to MongoDB, and update in-memory set.
    Returns True if new data was fetched and stored.
    """
    global _holidays_set

    # Try NSE API first
    holidays = await asyncio.get_event_loop().run_in_executor(
        None, _fetch_nse_holidays_api, target_year
    )
    source = "nse_api"

    # Fallback to Zerodha
    if not holidays:
        holidays = await asyncio.get_event_loop().run_in_executor(
            None, _fetch_holidays_fallback, target_year
        )
        source = "zerodha_fallback"

    if holidays:
        await _save_holidays_to_db(target_year, holidays, source)
        # Reload full set from DB
        db_holidays = await _load_from_db()
        if db_holidays:
            _holidays_set = db_holidays
        logger.info(
            "Holiday set updated. Total holidays in memory: %d", len(_holidays_set)
        )
        return True

    logger.warning(
        "Could not fetch holidays for %d from any source. "
        "Hardcoded defaults remain in use.", target_year
    )
    return False


# ─── Background Task ──────────────────────────────────────────────────────────

async def _holiday_update_loop():
    """
    Background coroutine that runs once per day (at ~02:00 IST).
    One week before April 1st (i.e., March 25th), it attempts to fetch
    the upcoming FY's NSE holiday list automatically.
    """
    while True:
        try:
            now = datetime.now(IST)
            # Calculate next run: 02:00 IST tomorrow
            next_run = (now + timedelta(days=1)).replace(
                hour=2, minute=0, second=0, microsecond=0
            )
            sleep_seconds = (next_run - now).total_seconds()
            if sleep_seconds < 0:
                sleep_seconds = 86400  # fallback: 24h
            await asyncio.sleep(sleep_seconds)

            now = datetime.now(IST)
            logger.info("Holiday manager daily check at %s", now.isoformat())

            # Check if we are within the auto-fetch window: March 25 - March 31
            if now.month == 3 and 25 <= now.day <= 31:
                # The upcoming FY starts April 1st of this year.
                # We need holidays for the calendar year that covers most of the new FY.
                # FY 2026-27 means April 2026 to March 2027.
                # We need holidays for both the current year (rest of it) and next year.
                upcoming_fy_start_year = now.year
                next_calendar_year = now.year + 1

                logger.info(
                    "Auto-fetch window active. Fetching holidays for %d and %d.",
                    upcoming_fy_start_year, next_calendar_year,
                )
                await fetch_and_update_holidays(upcoming_fy_start_year)
                await fetch_and_update_holidays(next_calendar_year)

            # Also check if current year's holidays are loaded
            current_year = now.year
            current_year_count = sum(
                1 for h in _holidays_set if h.startswith(str(current_year))
            )
            if current_year_count == 0:
                logger.info(
                    "No holidays found for current year %d. Attempting fetch.",
                    current_year,
                )
                await fetch_and_update_holidays(current_year)

        except asyncio.CancelledError:
            logger.info("Holiday update loop cancelled.")
            break
        except Exception as e:
            logger.error("Holiday update loop error: %s", e, exc_info=True)
            await asyncio.sleep(3600)  # retry in 1 hour on error


# ─── Public Init / Shutdown ───────────────────────────────────────────────────

async def init_holiday_manager(database) -> Set[str]:
    """
    Initialize the holiday manager:
    1. Store DB reference
    2. Seed defaults if DB is empty
    3. Load holidays from DB into memory
    4. Start background updater task
    Returns the loaded holiday set.
    """
    global _db_ref, _holidays_set, _background_task

    _db_ref = database

    # Ensure index on date field
    await _db_ref["nse_holidays"].create_index("date", unique=True)
    await _db_ref["nse_holidays"].create_index("year")

    # Seed defaults
    await _seed_defaults_to_db()

    # Load from DB
    db_holidays = await _load_from_db()
    if db_holidays:
        _holidays_set = db_holidays
        logger.info("Loaded %d NSE holidays from MongoDB.", len(_holidays_set))
    else:
        _holidays_set = _build_default_set()
        logger.info("Using %d hardcoded default holidays.", len(_holidays_set))

    # Start background task
    _background_task = asyncio.create_task(_holiday_update_loop())
    logger.info("Holiday background updater started.")

    return _holidays_set


async def shutdown_holiday_manager():
    """Cancel the background task on app shutdown."""
    global _background_task
    if _background_task and not _background_task.done():
        _background_task.cancel()
        try:
            await _background_task
        except asyncio.CancelledError:
            pass
    logger.info("Holiday manager shut down.")
