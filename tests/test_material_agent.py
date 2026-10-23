import pathlib,tempfile,unittest,json,datetime as dt
from unittest.mock import patch,Mock
import material_agent as agent
class MaterialAgentTests(unittest.TestCase):
 def test_domains(self):
  self.assertTrue(agent.site_matches('https://www.moyuoo.com/a','https://moyuoo.com/'))
  self.assertFalse(agent.site_matches('https://moyuoo.com.attacker.test/a','https://moyuoo.com/'))
 def test_auth_and_endpoint(self):
  response=Mock(status_code=200);response.json.return_value={'results':[]}
  with patch.object(agent.collector.providers,'load',return_value={'providers':[{'id':'deepseek','key':'test-secret'}]}),patch.object(agent.requests,'post',return_value=response) as post:
   self.assertEqual(agent.search('梗'),[])
   self.assertEqual(post.call_args.args[0],'https://api.deepseek.com/v1/tools/search')
   self.assertFalse(post.call_args.kwargs['allow_redirects'])
 def test_failed_auth_is_not_retried_or_leaked(self):
  with patch.object(agent.collector.providers,'load',return_value={'providers':[{'id':'deepseek','key':'test-secret'}]}),patch.object(agent.requests,'post',return_value=Mock(status_code=401)) as post:
   with self.assertRaisesRegex(RuntimeError,'HTTP 401'):agent.search('梗')
   self.assertEqual(post.call_count,1)
 def test_fetch_rejects_block_page(self):
  with patch.object(agent,'call_api',return_value={'content':'验证码'+'x'*120}),patch.object(agent,'fetch_html',side_effect=ValueError('blocked')):
   with self.assertRaises(ValueError):agent.fetch('https://example.com')
 def test_site_checks_do_not_assert_current_activity(self):
  with patch.object(agent,'fetch_known',return_value={'title':'词典','text':'释义页面'}),patch.object(agent,'search',return_value=[{'url':'https://moyuoo.com/123','date':'2020-01-01'}]):
   result=agent.check_site({'url':'https://moyuoo.com/','name':'词典'})
   self.assertEqual(result['status'],'可访问');self.assertIn('未核实',result['update_status'])
 def test_repurposed_sites_are_excluded(self):
  with patch.object(agent,'fetch_known',return_value={'title':'正规配资炒股网','text':'广告'}),patch.object(agent,'search') as search:
   result=agent.check_site({'url':'https://ttseed.cn/','name':'梗百科'})
   self.assertEqual(result['status'],'用途已变更');self.assertEqual(result['candidates'],[]);search.assert_not_called()
 def test_login_widget_is_not_a_block_page(self):
  self.assertIn('验证码',agent.usable_page({'title':'墨鱼词典','content':'验证码'+'公开词条内容'*200}))
 def test_fetch_falls_back_without_credentials(self):
  page={'url':'https://example.com','text':'正文'*100,'title':'词条','retrieval':'服务器直读'}
  with patch.object(agent,'call_api',side_effect=RuntimeError('HTTP 404')),patch.object(agent,'fetch_html',return_value=page) as fallback:
   self.assertEqual(agent.fetch('https://example.com'),page);fallback.assert_called_once_with('https://example.com')
 def test_fixed_site_does_not_search(self):
  with patch.object(agent,'fetch_known',return_value={'title':'词典','text':'释义页面'}),patch.object(agent,'search') as search:
   agent.check_site({'url':'https://moyuoo.com/','name':'词典'});search.assert_not_called()
 def test_known_url_prefers_html_without_api(self):
  with patch.object(agent,'fetch_html',return_value={'text':'正文'}) as html,patch.object(agent,'fetch') as api:
   self.assertEqual(agent.fetch_known('https://example.com'),{'text':'正文'});api.assert_not_called()
 def test_recovery_must_read_search_result(self):
  seed={'url':'https://moyuoo.com/','name':'词典'}
  with patch.object(agent,'fetch_known',side_effect=[ValueError('offline'),{'title':'词条','text':'实际正文'}]) as reader,patch.object(agent,'search',return_value=[{'url':'https://moyuoo.com/123'}]):
   result=agent.check_site(seed);self.assertEqual(result['status'],'词条可读 / 首页不可用');self.assertEqual(reader.call_count,2)
 def test_retire_only_after_distinct_failed_days(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(agent,'ROOT',pathlib.Path(tmp)),patch.object(agent,'SEEDS',pathlib.Path(tmp)/'seeds.json'):
   site={'url':'https://example.com','status':'抓取失败','recovery_search_completed':True};agent.SEEDS.write_text(json.dumps([site]))
   self.assertEqual(len(agent.retire_failed_sites([site])),1);self.assertEqual(len(agent.retire_failed_sites([site])),1)
   path=pathlib.Path(tmp)/'private/wiki-ingest/site-health.json';d=json.loads(path.read_text());today=dt.date.today();d[site['url']]['failed_days']=[(today-dt.timedelta(days=n)).isoformat() for n in (2,1)];path.write_text(json.dumps(d))
   self.assertEqual(agent.retire_failed_sites([site]),[]);self.assertEqual(json.loads(agent.SEEDS.read_text()),[])
if __name__=='__main__':unittest.main()
