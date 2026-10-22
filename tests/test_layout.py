import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import layout
class LayoutTests(unittest.TestCase):
 def test_counts_visual_paragraphs_and_stops_at_sources(self):
  a={'blocks':[{'type':'heading','text':'Heading'},{'type':'paragraph','text':'甲'*100+'\n\n'+'乙'*240},{'type':'heading','text':'参考资料'},{'type':'paragraph','text':'https://example.com/'+('x'*500)}]}
  r=layout.audit(a)
  self.assertEqual(r['paragraph_count'],2);self.assertEqual(r['median_characters'],170);self.assertEqual(r['over_220'],[{'block_index':1,'characters':240}]);self.assertEqual(a['blocks'][1]['text'].count('乙'),240)
 def test_empty_and_whitespace(self):
  self.assertEqual(layout.audit({'blocks':[]})['median_characters'],0)
  self.assertEqual(layout.audit({'blocks':[{'text':'a b\nc'}]})['median_characters'],3)
if __name__=='__main__':unittest.main()
