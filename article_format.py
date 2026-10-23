"""Semantic article blocks v2; legacy plain blocks remain valid."""
TYPES=('paragraph','heading','quote','bullet','ordered')
BLOCK_SCHEMA={'type':'object','additionalProperties':False,'properties':{'type':{'type':'string','enum':list(TYPES)},'text':{'type':'string'},'emphasis':{'type':'array','maxItems':3,'uniqueItems':True,'items':{'type':'string','minLength':1,'maxLength':80}}},'required':['type','text']}
def validate_blocks(blocks):
 for index,block in enumerate(blocks):
  if block.get('type') not in TYPES or not isinstance(block.get('text'),str):raise ValueError(f'blocks/{index} 类型或正文无效')
  ranges=[]
  for text in block.get('emphasis',[]):
   start=block['text'].find(text)
   if not text or start<0 or any(start<end and start+len(text)>begin for begin,end in ranges):raise ValueError(f'blocks/{index}/emphasis 强调片段不在原文或重叠，须保留原文并修正emphasis')
   ranges.append((start,start+len(text)))
def validate_result(result):
 if not isinstance(result,dict):return
 candidates=[result]+([result['article']] if isinstance(result.get('article'),dict) else [])+[a for a in result.get('articles',[]) if isinstance(a,dict)]
 for article in candidates:
  if isinstance(article.get('blocks'),list):validate_blocks(article['blocks'])
