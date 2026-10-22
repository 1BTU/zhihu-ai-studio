"""Resumable long articles: chapter generation and whole-manuscript patch review."""
import copy,json,re,hashlib

def words(article):
 return len(re.findall(r'[\u3400-\u9fff]', ''.join(b['text'] for b in article['blocks'] if b['type']=='paragraph')))

def schema_file(d,name,definition):
 p=d.RUN/name;d.save(p,definition);return p

def expand(d,article,index,runner=None):
 run=runner or d.agent
 folder=d.RUN
 seed=folder/f'long-{index}-seed.json';d.save(seed,article)
 blocks={'type':'array','minItems':1,'items':{'type':'object','additionalProperties':False,'properties':{'type':{'type':'string','enum':['paragraph','heading']},'text':{'type':'string'}},'required':['type','text']}}
 section_schema=schema_file(d,'long-section-schema.json',{'type':'object','additionalProperties':False,'properties':{'blocks':blocks},'required':['blocks']})
 plan_schema=schema_file(d,'long-plan-schema.json',{'type':'object','additionalProperties':False,'properties':{'sections':{'type':'array','minItems':6,'maxItems':8,'items':{'type':'object','additionalProperties':False,'properties':{'title':{'type':'string'},'purpose':{'type':'string'},'facts':{'type':'string'}},'required':['title','purpose','facts']}}},'required':['sections']})
 identity=hashlib.sha256(json.dumps(article,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 planpath=folder/f'long-{index}-plan.json';marker=folder/f'long-{index}-identity.json'
 same=marker.exists() and json.loads(marker.read_text())==identity
 if not same:
  for old in folder.glob(f'long-{index}-section-*.json'):old.unlink()
 plan=json.loads(planpath.read_text()) if same and planpath.exists() else run(f'读取 {seed} 与本任务 writing-context.json。把此选题规划为一篇12000–15000汉字的完整长文，6–8节，每节不同贡献。保持原选题、已核实来源、范文迁移和人物设定。第一节交代背景，最后一节收束，不用重复开头凑字。facts记录本节可用证据及不能推断的边界。返回JSON。',planpath,plan_schema)
 d.save(marker,identity);d.save(planpath,plan)
 result=copy.deepcopy(article);result['blocks']=[]
 for n,part in enumerate(plan['sections'],1):
  d.report_progress('长文分节写作',f'第{index}篇 · {n}/{len(plan["sections"])}节：{part["title"]}')
  context=folder/f'long-{index}-context.json';d.save(context,{'seed':article,'plan':plan,'completed_blocks':result['blocks'],'current_section':part})
  output=folder/f'long-{index}-section-{n}.json'
  data=json.loads(output.read_text()) if same and output.exists() else None
  for attempt in range(3):
   if data and words(data)>=1800:break
   data=run(f'读取完整上下文 {context}。只写当前第{n}节，正文1800–2400汉字（不是token），必须衔接已完成正文，不重复已写内容，不预写后续章节。禁止灌水、无来源的新事实和虚构个人经历。引用来源与seed一致；故事保持人物与物件时间线。首节保留必要背景；最后一节才收尾。只输出本节blocks JSON。'+('上一稿字数不合要求，请补足具体论证或情节而不是重复。' if attempt else ''),output,section_schema)
  if not data or not words(data)>=1800:raise RuntimeError(f'长文第{n}节未达到有效字数，已保留进度')
  d.save(output,data);result['blocks'].extend(data['blocks'])
 if words(result)<10000:raise RuntimeError('长文正文未达到10000汉字，停止发布')
 d.save(folder/f'long-{index}-full.json',result)
 return result

def review(d,article,index,require_recent=True,runner=None):
 run=runner or d.agent;current=copy.deepcopy(article)
 definition={'type':'object','additionalProperties':False,'properties':{'verdict':{'type':'string','enum':['approved','revise','reject']},'issues':{'type':'array','items':{'type':'string'}},'changes':{'type':'array','items':{'type':'object','additionalProperties':False,'properties':{'index':{'type':'integer','minimum':0},'original':{'type':'string'},'text':{'type':'string'}},'required':['index','original','text']}}},'required':['verdict','issues','changes']}
 schema=schema_file(d,'long-review-schema.json',definition)
 for round_no in range(1,d.CFG['review_max_rounds']+1):
  d.report_progress('长文整体审稿',f'第{index}篇 · 第{round_no}轮 · {words(current)}汉字')
  source=d.RUN/f'review-{index}-round-{round_no}-input.json'
  indexed=copy.deepcopy(current);indexed['blocks']=[dict(b,index=i) for i,b in enumerate(current['blocks'])];d.save(source,indexed)
  output=d.RUN/f'review-{index}-round-{round_no}-patch.json'
  prompt=(d.ROOT/'review-prompt.txt').read_text()+f'\n本次是长文整体审核。完整正文 {source}，完整热点与范文资料在当前任务目录。长文必须保留10000汉字以上，不适用短文字数和最多3小标题要求。逐节核对全篇，特别检查重复灌水、前后矛盾、事实来源和论点推进。只返回schema规定的精确段落修改，index必须使用输入段落自带的index，不得自行估数；original必须逐字复制该段完整原文，text是该段完整可发布的新正文，不得写入审稿说明、issues、占位符或创作过程。无改动则changes为空。issues只列应用本轮修改后仍然存在的问题，不重复列已修复项。不输出全文。修改较多可返回revise，但必须给出本轮实际修改。'
  prompt+=__import__('layout').review_note(current)
  if not require_recent:prompt+=' 用户指定选题，不强制72小时时效。'
  if article.get('genre')=='fiction':prompt+=' 原创虚构故事按人物、情节因果和时间线审核，不要求公开事件来源。'
  value=run(prompt,output,schema)
  if value['verdict']=='reject':raise RuntimeError('长文审稿未通过：'+'；'.join(value['issues']))
  seen=set()
  for change in value['changes']:
   n=change['index']
   if n in seen or not 0<=n<len(current['blocks']) or not change['text'].strip():raise RuntimeError('长文审稿修改索引无效')
   if change.get('original')!=current['blocks'][n]['text']:raise RuntimeError('长文审稿原文与段落位置不匹配，未应用错位修改')
   seen.add(n);current['blocks'][n]['text']=change['text']
  d.validate_article(current,require_recent)
  if words(current)<10000:raise RuntimeError('审稿把长文缩短至10000字以下，停止发布')
  if value['verdict']=='approved' and not value['issues']:
   proof=d.RUN/f'review-{index}-round-{round_no}.json';d.save(proof,{'verdict':'approved','issues':[],'article':current})
   final=d.prepare_article(current);final['editorial_review']={'status':'approved','rounds':round_no,'proof':proof.name,'fingerprint':d.article_fingerprint(final)};return final
 raise RuntimeError('长文达到审稿轮次上限，保留进度，未发布')
