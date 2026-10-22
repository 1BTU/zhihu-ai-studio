"""Once-daily AI-assisted challenge actions; completion verified independently in DOM."""
import argparse,datetime as dt,fcntl,json,os,pathlib,re,shutil,signal,subprocess
from zoneinfo import ZoneInfo
from scheduler import read,save
ROOT=pathlib.Path(__file__).resolve().parent
import runtime
NODE=runtime.NODE
CODEX=runtime.CODEX

def parse_progress(text):
    tail=text.split('今日任务',1)[-1] if '今日任务' in text else ''
    creation=re.search(r'创作任务\s*[（(](\d+)\s*/\s*(\d+)[）)]',tail)
    interaction=re.search(r'互动任务\s*[（(](\d+)\s*/\s*(\d+)[）)]',tail)
    if not creation or not interaction:raise ValueError('未读到完整打卡进度，可能需要登录或活动已结束')
    c,ct=map(int,creation.groups());i,it=map(int,interaction.groups())
    if ct<=0 or it<=0:raise ValueError('打卡任务目标无效')
    done=bool(re.match(r'\s*(?:已完成|打卡成功)',tail)) and c>=ct and i>=it
    return {'creation':f'{c}/{ct}','interaction':f'{i}/{it}','completed':done,'progress':tail.split('分享',1)[0].strip()}

def due(state,now,settings):
    start=dt.datetime.combine(now.date(),dt.time.fromisoformat(settings.get('time','20:30')),now.tzinfo)
    if not settings.get('enabled') or now<start or now.hour>=23:return False
    if state.get('status')=='completed':return False
    if int(state.get('checks',0))>=4:return False
    last=state.get('last_checked_at')
    return not last or now-dt.datetime.fromisoformat(last)>=dt.timedelta(minutes=30)

def probe(folder):
    r=subprocess.run([NODE,str(ROOT/'challenge-probe.mjs'),str(folder)],cwd=ROOT,capture_output=True,text=True,timeout=120)
    (folder/'probe.log').write_text(r.stdout+'\n'+r.stderr)
    if r.returncode:raise RuntimeError('打卡进度读取失败，详见巡查日志')
    evidence=read(folder/'probe.json');return {**parse_progress(evidence['text']),'verified_at':evidence['checked_at']}

def execute_agent(folder,cfg):
    active=read(ROOT/'private/active-profile.json')['name']
    if not re.fullmatch(r'browser-profile(?:-\d+)?',active):raise ValueError('无效账号目录')
    profile=ROOT/'private'/active
    (folder/'node_modules').symlink_to(ROOT/'node_modules',target_is_directory=True) if not (folder/'node_modules').exists() else None
    schema={'type':'object','additionalProperties':False,'properties':{'summary':{'type':'string'},'actions':{'type':'array','items':{'type':'object','additionalProperties':False,'properties':{'task':{'type':'string'},'status':{'type':'string'},'url':{'type':'string'},'detail':{'type':'string'}},'required':['task','status','url','detail']}},'error':{'type':'string'}},'required':['summary','actions','error']}
    save(folder/'agent-schema.json',schema)
    context={'date':folder.parent.name,'activity_url':cfg['challenge']['url'],'profile':str(profile),'project':str(ROOT),'folder':str(folder)}
    save(folder/'context.json',context)
    prompt=(ROOT/'challenge-prompt.txt').read_text()+f'\n本次上下文 {folder}/context.json；先读 probe.json。'
    args=[CODEX,'exec','--skip-git-repo-check','--ephemeral','--disable','apps','-s','workspace-write',
          '-c','sandbox_workspace_write.network_access=true','-c','sandbox_workspace_write.writable_roots='+json.dumps([str(profile)]),
          '-c','approval_policy="never"','-c','web_search="disabled"','--output-schema',str(folder/'agent-schema.json'),'-o',str(folder/'agent-result.json'),'--json','-']
    with (folder/'agent.log').open('w') as log:
        p=subprocess.Popen(args,cwd=folder,stdin=subprocess.PIPE,stdout=log,stderr=log,text=True,start_new_session=True)
        try:
            p.communicate(prompt,timeout=1200)
            if p.returncode:raise RuntimeError('自动打卡执行器未正常结束；不会重复提交，稍后仅复查活动进度')
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            raise RuntimeError('自动打卡超时；保留记录，稍后仅复查活动进度')
    result=read(folder/'agent-result.json',{})
    if not isinstance(result.get('actions'),list):raise RuntimeError('缺少执行记录')
    return result

def run(cfg,verify_only=False):
    now=dt.datetime.now(ZoneInfo(cfg['timezone']));folder=ROOT/'reports'/str(now.date())/'challenge';folder.mkdir(parents=True,exist_ok=True)
    state=read(folder/'state.json',{'date':str(now.date()),'status':'pending','checks':0,'actions':[]})
    if not verify_only and not due(state,now,cfg.get('challenge',{})):return
    state.update(checks=state.get('checks',0)+1,last_checked_at=now.isoformat(),status='checking');save(folder/'state.json',state)
    try:
        try:observed=probe(folder)
        except ValueError:
            page=read(folder/'probe.json',{})
            if not re.search(r'/(signin|signup)(?:[/?#]|$)',page.get('url','')) or state.get('login_attempted'):raise
            state['login_attempted']=True;save(folder/'state.json',state)
            import daily
            daily.RUN=folder;daily.TODAY=now.date();daily.CFG=cfg
            daily.authenticate()
            observed=probe(folder)
        state.update(observed)
        if observed['completed']:state.update(status='completed',error='');save(folder/'state.json',state);return
        if verify_only:state['status']='pending';save(folder/'state.json',state);return
        if state.get('attempted_at'):
            state.update(status='needs_attention',error='本日已执行过，复查仍未打卡完成；不重复提交内容');save(folder/'state.json',state);return
        state.update(status='running',attempted_at=now.isoformat());save(folder/'state.json',state)
        error=''
        try:
            result=execute_agent(folder,cfg);state.update(actions=result['actions'],summary=result['summary']);error=result.get('error','')
        except Exception as exc:error=str(exc)
        # Never trust model-declared success. Reopen the activity in a new browser.
        observed=probe(folder);state.update(observed,status='completed' if observed['completed'] else 'needs_attention',error='' if observed['completed'] else error or '活动尚未计入全部任务，稍后只复查进度')
        save(folder/'state.json',state)
    except Exception as exc:
        state.update(status='needs_attention',error=str(exc));save(folder/'state.json',state)

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-only',action='store_true');opts=p.parse_args();cfg=read(ROOT/'daily-config.json')
    with (ROOT/'private/daily.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        run(cfg,opts.verify_only)
if __name__=='__main__':main()
