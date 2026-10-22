'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let state=null,selected=null,view='overview',lastMessageId=0;
let activeConversation=localStorage.getItem('lc-conversation')||'legacy';
const names={operations:['知乎日常','活动、问题与每一次真实提交，都有记录。'],overview:['让每一篇，都有迹可循。','从一个想法，到发布后的真实反馈。'],articles:['文章与成稿','读过的、改过的、发出的，都在这里。'],chat:['一个好想法，从聊天开始。','把方向告诉 AI，材料、写作与修改交给流程。'],jobs:['任务与运行记录','知道今天做到哪一步，也知道哪里需要处理。']};
function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n}
function showView(v,push=true){if(!names[v])return;const target='/studio/'+v+'/';if(push&&location.pathname!==target)history.pushState({view:v},'',target);view=v;$$('[data-panel]').forEach(n=>n.hidden=n.dataset.panel!==v);$$('[data-view]').forEach(n=>{n.classList.toggle('active',n.dataset.view===v);if(n.dataset.view===v)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current')});$('#page-title').textContent=names[v][0];$('#page-subtitle').textContent=names[v][1];if(v==='chat')$('#chat-input').focus()}
function pretty(t){if(!t)return '—';return new Date(t).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})}
function num(x){return x==null?'—':Number(x).toLocaleString('zh-CN')}
function notify(s){$('#notice').hidden=false;$('#notice').textContent=s}
async function api(path,payload){const r=await fetch('api/'+path,{method:payload?'POST':'GET',headers:payload?{'Content-Type':'application/json','X-Requested-With':'WritingStudio'}:{},body:payload?JSON.stringify(payload):undefined,cache:'no-store'});if(r.status===401){location.href='/studio/login/?next='+encodeURIComponent(location.pathname+location.search);throw Error('请重新登录')}const j=await r.json();if(!r.ok)throw Error(j.error||'请求未完成');return j}
const jobLabels={chat:'AI 对话与写作',sync:'同步知乎数据',publish:'发布文章',read:'读取文章全文',login:'恢复登录'};
const statusLabels={deleted:'回收站',queued:'等待处理',running:'正在执行',done:'已完成',failed:'未完成',ready:'成稿待发布',published:'已提交发布',writing:'草稿写入待核对',publishing:'发布结果待核对',publish_failed:'发布待重试'};
function badge(text,status){return el('span','badge'+(['failed','writing','publishing','publish_failed'].includes(status)?' failed':['queued','running','ready'].includes(status)?' waiting':''),text)}
function btn(text,fn,secondary=true){const b=el('button',secondary?'text-button':'button',text);b.type='button';b.onclick=fn;return b}
function articleStatus(a){if(a.status!=='deleted'&&(a.preview_only||a.data?.preview_only))return '图文试读稿';return a.status==='published'?(a.review_status||'已提交发布'):(statusLabels[a.status]||a.status)}
function totals(key){const a=state.articles.filter(a=>a[key]!=null);return a.length?a.reduce((s,a)=>s+a[key],0):null}
function renderArticles(){
 const query=$('#search').value.toLowerCase(),filter=$('#status-filter').value;
 const list=state.articles.filter(a=>(!$('#article-column').value||a.column_id===$('#article-column').value)&&(filter==='all'&&a.status!=='deleted'||filter==='attention'&&['writing','publishing','publish_failed'].includes(a.status)||a.status===filter)&&(!query||(a.title+' '+a.excerpt).toLowerCase().includes(query)));
 const checked=new Set($$('.draft-selection:checked').map(x=>x.value));const body=$('#article-table');body.replaceChildren();for(const a of list){const row=el('tr');const title=el('td');if(['ready','deleted'].includes(a.status)){const check=el('input','draft-selection');check.type='checkbox';check.value=a.id;check.checked=checked.has(a.id);check.setAttribute('aria-label','选择草稿 '+a.title);title.append(check)}title.append(btn(a.title,()=>openArticle(a.id)));title.querySelector('button').className='title-link';title.append(el('p','',`${a.origin==='chat'?'AI 对话':a.origin==='account'?'账号同步':'每日任务'} · ${pretty(a.created_at)}`));row.append(title);const st=el('td');st.append(badge(articleStatus(a),a.status));row.append(st);for(const k of ['views','likes','comments','favorites'])row.append(el('td','',num(a[k])));const actions=el('td');actions.append(btn('阅读',()=>openArticle(a.id)));if(a.preview_url)actions.append(link('图文版 ↗',a.preview_url));if(a.url)actions.append(link('知乎 ↗',a.url));if(!a.preview_only&&!a.data?.preview_only&&['ready','publishing','publish_failed'].includes(a.status))actions.append(btn(a.status==='ready'?'发布':'核对发布',()=>publish(a.id)));if(a.status==='ready')actions.append(btn('删除草稿',()=>changeTrash([a.id],false)));if(a.status==='deleted')actions.append(btn('恢复草稿',()=>changeTrash([a.id],true)));row.append(actions);body.append(row)}
 if(!list.length){const tr=el('tr'),td=el('td','empty','还没有符合条件的文章。可以从 AI 对话开始。');td.colSpan=7;tr.append(td);body.append(tr)}
}
function link(text,url){const a=el('a','text-button',text);if(/^\/studio\/readings\/[a-z0-9-]+\/$/.test(url)||/^https:\/\/(?:zhuanlan\.zhihu\.com|www\.zhihu\.com)\//.test(url)){a.href=url;a.target='_blank';a.rel='noopener noreferrer'}return a}
function renderChart(){const c=$('#chart');c.replaceChildren();const h=state.history;if(h.length<2){const d=el('div','empty',h.length?'第一份数据已记录。积累两天后显示变化曲线。':'同步知乎数据后，这里会留下每日采样。');c.append(d);return}const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 450 190');svg.setAttribute('role','img');svg.setAttribute('aria-label','已同步文章累计阅读量采样趋势');const max=Math.max(1,...h.map(x=>x.views));const pts=h.map((x,i)=>[35+i*380/(h.length-1),150-x.views/max*115]);for(let i=0;i<3;i++){const line=document.createElementNS(ns,'line');line.setAttribute('x1','35');line.setAttribute('x2','415');line.setAttribute('y1',String(35+i*57));line.setAttribute('y2',String(35+i*57));line.setAttribute('stroke','#e7ece1');svg.append(line)}const poly=document.createElementNS(ns,'polyline');poly.setAttribute('points',pts.map(p=>p.join(',')).join(' '));poly.setAttribute('fill','none');poly.setAttribute('stroke','#547c52');poly.setAttribute('stroke-width','2.5');svg.append(poly);h.forEach((x,i)=>{const circle=document.createElementNS(ns,'circle');circle.setAttribute('cx',pts[i][0]);circle.setAttribute('cy',pts[i][1]);circle.setAttribute('r','4');circle.setAttribute('fill','#547c52');const title=document.createElementNS(ns,'title');title.textContent=`${x.day}：${x.views} 次阅读，覆盖 ${x.coverage} 篇`;circle.append(title);svg.append(circle)});for(const [i,anchor] of [[0,'start'],[h.length-1,'end']]){const tx=document.createElementNS(ns,'text');tx.setAttribute('x',pts[i][0]);tx.setAttribute('y','181');tx.setAttribute('font-size','11');tx.setAttribute('fill','#83917f');tx.setAttribute('text-anchor',anchor);tx.textContent=h[i].day;svg.append(tx)}c.append(svg)}
const progressOpen=new Map();
let eventSource=null,messageRenderKey=null;
function processDetails(job){
 const data=job?.stream;if(!data?.progress?.length&&!data?.draft)return null;
 const detail=el('details','process-details');detail.dataset.job=job.id;detail.open=progressOpen.get(job.id)||false;
 detail.addEventListener('toggle',()=>{if(detail.isConnected)progressOpen.set(job.id,detail.open)});
 const summary=el('summary','',`${['queued','running'].includes(job.status)?'正在处理':'处理记录'} · ${data.progress.length} 条摘要`);
 detail.append(summary,el('p','process-note','展示公开的处理摘要与操作进度。'));
 const list=el('div','process-list');for(const p of data.progress){const item=el('div','process-item');item.append(el('small','',`${pretty(p.time)} · ${p.phase}`),el('p','',p.text));list.append(item)}detail.append(list);
 if(data.draft){const preview=el('details','draft-preview');const draftKey=job.id+':draft';preview.open=progressOpen.get(draftKey)||false;preview.addEventListener('toggle',()=>{if(preview.isConnected)progressOpen.set(draftKey,preview.open)});preview.append(el('summary','',job.status==='done'?'查看生成过程中的文稿':'查看流式文稿 · 编辑审阅中'),el('div','draft-text',data.draft));detail.append(preview)}
 return detail;
}
const resendingConversations=new Set();
function conversationBusy(id){return resendingConversations.has(id)||state.jobs.some(j=>j.kind==='chat'&&j.conversation_id===id&&['queued','running'].includes(j.status))}
async function resendMessage(message){
 const conversation=message.conversation_id;if(conversationBusy(conversation))return;
 const model=$('#chat-model').value;
 resendingConversations.add(conversation);renderMessages();
 try{await api('chat',{message:message.content,article_id:message.article_id||null,conversation_id:conversation,model});notify('已重新发送，正在处理。');await refresh()}
 catch(e){notify(e.message)}
 finally{resendingConversations.delete(conversation);renderMessages()}
}
function resendButton(message){const b=btn('重新发送',()=>resendMessage(message));b.classList.add('resend-message');b.dataset.messageId=message.id;b.disabled=conversationBusy(message.conversation_id);b.title=b.disabled?'当前会话仍在处理，请完成后重试':'使用当前选择的模型，重新发送这条原始消息';return b}
function renderMessages(){
 const box=$('#messages');
 const messages=state.messages.filter(m=>m.conversation_id===activeConversation);
 const relevantJobs=state.jobs.filter(j=>j.conversation_id===activeConversation||messages.some(m=>m.job_id===j.id));
 const renderKey=JSON.stringify([activeConversation,messages,relevantJobs,resendingConversations.has(activeConversation)]);if(renderKey===messageRenderKey)return;messageRenderKey=renderKey;
 const nearBottom=box.scrollHeight-box.scrollTop-box.clientHeight<80,oldTop=box.scrollTop,scrolls=new Map();
 box.querySelectorAll('[data-job]').forEach(n=>{progressOpen.set(n.dataset.job,n.open);const draft=n.querySelector('.draft-preview');if(draft)progressOpen.set(n.dataset.job+':draft',draft.open);scrolls.set(n.dataset.job,[n.querySelector('.process-list')?.scrollTop||0,n.querySelector('.draft-text')?.scrollTop||0])});
 box.replaceChildren();
 if(!messages.length){const welcome=el('div','message');welcome.append(el('div','role','AI 编辑'),el('div','bubble','你好。你可以直接告诉我想写什么，也可以先聊一个热点的切入点。文章写好后，我会再核对材料、审核修改，把成稿放到工作台。'));box.append(welcome)}
 for(const m of messages){const item=el('div','message '+m.role);item.append(el('div','role',`${m.role==='user'?'你':'AI 编辑'} · ${pretty(m.created_at)}`));if(m.role==='assistant'){const details=processDetails(state.jobs.find(j=>j.id===m.job_id));if(details)item.append(details)}item.append(el('div','bubble',m.content.replace(/\\n/g,'\n')));if(m.article_id)item.append(btn('打开相关成稿 ↗',()=>openArticle(m.article_id)));if(m.role==='user')item.append(resendButton(m));else if(state.jobs.find(j=>j.id===m.job_id)?.status==='failed'){const original=messages.find(x=>x.role==='user'&&x.job_id===m.job_id);if(original)item.append(resendButton(original))}box.append(item)}
 const pending=state.jobs.filter(j=>j.kind==='chat'&&j.conversation_id===activeConversation&&['queued','running'].includes(j.status)).reverse();
 for(const job of pending){const item=el('div','message live-message');item.append(el('div','role',job.status==='queued'?'AI 编辑 · 等待处理':'AI 编辑 · 实时输出'));const details=processDetails(job);if(details)item.append(details);const text=job.stream?.answer|| (job.status==='queued'?'已记下你的想法，等待前面的任务完成。':job.result?.stage||'正在连接 AI…');item.append(el('div','bubble streaming-text',text.replace(/\\n/g,'\n')));box.append(item)}
 box.querySelectorAll('[data-job]').forEach(n=>{const saved=scrolls.get(n.dataset.job);if(saved){const list=n.querySelector('.process-list'),draft=n.querySelector('.draft-text');if(list)list.scrollTop=saved[0];if(draft)draft.scrollTop=saved[1]}});
 const id=messages.at(-1)?.id||0;box.scrollTop=nearBottom||id!==lastMessageId?box.scrollHeight:oldTop;lastMessageId=id;
}
function connectStream(){
 if(eventSource)return;
 eventSource=new EventSource('api/events?after='+(state?.event_cursor||0));
 eventSource.addEventListener('update',event=>{
  const data=JSON.parse(event.data),job=state?.jobs.find(j=>j.id===data.job_id);
  if(!job)return;
  if(data.kind==='finished'){refresh();return}
  job.stream_cursor=Number(event.lastEventId)||0;job.stream ||= {progress:[],answer:'',draft:''};
  if(data.kind==='progress'){const record={key:data.key,phase:data.phase,text:data.text,time:data.created_at};const i=job.stream.progress.findIndex(p=>p.key===record.key);if(i>=0)job.stream.progress[i]=record;else job.stream.progress.push(record)}
  if(['answer','draft'].includes(data.kind))job.stream[data.kind]=data.text;
  renderMessages();
 });
}
function renderJobs(){const jobs=$('#jobs');jobs.replaceChildren();for(const j of state.jobs){const n=el('div','job');n.append(badge(statusLabels[j.status]||j.status,j.status),el('strong','',jobLabels[j.kind]||j.kind),el('p','',pretty(j.created_at)));if(j.result?.stage)n.append(el('p','',j.result.stage));if(j.result?.answer)n.append(el('p','',j.result.answer));if(j.error)n.append(el('p','job-error',j.error));jobs.append(n)}if(!state.jobs.length)jobs.append(el('p','empty','还没有工作台任务。'));const runs=$('#runs');runs.replaceChildren();for(const r of state.runs){const n=el('div','run');n.append(badge(r.error?'需要处理':r.notified?'已完成':'执行中',r.error?'failed':r.notified?'done':'running'),el('strong','',r.date));const pub=(r.articles||[]).filter(x=>x.status==='published').length;n.append(el('p','',`已提交发布 ${pub} 篇 · ${r.completed_at?pretty(r.completed_at):'尚未完成通知'}`));if(r.progress)n.append(el('p','',`${r.progress.stage}${r.progress.detail?' · '+r.progress.detail:''}`));for(const a of r.articles||[])n.append(el('p','',`${a.title} · ${a.review_status||statusLabels[a.status]||a.status}`));if(r.error)n.append(el('p','job-error',r.error));runs.append(n)}if(!state.runs.length)runs.append(el('p','empty','还没有每日运行记录。'));const login=state.jobs.find(j=>j.qr_ready);$('#qr-panel').hidden=!login;if(login)$('#qr').src='api/qr/'+login.id+'?t='+Date.now()}
function render(){
 $('#article-count').textContent=state.articles.filter(a=>a.status!=='deleted').length;$('#stat-published').textContent=state.articles.filter(a=>a.status==='published').length;$('#stat-ready').textContent=state.articles.filter(a=>a.status==='ready').length+' 篇成稿待发布';$('#stat-views').textContent=num(totals('views'));$('#stat-likes').textContent=num(totals('likes'));$('#stat-engagement').textContent=num(totals('comments'))+' / '+num(totals('favorites'));const s=state.meta.sync;const syncError=state.meta.sync_error;$('.account').textContent=syncError?'● 账号同步需检查':s?'● 知乎账号已连接':'● 等待账号同步';$('#metric-coverage').textContent=s?`覆盖 ${s.captured} / ${s.reported_count??'未知'} 篇文章`:'等待首次同步';$('#sync-info').textContent=s?`最近同步 ${pretty(s.observed_at)} · ${s.source}。${s.coverage==='partial'?'当前为部分采样。':''}曲线为采样累计值，非单日新增；覆盖变化会影响对比。`:'尚未同步知乎数据';$('#schedule-info').textContent=`${state.schedule.windows?.length?'早 08–11 · 午 12–14 · 晚 18–21 随机发布':'每天 '+state.schedule.time+' 启动'} · ${state.schedule.article_layout?.includes('long')?'1 篇万字长文 + 2 篇短文':state.schedule.count+' 篇'} · 最多 ${state.schedule.review_max_rounds} 轮审稿`;$('#last-update').textContent='工作台更新于 '+pretty(state.updated_at);const rs=$('#recent-articles');rs.replaceChildren();state.articles.filter(a=>a.status==='published').slice(0,5).forEach((a,i)=>{const item=el('div','recent');item.tabIndex=0;item.role='button';item.onclick=()=>openArticle(a.id);item.onkeydown=e=>{if(e.key==='Enter')openArticle(a.id)};const detail=el('div');detail.append(el('h3','recent-title',a.title),el('p','',`${articleStatus(a)} · 阅读 ${num(a.views)} · 赞同 ${num(a.likes)}`));item.append(el('span','recent-index',String(i+1).padStart(2,'0')),detail);rs.append(item)});renderChart();renderArticles();renderMessages();renderJobs();renderOperations();renderSchedule();renderChallenges();const syncRunning=state.jobs.some(j=>j.kind==='sync'&&['queued','running'].includes(j.status));$('#sync').disabled=syncRunning;$('#sync').textContent=syncRunning?'同步进行中…':'↻ 同步知乎数据';$('#login').disabled=state.jobs.some(j=>j.kind==='login'&&['queued','running'].includes(j.status))
}
async function refresh(){try{const next=await api('state');for(const j of next.jobs){const old=state?.jobs.find(x=>x.id===j.id);if(old?.stream_cursor>next.event_cursor){j.stream=old.stream;j.stream_cursor=old.stream_cursor}}state=next;render();if(window.renderWorkspace)window.renderWorkspace();connectStream()}catch(e){notify(e.message)}}
function selectArticle(a){if(a.conversation_id&&a.conversation_id!==activeConversation&&state.conversations.some(c=>c.id===a.conversation_id))switchConversation(a.conversation_id);if(window.showManuscript)window.showManuscript(a);selected={id:a.id,title:a.title};$('#selection').hidden=false;$('#selection').replaceChildren(document.createTextNode('正在讨论：'+a.title),btn('×',()=>{selected=null;$('#selection').hidden=true}));$('#article-dialog').close();showView('chat');$('#chat-input').focus()}
let readerImages=[],readerImageIndex=0;
function validArticleImage(value){try{const u=new URL(value,location.origin);return u.origin===location.origin&&/^\/studio\/(?:readings|api\/feedback\/image)\//.test(u.pathname)?u.href:null}catch{return null}}
function articleImages(article){return (article.data?.illustrations||[]).map(im=>({...im,url:validArticleImage(im.url)})).filter(im=>im.url)}
function showImage(images,index){readerImages=images;readerImageIndex=(index+images.length)%images.length;const im=images[readerImageIndex];if(!im)return;const viewer=$('#image-viewer');viewer.classList.remove('actual-size');$('#image-viewer-size').textContent='原始尺寸';$('#image-viewer-img').src=im.url;$('#image-viewer-img').alt=im.caption||'文章配图';$('#image-viewer-count').textContent=`${readerImageIndex+1} / ${images.length}`;$('#image-viewer-caption').textContent=im.caption||'';$('#image-viewer-prev').disabled=$('#image-viewer-next').disabled=images.length<2;if(!viewer.open)viewer.showModal()}
function setReaderFullscreen(value){$('#article-dialog').classList.toggle('reader-fullscreen',value);$('#reader-fullscreen').textContent=value?'退出全屏':'全屏阅读';$('#reader-fullscreen').setAttribute('aria-pressed',String(value))}
$('#reader-fullscreen').onclick=()=>setReaderFullscreen(!$('#article-dialog').classList.contains('reader-fullscreen'));
$('#article-dialog').addEventListener('cancel',e=>{if($('#article-dialog').classList.contains('reader-fullscreen')){e.preventDefault();setReaderFullscreen(false)}});
$('#article-dialog').addEventListener('close',()=>setReaderFullscreen(false));
$('#image-viewer-close').onclick=()=>$('#image-viewer').close();
$('#image-viewer-prev').onclick=()=>showImage(readerImages,readerImageIndex-1);$('#image-viewer-next').onclick=()=>showImage(readerImages,readerImageIndex+1);
$('#image-viewer-size').onclick=()=>{const actual=$('#image-viewer').classList.toggle('actual-size');$('#image-viewer-size').textContent=actual?'适应屏幕':'原始尺寸'};
$('#image-viewer').addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();showImage(readerImages,readerImageIndex+(e.key==='ArrowRight'?1:-1))}});
function appendArticleBody(container,article){
 const blocks=article.data?.blocks?.length?article.data.blocks:[{type:'paragraph',text:article.body||'这篇文章还没有本地全文。'}],images=articleImages(article),chapters=article.data?.chapters||[];
 for(let i=0;i<=blocks.length;i++){
  for(const chapter of chapters.filter(ch=>ch.before_block===i)){const heading=el('h2','reader-chapter',chapter.title);heading.dataset.chapterIndex=i;container.append(heading)}
  for(const [index,im] of images.entries())if(Math.min(blocks.length,Math.max(0,Number.isInteger(im.before_block)?im.before_block:0))===i){
   const figure=el('figure','article-illustration'),button=el('button','image-open'),img=el('img');button.type='button';button.setAttribute('aria-label','放大查看：'+(im.caption||'文章配图'));button.onclick=()=>showImage(images,index);img.src=im.url;img.alt=im.caption||'文章配图';img.loading=index===0?'eager':'lazy';img.decoding='async';img.width=1536;img.height=1024;
   const retry=btn('图片加载失败，点击重试',()=>{img.hidden=false;retry.hidden=true;img.src=im.url+(im.url.includes('?')?'&':'?')+'retry='+Date.now()});retry.hidden=true;img.onerror=()=>{img.hidden=true;retry.hidden=false};button.append(img);figure.append(button,retry);figure.append(el('figcaption','',(im.caption?im.caption+' · ':'')+'点击图片放大'));container.append(figure);
  }
  if(i<blocks.length)container.append(el(blocks[i].type==='heading'?'h2':'p','',blocks[i].text));
 }
}
async function openArticle(id,fullscreen=false){try{const a=await api('article/'+id);const panel=$('#article-detail');panel.replaceChildren(el('h1','',a.title),el('p','article-meta',`${articleStatus(a)} · ${pretty(a.created_at)}`));const imageCount=articleImages(a).length;panel.append(el('p','reader-info',`${(a.body||'').replace(/\s/g,'').length.toLocaleString()} 字符 · ${imageCount?imageCount+' 幅配图 · 点击图片可放大':'暂无配图'}`));appendArticleBody(panel,a);const headings=[...panel.querySelectorAll('h2')];if(headings.length){const toc=el('details','reader-toc');toc.append(el('summary','','章节目录'));headings.forEach(h=>toc.append(btn(h.textContent,()=>h.scrollIntoView({block:'start',behavior:'smooth'}))));panel.insertBefore(toc,panel.querySelector('h2')||panel.children[3])}const actions=$('#article-actions');actions.replaceChildren(btn('与 AI 讨论这篇',()=>selectArticle(a),false));if(a.status==='ready')actions.append(btn('删除草稿',()=>changeTrash([a.id],false)));if(a.status==='deleted')actions.append(btn('恢复草稿',()=>changeTrash([a.id],true)));if(a.body)actions.append(btn('复制全文',async()=>{try{await navigator.clipboard.writeText(a.title+'\n\n'+a.body);notify('全文已复制。')}catch(e){notify('浏览器未允许复制，请在文章中选择文字复制。')}}));if(a.data?.preview_url)actions.append(link('阅读完整图文版 ↗',a.data.preview_url));if(a.url)actions.append(link('打开知乎原文 ↗',a.url));if(!a.preview_only&&!a.data?.preview_only&&['ready','publishing','publish_failed'].includes(a.status))actions.append(btn(a.status==='ready'?'发布到知乎':'核对并恢复发布',()=>publish(a.id),false));if(!a.body&&a.url)actions.append(btn('从知乎读取全文',async()=>{try{await api('read',{article_id:a.id});notify('已加入全文读取队列，完成后重新打开文章即可查看。');$('#article-dialog').close();await refresh()}catch(e){notify(e.message)}},false));setReaderFullscreen(fullscreen);if(!$('#article-dialog').open)$('#article-dialog').showModal();$('#article-dialog').scrollTop=0;}catch(e){notify(e.message)}}
async function publish(id){try{await api('publish',{article_id:id});notify('发布任务已加入队列，将核对正文并提交知乎。');$('#article-dialog').close();await refresh()}catch(e){notify(e.message)}}
$$('[data-view]').forEach(n=>n.onclick=e=>{e.preventDefault();showView(n.dataset.view)});$$('[data-go]').forEach(n=>n.onclick=()=>showView(n.dataset.go));$('#start-writing').onclick=()=>showView('chat');$('#close-dialog').onclick=()=>$('#article-dialog').close();$('#search').oninput=renderArticles;$('#status-filter').onchange=renderArticles;$$('[data-example]').forEach(n=>n.onclick=()=>{$('#chat-input').value=n.dataset.example;$('#chat-input').focus()});$('#sync').onclick=async()=>{try{await api('sync',{});notify('已加入同步队列，正在读取知乎创作中心。');await refresh()}catch(e){notify(e.message)}};$('#login').onclick=async()=>{try{await api('login',{});notify('正在检查登录，若需要扫码，二维码会在本页显示并发到邮箱。');await refresh()}catch(e){notify(e.message)}};$('#chat-form').onsubmit=async e=>{e.preventDefault();const input=$('#chat-input'),text=input.value.trim();if(!text)return;$('#send').disabled=true;try{await api('chat',{message:text,article_id:selected?.id||null,conversation_id:activeConversation,model:$('#chat-model').value});input.value='';await refresh()}catch(e){notify(e.message)}finally{$('#send').disabled=false}};
refresh();setInterval(refresh,5000);

const operationLabels={pending:'等待巡查',discovering:'正在巡查',discovered:'巡查已完成',writing:'正在写作',reviewing:'独立审稿中',publishing:'正在提交',done:'已完成',blocked:'访问受限 / 等待处理',failed:'需要处理',uncertain:'提交结果待核对',ready:'审稿通过',published:'已提交发布',preparing:'正在准备短文',missed:'已错过时段',interrupted:'进程中断'};
function renderSchedule(){
 const box=$('#schedule-plans');if(!box)return;box.replaceChildren();
 for(const plan of state.plans||[]){const n=el('div','run');n.append(el('h3','',plan.date+' · 三篇短文计划'));
 for(const slot of plan.slots){n.append(el('p','',`${slot.label} ${slot.start.slice(11,16)}–${slot.end.slice(11,16)} · 随机发布时间 ${slot.publish_at.slice(11,16)} · ${slot.status==='pending'?'等待准备':slot.status==='ready'?'等待发布':operationLabels[slot.status]||slot.status}`));if(slot.error)n.append(el('p','job-error',slot.error));}box.append(n);}
}
function renderOperations(){
 const box=$('#operations-runs');if(!box)return;const opened=new Set([...box.querySelectorAll('details[open][data-key]')].map(n=>n.dataset.key));const section=(key,cls='run')=>{const n=el('details',cls);n.dataset.key=key;n.open=opened.has(key);return n;};box.replaceChildren();
 for(const run of state.operations_runs||[]){const n=el('section','box');n.append(el('h2','',run.date+' · '+(operationLabels[run.status]||run.status)));
 if(run.observed_at)n.append(el('p','fine','巡查于 '+pretty(run.observed_at)));
 if(run.error)n.append(el('p','job-error',run.error));
 n.append(el('h3','',`内容与提交记录（${run.items?.length||0}）`));
 for(const item of run.items||[]){const d=section(run.date+':item:'+item.kind+':'+(item.target_url||item.title));d.append(el('summary','',`${item.kind==='answer'?'回答':'提问'} · ${item.title} · ${operationLabels[item.status]||item.status}`));for(const para of item.body.split('\n'))if(para)d.append(el('p','',para));d.append(el('p','fine',item.reason));if(item.url)d.append(link('查看已提交内容 ↗',item.url));else if(item.target_url)d.append(link('查看原问题 ↗',item.target_url));n.append(d);}
 if(!run.items?.length)n.append(el('p','fine','暂无已生成或已提交内容。'));
 const acts=section(run.date+':activities');acts.append(el('summary','',`发现活动与圆桌（${run.activities?.length||0}）`));for(const a of run.activities||[]){const p=el('p');p.append(link(a.title+' ↗',a.url));acts.append(p);}if(run.activity_overview){const more=section(run.date+':activity-overview','');more.append(el('summary','','活动中心现场记录'));for(const line of run.activity_overview.split('\n'))if(line)more.append(el('p','',line));acts.append(more);}n.append(acts);
 const qs=section(run.date+':questions');qs.append(el('summary','',`候选问题（${run.questions?.length||0}）`));for(const q of run.questions||[]){const p=el('p');p.append(link(q.title+' ↗',q.url));qs.append(p);}n.append(qs);
 if(run.report){const report=section(run.date+':report');report.append(el('summary','','选题与审稿记录'),el('p','',run.report));n.append(report);}box.append(n);}
 if(!state.operations_runs?.length)box.append(el('p','empty','尚无巡查记录，每天 15:00 开始执行。'));
}

function renderChallenges(){
 const box=$('#challenge-runs');if(!box)return;box.replaceChildren();
 const cfg=state.schedule.challenge;$('#challenge-schedule').textContent=cfg?.enabled?`每天 ${cfg.time} 自动打卡 · 晚间文章优先 · 延迟计入时仅复查，不重复提交`:'每日自动打卡未启用';
 const labels={pending:'等待执行',checking:'核对活动进度',running:'正在完成任务',completed:'今日打卡已完成',needs_attention:'待计入 / 需要处理'};
 for(const run of state.challenge_runs||[]){const n=el('div','run');n.append(el('strong','',`${run.date} · ${labels[run.status]||run.status}`),el('p','',`创作 ${run.creation||'待核对'} · 互动 ${run.interaction||'待核对'} · 核验 ${pretty(run.verified_at||run.last_checked_at)}`));if(run.summary)n.append(el('p','',run.summary));if(run.error)n.append(el('p','job-error',run.error));for(const a of run.actions||[]){const line=el('p','',`${a.task} · ${a.status} · ${a.detail}`);if(/^https:\/\/(?:www|zhuanlan)\.zhihu\.com\//.test(a.url||''))line.append(link('查看 ↗',a.url));n.append(line);}box.append(n);}
 if(!state.challenge_runs?.length)box.append(el('p','fine','尚无自动打卡记录。'));
}
