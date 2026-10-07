"""Read-only test of public calendar access; does not publish a calendar."""
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

URL = 'https://tradingeconomics.com/united-states/calendar'

def extract(page):
    starts = list(re.finditer(r'<tr\b[^>]*\bdata-country="united states"[^>]*>', page, re.I))
    events = []
    for i, match in enumerate(starts):
        attributes = dict(re.findall(r'(data-[\w-]+)="([^"]*)"', match.group()))
        segment = page[match.end():starts[i+1].start() if i+1 < len(starts) else page.find('</table>', match.end())]
        title = re.search(r'<a\b[^>]*class=[\'"]calendar-event[\'"][^>]*>(.*?)</a>', segment, re.S)
        date = re.search(r'<td\b[^>]*class=[\'"][^\'"]*(\d{4}-\d{2}-\d{2})[^\'"]*[\'"]', segment)
        clock = re.search(r'<span\b[^>]*class=[\'"][^\'"]*calendar-date-[^\'"]*[\'"][^>]*>\s*(.*?)\s*</span>', segment, re.S)
        if title and date and clock:
            events.append({'id': attributes.get('data-id'),
                'title': html.unescape(re.sub('<[^>]+>', '', title[1])).strip(),
                'date':date[1], 'time':html.unescape(clock[1]).strip(),
                'category':html.unescape(attributes.get('data-category', ''))})
    return events

def main():
    with urlopen(Request(URL), timeout=45) as response:
        status = response.status
        page = response.read().decode('utf-8')
    events = extract(page)
    if not events or any(not e['id'] for e in events):
        raise RuntimeError('No usable economic calendar events found')
    report = {'tested_at':datetime.now(timezone.utc).isoformat(), 'source':URL,
        'http_status':status, 'event_count':len(events), 'date_range':
        [min(e['date'] for e in events),max(e['date'] for e in events)],
        'fed_speeches':sum('speech' in e['title'].lower() for e in events),
        'michigan_events':sum('michigan' in e['title'].lower() for e in events),
        'nfib_events':sum('nfib' in e['title'].lower() for e in events),
        'events':events}
    Path('tradingeconomics-access-test.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='events'}))

if __name__ == '__main__':
    main()
