import unittest
from datetime import datetime, timezone
import sync

class SyncTests(unittest.TestCase):
    def row(self, ident, country='united states', impact=2, time='12:30 PM', linked=True):
        title="<a class='calendar-event'>CPI</a>" if linked else '<span>CPI</span>'
        return f'''<tr data-id="{ident}" data-country="{country}"><td class=' 2026-10-14'><span class="event-7 calendar-date-{impact}">{time}</span></td><td><table><tr><td>US</td></tr></table></td><td>{title}<span class="calendar-reference">SEP</span></td></tr>'''
    def page(self,*rows):
        return '<option selected="selected" value="0">UTC</option><table>'+''.join(rows)+'</table>'
    def test_filter_and_final_nested_row(self):
        events=sync.parse(self.page(self.row(1,impact=1),self.row(2,impact=2),self.row(3,impact=3,linked=False),self.row(4,country='canada')))
        state=sync.reconcile(events,{},datetime.now(timezone.utc))
        self.assertEqual(set(state),{'te-2','te-3'})
        self.assertEqual(state['te-3']['title'],'CPI')
    def test_updates_keep_uid_and_increment_sequence(self):
        now=datetime(2026,10,7,tzinfo=timezone.utc)
        event=sync.parse(self.page(self.row(2)))[0]
        state=sync.reconcile([event],{},now)
        self.assertEqual(sync.reconcile([event],state,now)['te-2']['sequence'],0)
        event={**event,'start':'2026-10-15T13:30:00+00:00','title':'CPI revised'}
        state=sync.reconcile([event],state,now)
        self.assertEqual(state['te-2']['sequence'],1)
        self.assertIn('UID:te-2@tradingeconomics-personal-sync',sync.calendar(state))
    def test_downgrade_removed_missing_preserved(self):
        now=datetime(2026,10,7,tzinfo=timezone.utc)
        state=sync.reconcile(sync.parse(self.page(self.row(2))),{},now)
        self.assertEqual(len(sync.reconcile([],state,now)),1)
        self.assertEqual(sync.reconcile([{'id':'2','excluded':True}],state,now),{})
    def test_utc_and_fail_closed(self):
        page=self.page(self.row(2))
        self.assertEqual(sync.parse(page)[0]['start'],'2026-10-14T12:30:00+00:00')
        for invalid in [page.replace('>UTC<','>EST<'), self.page(self.row(2,time='TBA')),self.page(self.row(2,impact=1))]:
            with self.assertRaises(ValueError):sync.parse(invalid)
    def test_duplicate_ids(self):
        with self.assertRaises(ValueError):sync.reconcile(sync.parse(self.page(self.row(2),self.row(2))),{},datetime.now(timezone.utc))
    def test_alarms_update_existing_and_retained_events(self):
        now=datetime(2026,10,7,tzinfo=timezone.utc)
        events=sync.parse(self.page(self.row(2),self.row(3)))
        state=sync.reconcile(events,{},now)
        for event in state.values():event.pop('alarm_minutes')
        state=sync.reconcile(events[:1],state,now)
        self.assertTrue(all(e['sequence']==1 for e in state.values()))
        content=sync.calendar(state)
        self.assertEqual(content.count('BEGIN:VALARM'),2)
        self.assertEqual(content.count('TRIGGER:-PT30M'),2)
        state=sync.reconcile(events,state,now)
        self.assertTrue(all(e['sequence']==1 for e in state.values()))

    def test_unicode_folding(self):
        line='SUMMARY:'+sync.escape('é'*100+',;\n')
        folded=sync.fold(line)
        self.assertTrue(all(len(p.encode())<=75 for p in folded.split('\r\n')))
        self.assertEqual(folded.replace('\r\n ',''),line)

if __name__=='__main__':unittest.main()
