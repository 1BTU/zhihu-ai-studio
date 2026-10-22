import puppeteer from 'puppeteer';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const [mode,folderArg,inputArg]=process.argv.slice(2),folder=path.resolve(folderArg);
await fs.mkdir(folder,{recursive:true,mode:0o700});
const save=async(name,data)=>{const p=path.join(folder,name);await fs.writeFile(p+'.tmp',JSON.stringify(data,null,2),{mode:0o600});await fs.rename(p+'.tmp',p);};
const {name}=JSON.parse(await fs.readFile(path.join(root,'private/active-profile.json'),'utf8'));
if(!/^browser-profile(?:-\d+)?$/.test(name))throw Error('Invalid profile');
const browser=await puppeteer.launch({headless:true,userDataDir:path.join(root,'private',name),args:['--no-sandbox','--disable-dev-shm-usage'],defaultViewport:{width:1440,height:1000}});
const page=await browser.newPage();
const visit=async url=>{await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});await new Promise(r=>setTimeout(r,3500));if(/signin|signup|account\/unhuman/.test(page.url()))throw Error('登录或验证未完成');if(await page.evaluate(()=>/您当前请求存在异常|暂时限制本次访问|安全验证/.test(document.body.innerText)))throw Error('知乎限制本次访问，请稍后通过官方页面检查');};
const capture=()=>page.evaluate(()=>({url:location.href,text:document.body.innerText.slice(0,22000),links:[...document.querySelectorAll('a[href]')].map(a=>({title:a.innerText.trim(),url:a.href})).filter(a=>a.title&&/^https:\/\/(www|zhuanlan)\.zhihu\.com\//.test(a.url))}));
try {
 if(mode==='discover'){
  const pages=[],errors=[];
  for(const url of ['https://www.zhihu.com/creator','https://www.zhihu.com/creator/activity','https://www.zhihu.com/question/waiting']){
   try{await visit(url);pages.push(await capture());}catch(e){errors.push({url,error:e.message});}
  }
  if(!pages.length)throw Error('无法读取知乎页面');
  const links=pages.flatMap(p=>p.links),unique=new Map();
  for(const l of links){const q=l.url.match(/^https:\/\/www\.zhihu\.com\/question\/(\d+)(?:[?#]|$)/);if(q&&l.title.length>8)unique.set(q[1],{title:l.title,url:'https://www.zhihu.com/question/'+q[1]});}
  const activities=[...new Map(links.filter(l=>/\/parker\/campaign\/|\/roundtable\/|\/special\//.test(l.url)).map(l=>[l.url,l])).values()];
  const details=[];
  for(const q of [...unique.values()].slice(0,6)){
   try{await visit(q.url);const detail=await capture();const title=await page.$eval('h1',e=>e.innerText.trim());if(title){q.title=title;details.push({...q,text:detail.text.slice(0,9000)});}}catch(e){errors.push({url:q.url,error:e.message});if(/限制|验证/.test(e.message))break;}
  }
  const data={observed_at:new Date().toISOString(),questions:[...unique.values()].slice(0,35),details,activities,pages,errors};await save('discovery.json',data);console.log(JSON.stringify({questions:data.questions.length,activities:activities.length,errors}));
 } else if(mode==='inspect'){
  if(!/^https:\/\/www\.zhihu\.com\/question\/\d+$/.test(inputArg))throw Error('Invalid question');
  await visit(inputArg);await save('question-page.json',await capture());
  const trigger=await page.$('button ::-p-text(写回答)')||await page.$('::-p-text(写回答)');
  if(trigger){await trigger.click();await new Promise(r=>setTimeout(r,2000));}
  await save('answer-editor.json',await page.evaluate(()=>({url:location.href,text:document.body.innerText.slice(0,12000),fields:[...document.querySelectorAll('[contenteditable="true"],textarea')].map(e=>({html:e.outerHTML.slice(0,1500)})),buttons:[...document.querySelectorAll('button')].filter(e=>/发布|回答/.test(e.innerText)).map(e=>({text:e.innerText,html:e.outerHTML.slice(0,600)}))})));
 } else if(mode==='publish'){
  const input=path.resolve(inputArg);
  if(path.dirname(input)!==folder||!/^item-\d+\.json$/.test(path.basename(input)))throw Error('Invalid item path');
  const item=JSON.parse(await fs.readFile(input,'utf8'));
  const proofName=path.basename(input).replace('.json','-proof.json');
  let old=JSON.parse(await fs.readFile(path.join(folder,proofName),'utf8').catch(()=>'{}'));
  if(old.published){console.log(JSON.stringify(old));}
  else {
   if(old.requested_at)throw Error('已有提交记录，必须核对结果，不重复提交');
   if(!['answer','question'].includes(item.kind)||typeof item.body!=='string'||item.body.length<400||item.body.length>2200)throw Error('内容校验失败');
   let expectedId;
   if(item.kind==='answer'){
    const m=item.target_url.match(/^https:\/\/www\.zhihu\.com\/question\/(\d+)$/);if(!m)throw Error('Invalid question');expectedId=m[1];
    await visit(item.target_url);
    const title=await page.$eval('h1',e=>e.innerText.trim()).catch(()=>'');
    if(title.replace(/\s/g,'')!==item.title.replace(/\s/g,''))throw Error('问题标题发生变化，停止提交');
    if(await page.evaluate(()=>/查看我的回答|编辑回答/.test(document.body.innerText)))throw Error('已有回答，停止重复提交');
    const trigger=await page.$('button ::-p-text(写回答)')||await page.$('::-p-text(写回答)');if(!trigger)throw Error('回答入口不可用');
    await trigger.click();await new Promise(r=>setTimeout(r,2000));
   }else{
    await visit('https://www.zhihu.com/creator');
    const trigger=await page.$('::-p-text(提问题)');if(!trigger)throw Error('提问入口不可用');await trigger.click();
    await page.waitForSelector('textarea[placeholder="写下你的问题，准确地描述问题更容易得到解答"]',{timeout:10000});
    await page.locator('textarea[placeholder="写下你的问题，准确地描述问题更容易得到解答"]').fill(item.title);
    await new Promise(r=>setTimeout(r,2000));
   }
   const editors=[];
   for(const e of await page.$$('[contenteditable="true"]'))if(await e.evaluate(e=>e.getClientRects().length>0))editors.push(e);
   if(editors.length!==1)throw Error('编辑器不唯一，停止提交');
   const ed=editors[0];if(await ed.evaluate(e=>e.innerText.trim()))throw Error('编辑器已有内容，保留原稿');
   const text=item.body+(item.sources.length?'\n\n参考资料\n'+item.sources.map(s=>s.title+'\n'+s.url).join('\n\n'):'');
   await ed.click();for(const [i,line] of text.split('\n').entries()){if(i)await page.keyboard.press('Enter');if(line)await page.keyboard.sendCharacter(line);}
   if((await ed.evaluate(e=>e.innerText)).replace(/\s/g,'')!==text.replace(/\s/g,''))throw Error('编辑器正文核对失败');
   const buttons=[];const labels=item.kind==='answer'?['发布回答','提交回答']:['发布问题'];
   for(const b of await page.$$('button'))if(await b.evaluate((e,labels)=>labels.includes(e.innerText.trim())&&!e.disabled&&e.getClientRects().length>0,labels))buttons.push(b);
   if(buttons.length!==1)throw Error('无法唯一确认发布按钮');
   old={kind:item.kind,title:item.title,target_url:item.target_url,requested_at:new Date().toISOString()};await save(proofName,old);
   const endpoint=item.kind==='answer'?new RegExp('/api/v\\d+/questions/'+expectedId+'/answers(?:\\?|$)'):/\/api\/v\d+\/questions(?:\?|$)/;
   const responsePromise=page.waitForResponse(r=>r.request().method()==='POST'&&endpoint.test(r.url()),{timeout:30000}).catch(()=>null);
   await buttons[0].click();const response=await responsePromise;
   if(!response)throw Error('未收到发布回执，需人工核对');
   const data=await response.json().catch(()=>({}));
   if(!response.ok()||!data.id)throw Error('发布回执未确认成功');
   if(item.kind==='answer'&&String(data.question?.id)!==expectedId)throw Error('回执中的问题不匹配');
   const url=item.kind==='answer'?item.target_url+'/answer/'+data.id:'https://www.zhihu.com/question/'+data.id;
   await save(proofName,{...old,published:true,url,submitted_at:new Date().toISOString(),status:response.status(),review_status:'已提交，审核状态待同步'});
   console.log(JSON.stringify({published:true,url}));
  }
 } else {throw Error('Unsupported mode');}
} finally {await browser.close();}
