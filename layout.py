"""Editorial diagnostics only: never rewrite text or reject solely by length."""
import re,statistics

def audit(article):
 paragraphs=[]
 for index,b in enumerate(article.get('blocks',[])):
  if b.get('type')=='heading':
   if b.get('text','').strip() in ('参考资料','参考来源','资料来源'):break
   continue
  for part in re.split(r'\n\s*\n',b.get('text','')):
   text=re.sub(r'\s+','',part)
   if text:paragraphs.append((index,len(text)))
 lengths=[n for _,n in paragraphs]
 return {'paragraph_count':len(lengths),'median_characters':round(statistics.median(lengths)) if lengths else 0,
         'over_150':sum(n>150 for n in lengths),'over_220':[{'block_index':i,'characters':n} for i,n in paragraphs if n>220],
         'note':'去空白字符数；按空行分段，忽略小标题并在参考资料标题处停止。阈值仅提醒编辑复核，不自动截断。段落索引从0开始。'}

def review_note(article):
 return '\n【段落排版诊断】'+__import__('json').dumps(audit(article),ensure_ascii=False)+'\n按段落节奏规则复查密集段和视觉层次，在changes记录实际排版修改或保留理由；不为达标机械切句。'
