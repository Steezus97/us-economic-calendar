"""Publish US Trading Economics events with importance 2 or 3."""
import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE = "https://tradingeconomics.com/united-states/calendar"

class Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.rows = []
        self.depth = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr' and not self.depth and 'data-country' in attrs:
            self.depth = 1
            self.attributes = attrs
            self.parts = []
        elif self.depth:
            if tag == 'tr': self.depth += 1
            self.parts.append(self.get_starttag_text())
    def handle_endtag(self, tag):
        if not self.depth: return
        if tag == 'tr':
            self.depth -= 1
            if not self.depth:
                self.rows.append((self.attributes, ''.join(self.parts)))
                return
        self.parts.append('</' + tag + '>')
    def handle_data(self, data):
        if self.depth: self.parts.append(data)
    def handle_entityref(self, name):
        self.handle_data('&' + name + ';')
    def handle_charref(self, name):
        self.handle_data('&#' + name + ';')

def clean(value):
    return ' '.join(html.unescape(re.sub('<[^>]+>', '', value)).split())

def parse(page):
    if not re.search(r'<option\b(?=[^>]*selected)(?=[^>]*value=[\'"]0[\'"])[^>]*>UTC</option>', page):
        raise ValueError('Expected source timezone UTC; preserving existing feed')
    parser = Rows(); parser.feed(page)
    events = []
    for attrs, row in parser.rows:
        if attrs['data-country'].lower() != 'united states': continue
        title = re.search(r'<a\b[^>]*class=[\'"]calendar-event[\'"][^>]*>(.*?)</a>', row, re.S)
        if not title:
            title = re.search(r'<span>(.*?)</span>\s*<span[^>]*class=[\'"]calendar-reference', row, re.S)
        day = re.search(r'<td\b[^>]*class=[\'"][^\'"]*(\d{4}-\d{2}-\d{2})[^\'"]*[\'"]', row)
        clock = re.search(r'<span\b[^>]*class=[\'"][^\'"]*calendar-date-([123])[^\'"]*[\'"][^>]*>(.*?)</span>', row, re.S)
        if not title or not day or not clock or not attrs.get('data-id','').isdigit():
            raise ValueError('Unrecognized calendar row; preserving existing feed')
        impact = int(clock[1])
        if impact not in (2,3):
            events.append({'id':attrs['data-id'], 'excluded':True})
            continue
        time = clean(clock[2])
        start = datetime.strptime(day[1] + ' ' + time, '%Y-%m-%d %I:%M %p').replace(tzinfo=timezone.utc)
        period = re.search(r'<span[^>]*class=[\'"]calendar-reference[\'"][^>]*>(.*?)</span>', row, re.S)
        events.append({'id':attrs['data-id'], 'title':clean(title[1]), 'period':clean(period[1]) if period else '',
            'description':f'Impact: {impact} stars', 'impact':impact, 'start':start.isoformat()})
    if not any(not e.get('excluded') for e in events):
        raise ValueError('Empty filtered calendar; preserving existing feed')
    return events

def collect():
    with urlopen(Request(SOURCE), timeout=45) as response:
        return response.read().decode('utf-8')

def signature(event):
    return hashlib.sha256(json.dumps({k:event[k] for k in ('title','period','description','start')},sort_keys=True).encode()).hexdigest()

def reconcile(incoming, records, now):
    records = dict(records)
    ids = [e['id'] for e in incoming]
    if len(set(ids)) != len(ids): raise ValueError('Duplicate source ID')
    for event in incoming:
        key = 'te-' + event['id']
        if event.get('excluded'):
            records.pop(key, None)
            continue
        old = records.get(key)
        changed = old is None or signature(old) != signature(event)
        records[key] = {**event, 'sequence':(old['sequence'] + 1 if old else 0) if changed else old['sequence'],
            'modified':now.isoformat() if changed else old['modified']}
    return {k:v for k,v in records.items() if k.startswith('te-') and datetime.fromisoformat(v['start']) > now-timedelta(days=90)}

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
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:US Economic Calendar (2–3 stars)",
             "X-WR-TIMEZONE:America/New_York", "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for key, event in sorted(records.items(), key=lambda p: p[1]["start"]):
        start = datetime.fromisoformat(event["start"])
        description = event["description"] + ("\nReporting period: " + event["period"] if event["period"] else "")
        description += "\nSource: " + SOURCE + "\nEnd time is a 15-minute calendar placeholder."
        lines += ["BEGIN:VEVENT", "UID:" + key + "@tradingeconomics-personal-sync",
                  "DTSTAMP:" + stamp(event["modified"]), "LAST-MODIFIED:" + stamp(event["modified"]),
                  "SEQUENCE:" + str(event["sequence"]), "DTSTART:" + stamp(event["start"]),
                  "DTEND:" + stamp((start + timedelta(minutes=15)).isoformat()),
                  "SUMMARY:" + escape(event["title"]), "DESCRIPTION:" + escape(description),
                  "URL:" + SOURCE, "TRANSP:TRANSPARENT", "END:VEVENT"]
    return "\r\n".join(map(fold, lines + ["END:VCALENDAR"])) + "\r\n"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, help='Read saved source HTML')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    incoming = parse(args.snapshot.read_text() if args.snapshot else collect())
    root = Path(__file__).resolve().parent
    state = root / 'data/state.json'
    records = reconcile(incoming, json.loads(state.read_text()) if state.exists() else {}, now)
    content = calendar(records)
    state.parent.mkdir(exist_ok=True)
    output = root / 'public'; output.mkdir(exist_ok=True)
    status = {'last_success':now.isoformat(), 'source':SOURCE, 'country':'United States', 'importance':[2,3],
        'events_read':sum(not e.get('excluded') for e in incoming), 'events_in_feed':len(records)}
    for path, value in [(state,json.dumps(records,indent=2)),(output/'calendar.ics',content),(output/'status.json',json.dumps(status))]:
        temporary = path.with_suffix(path.suffix+'.tmp')
        temporary.write_text(value,newline=''); temporary.replace(path)
    print(json.dumps(status))

if __name__ == '__main__': main()
