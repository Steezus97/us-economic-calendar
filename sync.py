"""Generate a persistent, subscribable calendar from MarketWatch's rendered table."""
import argparse
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE = "https://www.marketwatch.com/economy-politics/calendar"
ET = ZoneInfo("America/New_York")
# Reads the displayed calendar DOM, including collapsed event details.
EXTRACT = r"""() => {
  const table = document.querySelector('table[class*="Calendar_calendarTable"]');
  if (!table) throw new Error('MarketWatch calendar table not found');
  const events = []; let date = '';
  for (const row of table.querySelectorAll(':scope > tbody > tr')) {
    if (row.className.includes('calendarDateRow')) date = row.textContent.trim();
    if (!row.className.includes('Calendar_eventRow')) continue;
    const details = row.nextElementSibling;
    const metricRows = details?.querySelectorAll('table tr');
    const metrics = metricRows?.[metricRows.length - 1];
    const offset = row.cells.length === 7 ? 1 : 0;
    events.push({date, time: row.cells[offset].textContent.trim(),
      title: row.cells[offset + 1].textContent.trim(),
      description: details?.querySelector('[class*="eventDetailsDescription"]')?.textContent.trim() || '',
      period: (offset ? row.cells[3].textContent.trim() : metrics?.querySelector('td')?.textContent.trim()) || ''});
  }
  return {heading: document.querySelector('h1')?.textContent.trim(),
    timezone: table.querySelector('thead')?.textContent, events};
}"""

def collect():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        response = page.goto(SOURCE, wait_until="domcontentloaded", timeout=60000)
        if response and response.status >= 400:
            raise RuntimeError(f"MarketWatch returned HTTP {response.status}; existing feed preserved")
        page.locator('table[class*="Calendar_calendarTable"]').first.wait_for(timeout=60000)
        result = page.evaluate(EXTRACT)
        browser.close()
        return result

def parse(snapshot, now):
    if "ET" not in snapshot.get("timezone", ""):
        raise ValueError("Expected Eastern Time in MarketWatch calendar")
    if "Economic" not in snapshot.get("heading", "") and "ECONOMIC" not in snapshot.get("heading", ""):
        raise ValueError("Unexpected calendar heading")
    result = []
    for row in snapshot["events"]:
        clean = row["date"].replace(".", "")
        possible = []
        for year in (now.year - 1, now.year, now.year + 1):
            d = datetime.strptime(f"{clean} {year}", "%A, %b %d %Y").replace(tzinfo=ET)
            if d.strftime("%A") == clean.split(",")[0]:
                possible.append(d)
        if not possible:
            raise ValueError(f"Date weekday mismatch: {clean}")
        day = min(possible, key=lambda d: abs((d - now).total_seconds()))
        if abs((day - now).days) > 45:
            raise ValueError("Calendar outside expected rolling date window")
        clock = re.fullmatch(r"(\d{1,2}):(\d{2})\s*(AM|PM)", row["time"], re.I)
        if not clock:
            raise ValueError(f"Unrecognized time {row['time']!r}; refusing to invent a release time")
        hour, minute = int(clock[1]), int(clock[2])
        if not 1 <= hour <= 12 or not 0 <= minute < 60:
            raise ValueError("Invalid clock time")
        start = day.replace(hour=hour % 12 + (12 if clock[3].upper() == "PM" else 0), minute=minute)
        title = " ".join(row["title"].split())
        if not title:
            raise ValueError("Empty event title")
        result.append({"title": title, "period": row.get("period", ""),
                       "description": row.get("description", ""),
                       "start": start.astimezone(timezone.utc).isoformat()})
    if not result:
        raise ValueError("Empty calendar; preserving previous feed")
    return result

def signature(event):
    return hashlib.sha256(json.dumps({k: event[k] for k in
        ("title", "period", "description", "start")}, sort_keys=True).encode()).hexdigest()

def reconcile(incoming, records, now):
    used = set()
    identities = [(e['title'], e['period'], e['start']) for e in incoming]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate input event')
    for event in incoming:
        start = datetime.fromisoformat(event["start"])
        candidates = [(key, old) for key, old in records.items()
                      if key not in used and old["title"] == event["title"]
                      and old["period"] == event["period"]
                      and abs((datetime.fromisoformat(old["start"]) - start).total_seconds()) <=
                      (20 if event["period"] else 14) * 86400]
        if len(candidates) > 1:
            exact = [pair for pair in candidates if pair[1]["start"] == event["start"]]
            if len(exact) != 1:
                raise ValueError(f"Ambiguous identity for {event['title']}; preserving existing feed")
            candidates = exact
        key, old = candidates[0] if candidates else (str(uuid.uuid4()), None)
        if key in used:
            raise ValueError("Duplicate input event")
        used.add(key)
        changed = old is None or signature(old) != signature(event)
        records[key] = {**event, "sequence": (old["sequence"] + 1 if old else 0) if changed else old["sequence"],
                        "modified": now.isoformat() if changed else old["modified"]}
    # Preserve events that disappear from the limited rolling page. Absence is not cancellation.
    return {k: v for k, v in records.items()
            if datetime.fromisoformat(v["start"]) > now - timedelta(days=90)}

def escape(value):
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,").replace("\r", "")

def stamp(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def fold(line):
    parts, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            parts.append(current)
            current = " "
        current += char
    return "\r\n".join(parts + [current])

def calendar(records):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Personal Economic Calendar Sync//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:MarketWatch US Economic Calendar",
             "X-WR-TIMEZONE:America/New_York", "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for key, event in sorted(records.items(), key=lambda p: p[1]["start"]):
        start = datetime.fromisoformat(event["start"])
        description = event["description"] + ("\nReporting period: " + event["period"] if event["period"] else "")
        description += "\nSource: " + SOURCE + "\nEnd time is a 15-minute calendar placeholder."
        lines += ["BEGIN:VEVENT", "UID:" + key + "@marketwatch-personal-sync",
                  "DTSTAMP:" + stamp(event["modified"]), "LAST-MODIFIED:" + stamp(event["modified"]),
                  "SEQUENCE:" + str(event["sequence"]), "DTSTART:" + stamp(event["start"]),
                  "DTEND:" + stamp((start + timedelta(minutes=15)).isoformat()),
                  "SUMMARY:" + escape(event["title"]), "DESCRIPTION:" + escape(description),
                  "URL:" + SOURCE, "TRANSP:TRANSPARENT", "END:VEVENT"]
    return "\r\n".join(map(fold, lines + ["END:VCALENDAR"])) + "\r\n"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, help="Use a saved rendered-table snapshot for validation")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    snapshot = json.loads(args.snapshot.read_text()) if args.snapshot else collect()
    incoming = parse(snapshot, now.astimezone(ET))
    root = Path(__file__).resolve().parent
    state = root / "data/state.json"
    old = json.loads(state.read_text()) if state.exists() else {}
    records = reconcile(incoming, old, now)
    content = calendar(records)
    # Validate everything before replacing any previous successful output.
    state.parent.mkdir(exist_ok=True)
    output = root / "public"
    output.mkdir(exist_ok=True)
    for path, value in [(state, json.dumps(records, indent=2)),
                        (output / "calendar.ics", content),
                        (output / "status.json", json.dumps({"last_success": now.isoformat(), "events_read": len(incoming), "events_in_feed": len(records)}))]:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(value, newline="")
        temporary.replace(path)
    print(f"Read {len(incoming)} events; feed contains {len(records)} events")

if __name__ == "__main__":
    main()
