"""Codex app-server adapter: only public messages and safe progress leave this module."""
import json,os,pathlib,queue,re,signal,subprocess,threading,time
import runtime

def string_prefix(source,start):
 """Decode the available prefix of a JSON string, tolerating split escapes."""
 i=start;escaped=False
 while i<len(source):
  ch=source[i]
  if ch=='"' and not escaped:
   try:return json.loads(source[start-1:i+1])
   except ValueError:return ''
  if ch=='\\' and not escaped:escaped=True
  else:escaped=False
  i+=1
 raw=source[start:]
 while raw:
  try:
   value=json.loads('"'+raw+'"')
   return value.encode('utf-16','surrogatepass').decode('utf-16','ignore')
  except (ValueError,UnicodeError):raw=raw[:-1]
 return ''

def field_prefix(source,key):
 m=re.search(r'"'+re.escape(key)+r'"\s*:\s*"',source)
 return string_prefix(source,m.end()) if m else ''

def draft_prefix(source):
 m=re.search(r'"blocks"\s*:\s*\[',source)
 if not m:return ''
 end=source.find('"sources"',m.end())
 area=source[m.end():end if end>=0 else len(source)]
 texts=[string_prefix(area,x.end()) for x in re.finditer(r'"text"\s*:\s*"',area)]
 title=field_prefix(source,'title')
 return (title+'\n\n' if title else '')+'\n\n'.join(texts)

class PublicEvents:
 def __init__(self,emit,phase):
  self.emit=emit;self.phase=phase;self.items={};self.sent={};self.last={};self.final=None
  match=re.search(r'round-(\d+)',phase)
  self.label='编辑审阅 · 第'+match[1]+'轮' if match else '写作与回复'
 def put(self,kind,key,text,force=False):
  if not text or self.sent.get((kind,key))==text:return
  clock=time.monotonic()
  if not force and clock-self.last.get((kind,key),0)<.12:return
  self.sent[kind,key]=text;self.last[kind,key]=clock
  self.emit(kind,{'key':self.phase+':'+key,'phase':self.label,'text':text})
 def handle(self,event):
  method=event.get('method','');p=event.get('params',{});item=p.get('item',{})
  if method=='item/started':
   if item.get('type')=='agentMessage':self.items[item['id']]={'text':item.get('text',''),'phase':item.get('phase')}
   labels={'webSearch':'正在检索公开资料','commandExecution':'正在整理或核对材料','mcpToolCall':'正在读取相关资料'}
   if item.get('type') in labels:self.put('progress',item['id'],labels[item['type']],True)
  elif method=='item/agentMessage/delta':
   state=self.items.setdefault(p['itemId'],{'text':'','phase':None});state['text']+=p['delta'];self.publish(p['itemId'])
  elif method=='item/completed' and item.get('type')=='agentMessage':
   self.items[item['id']]={'text':item['text'],'phase':item.get('phase')};self.publish(item['id'],True)
   try:
    value=json.loads(item['text'])
    if isinstance(value,dict):self.final=value
   except ValueError:pass
 def publish(self,key,force=False):
  state=self.items[key];text=state['text']
  if state['phase']=='commentary':self.put('progress',key,text[:2000],force)
  elif text.lstrip().startswith('{'):
   self.put('answer',key,field_prefix(text,'answer'),force)
   self.put('draft',key,draft_prefix(text)[:24000],force)

def run_agent(prompt,output,schema,emit,cwd,env,timeout=1800):
 output=pathlib.Path(output);events=queue.Queue();adapter=PublicEvents(emit,output.stem)
 args=[runtime.CODEX,'app-server','-c','web_search="live"']
 with output.with_suffix('.stderr.log').open('w') as errors,output.with_suffix('.events.jsonl').open('w') as log:
  proc=subprocess.Popen(args,cwd=cwd,env=env,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,start_new_session=True,bufsize=1)
  def reader():
   for line in proc.stdout:events.put(line)
   events.put(None)
  thread=threading.Thread(target=reader,daemon=True);thread.start()
  def send(value):proc.stdin.write(json.dumps(value,ensure_ascii=False)+'\n');proc.stdin.flush()
  send({'id':0,'method':'initialize','params':{'clientInfo':{'name':'lc_writing_studio','title':'LC Writing Studio','version':'0.2.0'}}})
  deadline=time.monotonic()+timeout
  try:
   while time.monotonic()<deadline:
    try:line=events.get(timeout=min(2,max(.01,deadline-time.monotonic())))
    except queue.Empty:continue
    if line is None:raise RuntimeError('AI实时通道提前结束，请查看任务记录')
    event=json.loads(line);method=event.get('method','');item=event.get('params',{}).get('item',{})
    # Never persist or forward reasoning text/summaries, command output or credentials to the UI.
    if method.startswith('item/reasoning/') or item.get('type')=='reasoning':continue
    log.write(line);log.flush()
    if event.get('error') and 'id' in event:raise RuntimeError('AI接口请求失败：'+str(event['error'].get('message','未知错误')))
    if event.get('id')==0 and 'result' in event:
     send({'method':'initialized','params':{}})
     send({'id':1,'method':'thread/start','params':{'cwd':str(cwd),'approvalPolicy':'never','sandbox':'read-only','ephemeral':True,'config':{'web_search':'live'}}})
    elif event.get('id')==1 and 'result' in event:
     tid=event['result']['thread']['id']
     send({'id':2,'method':'turn/start','params':{'threadId':tid,'input':[{'type':'text','text':prompt}], 'approvalPolicy':'never','sandboxPolicy':{'type':'readOnly'},'outputSchema':json.loads(pathlib.Path(schema).read_text())}})
    elif 'id' in event and method:
     send({'id':event['id'],'error':{'code':-32601,'message':'工作台不支持交互审批；请在现有只读权限内完成任务'}})
    else:adapter.handle(event)
    if method=='turn/completed':
     turn=event['params']['turn']
     if turn['status']!='completed':raise RuntimeError('AI任务未完成：'+str(turn.get('error') or turn['status']))
     if adapter.final is None:raise RuntimeError('AI未返回完整结构化结果')
     output.write_text(json.dumps(adapter.final,ensure_ascii=False,indent=2))
     return adapter.final
   raise RuntimeError('AI实时任务超时，已停止')
  finally:
   if proc.poll() is None:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
   thread.join(timeout=1)
   proc.stdin.close();proc.stdout.close()
