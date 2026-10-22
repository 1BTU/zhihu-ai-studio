"""Persistent, non-overlapping daily publication windows. All times are local."""
import argparse, datetime as dt, fcntl, json, pathlib, secrets
from types import SimpleNamespace
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(__file__).resolve().parent
TERMINAL={'done','failed','missed','interrupted'}
def read(p,default=None):
    return json.loads(p.read_text()) if p.exists() else default

def save(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.chmod(0o600);tmp.replace(p)

def plan(folder,date,cfg):
    p=folder/'schedule.json'
    if p.exists():return read(p)
    zone=ZoneInfo(cfg['timezone']);slots=[];previous=None
    for w in cfg['windows']:
        start=dt.datetime.combine(date,dt.time.fromisoformat(w['start']),zone)
        end=dt.datetime.combine(date,dt.time.fromisoformat(w['end']),zone)
        if end<=start or previous and start<previous:raise ValueError('发布时间段无效或重叠')
        if not w['id'].isascii() or not w['id'].isalpha():raise ValueError('时段标识无效')
        minute=secrets.randbelow(int((end-start).total_seconds()//60))
        slots.append(dict(id=w['id'],label=w['label'],start=start.isoformat(),end=end.isoformat(),
                          prepare_at=(start-dt.timedelta(minutes=30)).isoformat(),publish_at=(start+dt.timedelta(minutes=minute)).isoformat(),status='pending'))
        previous=end
    if len(slots)!=3 or len({s['id'] for s in slots})!=3:raise ValueError('每天需要三个独立时段')
    value={'date':str(date),'timezone':cfg['timezone'],'slots':slots};save(p,value);return value

def action(slot,now):
    if slot['status'] in TERMINAL:return None
    if slot['status'] in ('preparing','publishing'):return 'interrupted'
    if now>=dt.datetime.fromisoformat(slot['end']):return 'missed'
    if slot['status']=='pending' and now>=dt.datetime.fromisoformat(slot['prepare_at']):return 'prepare'
    if slot['status']=='ready' and now>=dt.datetime.fromisoformat(slot['publish_at']):return 'publish'
    return None

def aggregate(folder,value):
    articles=[]
    for slot in value['slots']:
        state=read(folder/'slots'/slot['id']/'state.json',{})
        articles.extend(dict(a,slot=slot['label']) for a in state.get('articles',[]))
    terminal=all(s['status'] in TERMINAL for s in value['slots'])
    complete=all(s['status']=='done' for s in value['slots'])
    state={'date':value['date'],'articles':articles,'notified':complete,'schedule_status':'completed' if complete else 'partial' if terminal else 'scheduled'}
    failures=[s['label']+'：'+s.get('error',s['status']) for s in value['slots'] if s['status'] in TERMINAL-{'done'}]
    if failures:state['error']='；'.join(failures)
    if terminal:state['completed_at']=dt.datetime.now(ZoneInfo(value['timezone'])).isoformat()
    save(folder/'state.json',state)
    save(folder/'progress.json',{'stage':'已完成' if complete else '部分完成' if terminal else '分时段执行','detail':' · '.join(s['label']+' '+s['publish_at'][11:16]+' '+s['status'] for s in value['slots'])})

def tick(cfg):
    import daily
    now=dt.datetime.now(ZoneInfo(cfg['timezone']));date=now.date()
    folder=ROOT/'reports'/str(date)/'daily'
    legacy=read(folder/'state.json',{})
    if not (folder/'schedule.json').exists() and legacy.get('articles'):
        # Never turn an existing bulk run into a second daily quota.
        return
    value=plan(folder,date,cfg)
    for slot in value['slots']:
        now=dt.datetime.now(ZoneInfo(cfg['timezone']));todo=action(slot,now)
        if todo is None:continue
        if todo in ('missed','interrupted'):
            slot.update(status=todo,error='已错过时段，稿件保留，不补发' if todo=='missed' else '上次进程中断，请核对结果后恢复')
        else:
            slot['status']='preparing' if todo=='prepare' else 'publishing';save(folder/'schedule.json',value)
            daily.RUN=folder/'slots'/slot['id'];daily.RUN.mkdir(parents=True,exist_ok=True)
            daily.TODAY=date;daily.CFG=dict(cfg,count=1,article_layout=['short'])
            daily.ENV=dict(daily.ENV,ZHIHU_PUBLISH_AFTER=slot['publish_at'],ZHIHU_PUBLISH_BEFORE=slot['end'])
            try:
                daily.run_locked(SimpleNamespace(test_mail=False,generate_only=todo=='prepare'))
                slot['status']='ready' if todo=='prepare' else 'done'
            except Exception as exc:slot.update(status='failed',error=str(exc))
        save(folder/'schedule.json',value);aggregate(folder,value)
        # One expensive operation per tick. Never launch a batch of overdue publications.
        return
    aggregate(folder,value)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan-only',action='store_true');parser.add_argument('--date');opts=parser.parse_args()
    cfg=read(ROOT/'daily-config.json');now=dt.datetime.now(ZoneInfo(cfg['timezone']))
    with (ROOT/'private/daily.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        if opts.plan_only:
            date=dt.date.fromisoformat(opts.date) if opts.date else now.date()
            print(json.dumps(plan(ROOT/'reports'/str(date)/'daily',date,cfg),ensure_ascii=False));return
        tick(cfg)
        now=dt.datetime.now(ZoneInfo(cfg['timezone']))
        settings=cfg.get('operations',{})
        start=dt.datetime.combine(now.date(),dt.time.fromisoformat(settings.get('time','15:00')),now.tzinfo)
        if settings.get('enabled') and start<=now<start+dt.timedelta(hours=2):
            import operations
            operations.run()
        # Finish due article work first; challenge must not hold the account across its publication slot.
        now=dt.datetime.now(ZoneInfo(cfg['timezone']))
        schedule=read(ROOT/'reports'/str(now.date())/'daily/schedule.json',{})
        waiting=any(s['status'] not in TERMINAL and now<dt.datetime.fromisoformat(s['end']) for s in schedule.get('slots',[]))
        if cfg.get('challenge',{}).get('enabled') and not waiting:
            import challenge
            challenge.run(cfg)
if __name__=='__main__':main()
