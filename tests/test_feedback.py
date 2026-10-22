import base64,contextlib,datetime as dt,io,json,pathlib,sys,tempfile,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'studio'))
import feedback as f,repair_runner as r
from PIL import Image
class FeedbackTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  for module,k,v in [(f,'DB',self.root/'db'),(f,'DATA',self.root/'feedback'),(r,'ROOT',self.root/'live'),(r,'DATA',self.root/'feedback')]:
   patch=mock.patch.object(module,k,v);patch.start();self.addCleanup(patch.stop)
  self.c=f.connect();self.addCleanup(self.c.close);f.init(self.c);self.c.commit()
 def submit(self,**extra):
  with self.c:return f.submit(self.c,{'title':'问题','body':'按钮不清楚','mode':'night',**extra})['id']
 def test_schedule_is_next_shanghai_3am(self):
  due=dt.datetime.fromisoformat(f.due('night'));self.assertGreater(due,dt.datetime.now(dt.timezone.utc));self.assertEqual(due.astimezone(f.ZoneInfo('Asia/Shanghai')).hour,3)
 def test_create_edit_cancel_and_resubmit(self):
  fid=self.submit();self.assertEqual(f.get(self.c,fid)['status'],'scheduled')
  with self.c:f.action(self.c,{'id':fid,'action':'cancel'})
  self.assertEqual(f.get(self.c,fid)['status'],'cancelled');self.submit(id=fid,mode='now');row=f.get(self.c,fid);self.assertEqual(row['status'],'queued');self.assertEqual(row['cancel_requested'],0)
 def test_upload_and_attachment_ownership(self):
  buf=io.BytesIO();Image.new('RGB',(30,20),'green').save(buf,'PNG')
  with self.c:im=f.upload(self.c,{'name':'截图.png','data':base64.b64encode(buf.getvalue()).decode()})
  fid=self.submit(images=[im['id']]);self.assertEqual(len(f.records(self.c)[0]['images']),1)
  with self.assertRaises(ValueError):self.submit(images=[im['id']])
  self.c.rollback()
  with self.assertRaises(ValueError):
   with self.c:f.upload(self.c,{'data':base64.b64encode(b'<svg/>').decode()})
 def test_running_cancel_and_deploy_boundary(self):
  fid=self.submit()
  with self.c:self.c.execute("UPDATE feedback SET status='running' WHERE id=?",(fid,))
  with self.c:f.action(self.c,{'id':fid,'action':'cancel'})
  self.assertEqual(f.get(self.c,fid)['status'],'cancelling')
  with self.assertRaises(r.Cancelled):r.check_cancel(fid)
  with self.c:self.c.execute("UPDATE feedback SET status='deploying' WHERE id=?",(fid,))
  with self.assertRaises(ValueError):
   with self.c:f.action(self.c,{'id':fid,'action':'cancel'})
 def test_scope_and_unique_patch(self):
  stage=self.root/'stage';p=stage/'studio/app.js';p.parent.mkdir(parents=True);p.write_text('one one')
  with self.assertRaises(ValueError):r.patch(stage,[{'path':'private/studio/models.json','find':'one','replace':'two'}])
  with self.assertRaises(ValueError):r.patch(stage,[{'path':'studio/app.js','find':'one','replace':'two'}])
 def test_backend_patch_is_allowed(self):
  stage=self.root/'stage';name='studio/providers.py'
  for base in (stage,r.ROOT):
   p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('old implementation')
  self.assertEqual(r.patch(stage,[{'path':name,'find':'old implementation','replace':'new implementation'}]),[name])
  self.assertEqual((stage/name).read_text(),'new implementation')
 def test_backend_activation_restarts_studio(self):
  with mock.patch.object(r,'export_wiki'),mock.patch.object(r,'health'),mock.patch.object(r.subprocess,'run') as run:
   r.activate(['studio/providers.py']);run.assert_called_once_with(['systemctl','restart','zhihu-studio.service'],check=True,timeout=40)
 def test_backend_deployment_waits_for_jobs(self):
  with self.c:
   self.c.execute('CREATE TABLE jobs(status TEXT)');self.c.execute("INSERT INTO jobs VALUES('running')")
  with self.assertRaises(RuntimeError):r.ensure_idle(['studio/providers.py'])
  r.ensure_idle(['studio/app.js'])
 def rollback_fixture(self):
  fid=self.submit();folder=r.DATA/fid/'1';name='studio/app.js'
  for base,value in [(r.ROOT,'after'),(folder/'stage','after'),(folder/'before','before')]:
   p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value)
  (folder/'manifest.json').write_text(json.dumps({name:{'before':r.digest(folder/'before'/name),'after':r.digest(folder/'stage'/name)}}));return fid,folder,name
 def test_rollback_restores_only_exact_version(self):
  fid,folder,name=self.rollback_fixture()
  with mock.patch.object(r,'export_wiki'),mock.patch.object(r,'health'):r.rollback(fid,folder)
  self.assertEqual((r.ROOT/name).read_text(),'before');self.assertEqual(f.get(self.c,fid)['status'],'reverted')
 def test_rollback_conflict_keeps_new_changes(self):
  fid,folder,name=self.rollback_fixture();(r.ROOT/name).write_text('newer version')
  r.rollback(fid,folder);self.assertEqual((r.ROOT/name).read_text(),'newer version');self.assertEqual(f.get(self.c,fid)['status'],'rollback_conflict')
 def test_deploy_cancel_does_not_change_files(self):
  fid,folder,name=self.rollback_fixture()
  with self.c:self.c.execute('UPDATE feedback SET cancel_requested=1 WHERE id=?',(fid,))
  with self.assertRaises(r.Cancelled):r.deploy(fid,folder,json.loads((folder/'manifest.json').read_text()))
  self.assertEqual((r.ROOT/name).read_text(),'after')
 def test_scheduler_waits_until_due_and_runs_immediate(self):
  self.submit(mode='night')
  with mock.patch.object(r,'repair') as repair:
   self.assertFalse(r.once());repair.assert_not_called()
   fid=self.submit(mode='now');self.assertTrue(r.once());self.assertEqual(repair.call_args[0][0]['id'],fid)
 def test_due_night_feedback_is_processed(self):
  fid=self.submit(mode='night')
  with self.c:self.c.execute('UPDATE feedback SET due_at=? WHERE id=?',((dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=1)).isoformat(),fid))
  with mock.patch.object(r,'repair') as repair:
   self.assertTrue(r.once());self.assertEqual(repair.call_args[0][0]['id'],fid)
 def test_failure_retries_next_night_with_bounded_attempts(self):
  fid=self.submit(mode='now')
  for attempt in range(1,4):
   with self.c:self.c.execute('UPDATE feedback SET due_at=? WHERE id=?',('2000-01-01T00:00:00+00:00',fid))
   with mock.patch.object(r,'repair',side_effect=RuntimeError('test failure')):r.once()
   row=f.get(self.c,fid);self.assertEqual(row['attempts'],attempt);self.assertEqual(row['status'],'scheduled' if attempt<3 else 'failed')

if __name__=='__main__':unittest.main()
