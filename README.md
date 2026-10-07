# US economic calendar sync

A public Apple Calendar subscription containing Trading Economics United States events with two or three stars (medium or high importance).

Subscribe to https://steezus97.github.io/us-economic-calendar/calendar.ics using Apple Calendar → File → New Calendar Subscription. Choose iCloud as the location and an hourly or daily refresh. Importing the file once does not subscribe to updates.

GitHub Actions checks the public US calendar daily at 10:17 UTC and publishes the feed through GitHub Pages. Your Mac does not need to be available. Apple fetches changes according to its subscription refresh setting; scheduled GitHub runs can be delayed.

The collector validates the source timezone as UTC. Apple displays events in your calendar's timezone. Entries include a reminder 30 minutes before each release, have a 15-minute placeholder duration, and do not mark you busy. In Apple Calendar subscription settings, uncheck Remove: Alerts to receive the reminders. Source event IDs preserve the same calendar identity across title/time changes. Events downgraded to one star are removed. Events missing from the rolling source window are retained for up to 90 days because absence does not prove cancellation.

If fetching or parsing fails, the previous published feed remains available. Monitor `status.json` at the same base URL for the last successful update. Public page availability and markup may change. No Trading Economics API key or Apple credentials are used.

Run with Python 3.12+: `python -m unittest discover -s tests -v`, then `python sync.py`. `--snapshot path/to/source.html` supports offline validation.

The active feed uses Trading Economics.
