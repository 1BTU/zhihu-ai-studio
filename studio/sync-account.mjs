import puppeteer from 'puppeteer';
import fs from 'node:fs/promises';
const {name}=JSON.parse(await fs.readFile('private/active-profile.json','utf8'));
if(!/^browser-profile(?:-\d+)?$/.test(name))throw Error('无效会话');
const browser=await puppeteer.launch({headless:true,userDataDir:`${process.cwd()}/private/${name}`,args:['--no-sandbox','--disable-dev-shm-usage'],defaultViewport:{width:1440,height:1100}});
try{
 const p=await browser.newPage();await p.goto('https://www.zhihu.com/creator/manage/creation/article',{waitUntil:'networkidle2',timeout:60000});
 if(/signin|signup/.test(p.url()))throw Error('登录已失效，请恢复登录');
 await p.waitForFunction(()=>document.body.innerText.includes('共 ')||document.querySelector('.CreationManage-CreationCard'),{timeout:20000});
 const count=await p.evaluate(()=>Number(document.body.innerText.match(/共\s*(\d+)\s*条内容/)?.[1])||null);
 const collected=new Map();let pages=0;
 for(;pages<30;pages++){
  const rows=await p.evaluate(()=>[...document.querySelectorAll('.CreationManage-CreationCard')].map(card=>{
   const anchors=[...card.querySelectorAll('a[href]')];const a=anchors.find(a=>/^https:\/\/zhuanlan.zhihu.com\/p\/\d+$/.test(a.href)&&a.querySelector('.CreationCardTitle-wrapper'));
   if(!a)return null;
   const metrics={},raw={};for(const label of ['阅读','赞同','评论','收藏','喜欢']){
    const node=[...card.querySelectorAll('div')].find(n=>n.children.length===0&&n.textContent.trim()===label);
    const text=node?.previousElementSibling?.textContent.trim().replace(/,/g,'');raw[label]=text??null;
    metrics[label]=text&&/^\d+$/.test(text)?Number(text):null;
   }
   const text=card.innerText;
   return {url:a.href,title:a.querySelector('.CreationCardTitle-wrapper').innerText,published_label:a.querySelector('[data-tooltip]')?.getAttribute('data-tooltip')||null,excerpt:card.querySelector('.CreationCardContent-text')?.innerText||'',review_status:/审核未通过|审核失败/.test(text)?'审核未通过':/审核中/.test(text)?'审核中':/已下架/.test(text)?'已下架':'已发布',metrics,raw};
  }).filter(Boolean));
  const old=collected.size;for(const row of rows)collected.set(row.url,row);
  if(count&&collected.size>=count)break;
  const next=await p.$('button.PaginationButton-next');
  if(!next){
   await p.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
   const loaded=await p.waitForFunction(n=>document.querySelectorAll('.CreationManage-CreationCard').length>n,{timeout:7000},rows.length).then(()=>true).catch(()=>false);
   if(!loaded)break;
  }else{
   if(await next.evaluate(n=>n.disabled))break;
   await next.click();await new Promise(r=>setTimeout(r,2000));
  }
  if(collected.size===old&&pages>0)break;
 }
 console.log(JSON.stringify({observed_at:new Date().toISOString(),source:'知乎创作中心 / 内容管理 / 文章',reported_count:count,coverage:count&&collected.size>=count?'complete':'partial',articles:[...collected.values()]}));
}finally{await browser.close()}
