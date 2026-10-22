import datetime as dt,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import challenge
class ChallengeTests(unittest.TestCase):
 def test_only_authoritative_complete(self):
  s='今日任务\n已完成\n创作任务\n(1/1)\n互动任务\n(3/3)\n分享'
  self.assertTrue(challenge.parse_progress(s)['completed'])
  self.assertFalse(challenge.parse_progress(s.replace('已完成','未完成'))['completed'])
  self.assertFalse(challenge.parse_progress(s.replace('(3/3)','(2/3)'))['completed'])
  with self.assertRaises(ValueError):challenge.parse_progress('已报名\n登录')
 def test_due_and_no_duplicate(self):
  now=dt.datetime(2026,10,23,20,30,tzinfo=ZoneInfo('Asia/Shanghai'));cfg={'enabled':True,'time':'20:30'}
  self.assertTrue(challenge.due({},now,cfg))
  self.assertFalse(challenge.due({'status':'completed'},now,cfg))
  self.assertFalse(challenge.due({'checks':4},now,cfg))
  self.assertFalse(challenge.due({},now-dt.timedelta(minutes=1),cfg))
  self.assertFalse(challenge.due({'last_checked_at':now.isoformat()},now+dt.timedelta(minutes=29),cfg))
 def test_completion_does_not_launch_agent(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(challenge,'ROOT',Path(tmp)),patch.object(challenge,'probe',return_value={'completed':True,'creation':'1/1','interaction':'3/3'}),patch.object(challenge,'execute_agent') as agent:
   challenge.run({'timezone':'Asia/Shanghai','challenge':{}},True)
   agent.assert_not_called()
 def test_retry_only_verifies_and_model_cannot_claim_success(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(challenge,'ROOT',Path(tmp)),patch.object(challenge,'due',return_value=True),patch.object(challenge,'probe',return_value={'completed':False,'creation':'1/1','interaction':'2/3'}),patch.object(challenge,'execute_agent',return_value={'summary':'已完成','actions':[],'error':''}) as agent:
   cfg={'timezone':'Asia/Shanghai','challenge':{'enabled':True}};challenge.run(cfg);challenge.run(cfg)
   self.assertEqual(agent.call_count,1)
   state=json.loads(next(Path(tmp).glob('reports/*/challenge/state.json')).read_text())
   self.assertEqual(state['status'],'needs_attention')
