// Read only: expands text and records article-level counters; never votes/comments.
import puppeteer from 'puppeteer';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
const url=process.argv[2],out=process.argv[3];
if(!/^https:\/\/www\.zhihu\.com\/question\/\d+\/answer\/\d+$/.test(url)||!out)throw Error('Provide a canonical answer URL and evidence output path');
const answerId=url.split('/').at(-1);
const {name}=JSON.parse(await readFile('private/active-profile.json','utf8'));
if(!/^browser-profile(?:-\d+)?$/.test(name))throw Error('Invalid profile');
const browser=await puppeteer.launch({headless:true,userDataDir:path.join(process.cwd(),'private',name),args:['--no-sandbox','--disable-dev-shm-usage']});
try {
 const p=await browser.newPage();
 await p.goto('https://www.zhihu.com/follow',{waitUntil:'domcontentloaded',timeout:60000});
 let link;
 for(let attempt=0;attempt<4;attempt++) {
  await new Promise(r=>setTimeout(r,1800));link=await p.$(`a[href*="/answer/${answerId}"]`);if(link)break;
  await p.evaluate(()=>window.scrollBy(0,innerHeight));
 }
 if(!link)throw Error('回答未出现在可访问关注流；未绕过访问限制');
 const card=await link.evaluateHandle(a=>a.closest('.ContentItem'));
 for(const b of await card.$$('button'))if(await b.evaluate(e=>e.innerText.includes('阅读全文'))){await b.click();break;}
 await new Promise(r=>setTimeout(r,1500));
 const data=await card.evaluate(e=>({title:e.querySelector('h2')?.innerText,body:e.querySelector('.RichContent-inner')?.innerText,buttons:[...e.querySelectorAll('button')].map(b=>b.innerText.replace(/[\u200b-\u200d\ufeff]/g,'').trim()),author:e.querySelector('.AuthorInfo-name')?.innerText||null}));
 const vote=data.buttons.find(t=>/^赞同\s+[\d,.万]+$/.test(t));
 const comment=data.buttons.find(t=>/^[\d,.万]+\s*条评论$/.test(t));
 function number(t){const m=t.match(/[\d,.]+/);if(!m)return null;return Math.round(Number(m[0].replaceAll(',',''))*(t.includes('万')?10000:1));}
 if(!vote || !comment || !data.body || data.body.length<300)throw Error('无法确认回答全文或文章级指标');
 const result={platform:'zhihu',url,title:data.title,author:data.author,observed_at:new Date().toISOString(),verification:'live_dom',metric_label:'赞同',likes:number(vote),comments:number(comment),body_length:data.body.length,body_sha256:createHash('sha256').update(data.body).digest('hex'),evidence:{location:'登录后的关注流，指定回答卡片',vote_text:vote,comment_text:comment,full_text_expanded:true}};
 await mkdir(path.dirname(out),{recursive:true,mode:0o700});await writeFile(out,JSON.stringify(result,null,2),{flag:'wx',mode:0o600});console.log(JSON.stringify(result));
} finally{await browser.close();}
