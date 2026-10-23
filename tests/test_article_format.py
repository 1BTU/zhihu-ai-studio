import copy,json,pathlib,unittest
import jsonschema
from article_format import BLOCK_SCHEMA,validate_blocks
class ArticleFormatTests(unittest.TestCase):
 def test_new_and_legacy_blocks(self):
  for kind in ('paragraph','heading','quote','bullet','ordered'):
   block={'type':kind,'text':'关键事实和适用范围','emphasis':['关键事实']}
   jsonschema.validate(block,BLOCK_SCHEMA);validate_blocks([block])
  validate_blocks([{'type':'paragraph','text':'旧格式'}])
 def test_emphasis_must_exist_and_not_overlap(self):
  for fragments in [['不存在'],['关键','关键事实']]:
   with self.assertRaises(ValueError):validate_blocks([{'type':'paragraph','text':'关键事实','emphasis':fragments}])
 def test_all_article_schemas_share_contract(self):
  root=pathlib.Path(__file__).resolve().parents[1]
  for filename in ['daily-schema.json','review-schema.json','fiction-daily-schema.json','fiction-review-schema.json','studio/chat-schema.json','studio/fiction-chat-schema.json']:
   def walk(value):
    if isinstance(value,dict):
     if 'blocks' in value.get('properties',{}):self.assertEqual(value['properties']['blocks']['items'],BLOCK_SCHEMA,filename)
     for child in value.values():walk(child)
    elif isinstance(value,list):
     for child in value:walk(child)
   walk(json.loads((root/filename).read_text()))

 def test_review_fingerprint_covers_styles(self):
  import daily
  a={'blocks':[{'type':'paragraph','text':'关键事实'}]};b=copy.deepcopy(a);b['blocks'][0]['emphasis']=['关键事实']
  self.assertNotEqual(daily.article_fingerprint(a),daily.article_fingerprint(b))
