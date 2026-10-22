import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'studio'))
import providers
class LayoutSkillAccessTests(unittest.TestCase):
 def test_configured_models_can_read_skill_and_references(self):
  with tempfile.TemporaryDirectory() as folder:
   for name in ['SKILL.md','references/content-profiles.md','references/platform-and-review.md','references/sources.md','references/audience-discussion.md','references/editorial-diversity.md']:
    result=providers.tool('read_material',{'path':'skills/zhihu-converter/'+name},pathlib.Path(folder))
    self.assertGreater(len(result),100)
 def test_skill_read_access_does_not_open_private_files(self):
  with tempfile.TemporaryDirectory() as folder:
   for name in ['private/studio/auth.json','skills/zhihu-converter/../../private/studio/auth.json','studio/providers.py']:
    with self.assertRaises(ValueError):providers.tool('read_material',{'path':name},pathlib.Path(folder))
