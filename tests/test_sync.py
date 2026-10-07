import unittest
from datetime import datetime, timezone
import sync

class SyncTests(unittest.TestCase):
    def event(self, date="2026-10-14T12:30:00+00:00", title="CPI", period="Sep"):
        return {"title": title, "period": period, "description": "Inflation", "start": date}

    def test_repeat_and_reschedule_preserve_uid(self):
        now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        state = sync.reconcile([self.event()], {}, now)
        key = next(iter(state))
        state = sync.reconcile([self.event()], state, now)
        self.assertEqual(state[key]["sequence"], 0)
        state = sync.reconcile([self.event("2026-10-15T13:30:00+00:00")], state, now)
        self.assertEqual(list(state), [key])
        self.assertEqual(state[key]["sequence"], 1)

    def test_weekly_periods_stay_separate(self):
        now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        state = sync.reconcile([self.event(title="Claims", period="Oct. 3"),
            self.event("2026-10-21T12:30:00+00:00", "Claims", "Oct. 10")], {}, now)
        self.assertEqual(len(state), 2)

    def test_missing_event_is_retained(self):
        now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        state = sync.reconcile([self.event()], {}, now)
        self.assertEqual(len(sync.reconcile([], state, now)), 1)

    def test_dst_and_year_rollover(self):
        for date, now, expected in [("Wednesday, Oct. 14", datetime(2026,10,7,tzinfo=sync.ET), "12:30"),
            ("Wednesday, Nov. 4", datetime(2026,11,1,tzinfo=sync.ET), "13:30"),
            ("Friday, Jan. 1", datetime(2026,12,30,tzinfo=sync.ET), "13:30")]:
            snapshot = {"heading":"U.S. Economic Calendar", "timezone":"Time (ET)",
                "events":[{"date":date,"time":"8:30 AM","title":"CPI"}]}
            event = sync.parse(snapshot, now)[0]
            self.assertIn(expected, event["start"])
        self.assertTrue(event["start"].startswith("2027-01-01"))

    def test_unknown_time_fails(self):
        with self.assertRaises(ValueError):
            sync.parse({"heading":"Economic Calendar", "timezone":"ET", "events":[
                {"date":"Wednesday, Oct. 14","time":"TBA","title":"CPI"}]},
                datetime(2026,10,7,tzinfo=sync.ET))

    def test_unicode_folding_and_escaping(self):
        line = "SUMMARY:" + sync.escape("é" * 100 + ",;\n")
        folded = sync.fold(line)
        self.assertTrue(all(len(p.encode()) <= 75 for p in folded.split("\r\n")))
        self.assertEqual(folded.replace("\r\n ", ""), line)

if __name__ == "__main__":
    unittest.main()
