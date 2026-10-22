import datetime as dt, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import scheduler
class ScheduleTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.cfg={'timezone':'Asia/Shanghai','windows':[{'id':i,'label':i,'start':s,'end':e} for i,s,e in [('morning','08:00','11:00'),('noon','12:00','14:00'),('evening','18:00','21:00')]]}
 def test_persisted_random_times(self):
  p=scheduler.plan(self.root,dt.date(2026,10,23),self.cfg)
  with patch('scheduler.secrets.randbelow',side_effect=AssertionError('must not redraw')):
   self.assertEqual(p,scheduler.plan(self.root,dt.date(2026,10,23),self.cfg))
  for s in p['slots']:self.assertTrue(s['start']<=s['publish_at']<s['end'])
 def test_no_late_catchup_or_retry_uncertain(self):
  s=scheduler.plan(self.root,dt.date(2026,10,23),self.cfg)['slots'][0]
  self.assertEqual(scheduler.action(s,dt.datetime.fromisoformat(s['end'])),'missed')
  s['status']='publishing';self.assertEqual(scheduler.action(s,dt.datetime.fromisoformat(s['start'])),'interrupted')
  s['status']='failed';self.assertIsNone(scheduler.action(s,dt.datetime.fromisoformat(s['end'])))
 def test_prepare_then_wait_then_publish(self):
  s=scheduler.plan(self.root,dt.date(2026,10,23),self.cfg)['slots'][0]
  self.assertEqual(scheduler.action(s,dt.datetime.fromisoformat(s['prepare_at'])),'prepare')
  s['status']='ready';self.assertIsNone(scheduler.action(s,dt.datetime.fromisoformat(s['prepare_at'])))
  self.assertEqual(scheduler.action(s,dt.datetime.fromisoformat(s['publish_at'])),'publish')
 def test_overlap_rejected(self):
  self.cfg['windows'][1]['start']='10:00'
  with self.assertRaises(ValueError):scheduler.plan(self.root,dt.date(2026,10,23),self.cfg)
