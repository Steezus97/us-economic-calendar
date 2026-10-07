# MarketWatch → Apple Calendar

Personal hosted calendar feed. A GitHub Actions job reads MarketWatch's rendered economic calendar daily at 10:17 UTC (5:17 a.m. Central daylight time / 4:17 a.m. Central standard time), then publishes `public/calendar.ics` with GitHub Pages. Scheduled runs may be delayed by GitHub; public-repository schedules can be disabled after 60 days without repository activity. This job normally commits daily after a successful read.

Subscribe on Mac: Calendar → File → New Calendar Subscription. Paste the hosted HTTPS `calendar.ics` URL, choose iCloud as the location, and set auto-refresh to every hour. Importing a downloaded file does not provide ongoing synchronization. Apple refreshes independently of the daily collector, so updates can take additional time to appear.

## Behavior

- Adds newly listed events and retains stable UIDs when a matched event's time or description changes.
- Interprets source times in America/New_York, including daylight saving time, and publishes UTC timestamps.
- Matches the exact report title and reporting period within 20 days (14 days without a reporting period). Ambiguous matches stop publication. A changed report title cannot always be recognized as the same event and may create a new entry.
- Keeps events that leave the rolling page; disappearance is not treated as cancellation. Retains 90 days of history.
- Uses 15-minute placeholder durations and leaves your calendar availability free.
- Stops on access errors, unrecognized dates/times, empty results, or unexpected page structure. The existing hosted feed stays published. GitHub Actions reports failed runs through your configured GitHub notification settings.
- Only captures MarketWatch's current default rolling window, not an entire year's future events.

## Hosting

Create a GitHub repository containing these files, enable Settings → Pages → GitHub Actions, and run **Refresh economic calendar** manually once. Use the resulting Pages URL with `/calendar.ics` appended. Verify the first live run succeeds before subscribing. No Apple password or access to personal calendar contents is needed. Repository code and the derived event feed will be public when using a public repository.

MarketWatch can restrict automated access, including from cloud runners. Browser access working on a Mac does not establish that GitHub's runner can read it. This project does not bypass login challenges or access controls. If cloud access fails, an authorized data feed or another source is needed for unattended hosting.

## Validation

`python -m unittest discover -s tests -v`

`python sync.py` requires Playwright and Chromium. Set `MARKETWATCH_BROWSER_CHANNEL=chrome` to use an installed Google Chrome instead. The GitHub runner uses its preinstalled Chrome. `python sync.py --snapshot snapshot.json` validates the transformation using a saved table snapshot; it is not a live sync.
