import {assertPublishWindow} from './publish-window.mjs';
import puppeteer from 'puppeteer';
import {imageState,verifyImages} from './zhihu-images.mjs';
import {readFile, writeFile, mkdir, rename} from 'node:fs/promises';
import path from 'node:path';
const root = process.cwd();
const recordPath = process.env.ZHIHU_RESULT_PATH || path.join(root,'artifacts/draft-result.json');
const out = process.env.ZHIHU_PUBLISH_DIR || path.join(root,'artifacts');
await mkdir(out,{recursive:true,mode:0o700});
const {name} = JSON.parse(await readFile('private/active-profile.json','utf8'));
const draft = JSON.parse(await readFile(recordPath,'utf8'));
const article = JSON.parse(await readFile(process.argv[2] || 'demo.json','utf8'));
if(draft.title !== article.title) throw Error('文章与草稿记录标题不一致');
if(!/^https:\/\/zhuanlan\.zhihu\.com\/p\/\d+\/edit$/.test(draft.url)) throw Error('无效草稿地址');
if(!/^browser-profile(?:-\d+)?$/.test(name)) throw Error('Invalid profile');
const publicUrl = draft.url.replace(/\/edit$/,'');
const browser = await puppeteer.launch({headless:true,userDataDir:path.join(root,'private',name),args:['--no-sandbox','--disable-dev-shm-usage'],defaultViewport:{width:1440,height:1000}});
const page = await browser.newPage();
await page.setCacheEnabled(false);
page.setDefaultTimeout(20000);
async function record(value) {
 await writeFile(recordPath+'.tmp',JSON.stringify(value,null,2),{mode:0o600});
 await rename(recordPath+'.tmp',recordPath);
}
async function creatorProof(wait=false) {
 await page.goto('https://www.zhihu.com/creator/manage/creation/article',{waitUntil:'domcontentloaded',timeout:60000});
 await page.waitForFunction(()=>document.body.innerText.includes('文章') && !document.body.innerText.includes('加载中'),{timeout:20000}).catch(()=>{});
 const matches=(url,title)=>[...document.querySelectorAll('a[href]')].filter(a=>a.href===url && a.innerText.includes(title) && a.innerText.includes('发布于')).map(a=>a.innerText);
 await page.waitForFunction((url,title)=>[...document.querySelectorAll('a[href]')].some(a=>a.href===url && a.innerText.includes(title) && a.innerText.includes('发布于')),{timeout:wait?10000:7000},publicUrl,article.title).catch(()=>{});
 let proof=await page.evaluate(matches,publicUrl,article.title);
 // The management list is a snapshot and does not update merely by waiting.
 if(wait && !proof.length) {
  for(let attempt=0;attempt<2 && !proof.length;attempt++) {
   await new Promise(r=>setTimeout(r,5000));
   await page.reload({waitUntil:'networkidle2',timeout:60000});
   proof=await page.evaluate(matches,publicUrl,article.title);
  }
 }
 return proof;
}
try {
 if(article.illustrations?.length){
  if(!draft.saved||!draft.imageSources)throw Error('图文草稿缺少图片保存凭证，停止发布');
  await page.goto(draft.url,{waitUntil:'networkidle2',timeout:60000});await page.waitForSelector('[contenteditable=true]');
  await page.waitForFunction(()=>[...document.querySelector('[contenteditable=true]').querySelectorAll('img')].every(img=>{img.loading='eager';return img.complete&&img.naturalWidth}),{timeout:60000});
  verifyImages(await imageState(page),article,draft.imageSources);
 }
 // Reconcile server state before clicking: a previous attempt may have succeeded.
 let proof=await creatorProof();
 let verifiedByPublishedEditor=false;
 if(!proof.length) {
  await page.goto(draft.url,{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForSelector('textarea[placeholder*="请输入标题"]');
  const content=await page.evaluate(()=>({title:document.querySelector('textarea[placeholder*="请输入标题"]').value,body:document.querySelector('[contenteditable="true"]')?.innerText}));
  if(article.illustrations?.length)content.body=(await imageState(page)).text;
  if(content.title!==article.title || content.body?.replace(/\s+/gu,'')!==article.body.replace(/\s+/gu,'')) throw Error('草稿内容与本地文章不一致，停止发布');
  const buttons=[];
  let updateButton=false;
  for(const button of await page.$$('button')) {
   const state=await button.evaluate(b=>({text:b.innerText.replace(/[\u200b-\u200d\ufeff]/g,'').trim(),visible:!!b.getClientRects().length,disabled:b.disabled}));
   if(state.text==='发布' && state.visible && !state.disabled) buttons.push(button);
   if(state.text==='更新' && state.visible && !state.disabled) updateButton=true;
  }
  // The editor switches to 更新 for an existing publication, even while the
  // creator list is still awaiting synchronization. Never submit it twice.
  if(updateButton && !buttons.length) verifiedByPublishedEditor=true;
  if(!verifiedByPublishedEditor) {
  if(draft.published) throw Error('本地记录已发布，但服务器状态不一致；停止重复提交');
  if(buttons.length!==1) throw Error(`可用发布按钮数量异常：${buttons.length}`);
  assertPublishWindow();
  draft.publishRequestedAt=new Date().toISOString();
  await record(draft);
  await buttons[0].click();
  await new Promise(r=>setTimeout(r,5000));
  await page.screenshot({path:path.join(out,'publish-step.png'),fullPage:true});
  await writeFile(path.join(out,'publish-step.json'),JSON.stringify(await page.evaluate(()=>({url:location.href,text:document.body.innerText.slice(-7000)})),null,2),{mode:0o600});
  // Creator center is the source of truth; public pages may be blocked on this server.
  proof=await creatorProof(true);
  if(!proof.length) {
   await page.goto(draft.url,{waitUntil:'networkidle2',timeout:60000});
   const confirmed=await page.evaluate(()=>({title:document.querySelector('textarea[placeholder*="请输入标题"]')?.value,body:document.querySelector('[contenteditable="true"]')?.innerText,update:[...document.querySelectorAll('button')].some(b=>b.innerText.replace(/[\u200b-\u200d\ufeff]/g,'').trim()==='更新' && !!b.getClientRects().length)}));
   if(article.illustrations?.length)confirmed.body=(await imageState(page)).text;
   verifiedByPublishedEditor=confirmed.update && confirmed.title===article.title && confirmed.body?.replace(/\s+/gu,'')===article.body.replace(/\s+/gu,'');
   if(!verifiedByPublishedEditor) throw Error('尚未取得服务器发布凭证，停止并保留记录，稍后核实后恢复');
  }
  }
 }
 const proofText=proof.join('\n');
 const reviewStatus=!proof.length?'已提交发布，审核状态待同步':/审核未通过|审核不通过|审核失败|未通过/.test(proofText)?'审核未通过':/审核中|待审核/.test(proofText)?'审核中':/已下架|已删除/.test(proofText)?'已下架或删除':'创作中心已发布';
 const result={...draft,published:true,publishedUrl:publicUrl,verifiedInCreatorCenter:!!proof.length,verifiedByPublishedEditor,reviewStatus,proof,verifiedAt:new Date().toISOString()};
 await record(result);
 await writeFile(path.join(out,'publish-verified.json'),JSON.stringify(result,null,2),{mode:0o600});
 await page.screenshot({path:path.join(out,'publish-verified.png'),fullPage:true});
 console.log(JSON.stringify(result));
} catch(error) {
 console.error(error.message);process.exitCode=1;
 await page.screenshot({path:path.join(out,'publish-error.png'),fullPage:true}).catch(()=>{});
} finally {await browser.close();}
