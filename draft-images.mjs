import {hasRich,pasteBlocks,verifyRich} from './zhihu-richtext.mjs';
import puppeteer from 'puppeteer';import fs from 'node:fs/promises';import path from 'node:path';import {imageState,verifyImages} from './zhihu-images.mjs';
const root=path.resolve('.'),source=process.argv[2],article=JSON.parse(await fs.readFile(source,'utf8'));
const recordPath=process.env.ZHIHU_RESULT_PATH||path.join(path.dirname(source),'draft-result.json');const record=async value=>{await fs.writeFile(recordPath+'.tmp',JSON.stringify(value,null,2),{mode:0o600});await fs.rename(recordPath+'.tmp',recordPath)};
let prior=await fs.readFile(recordPath,'utf8').then(JSON.parse).catch(e=>{if(e.code!=='ENOENT')throw e;return null});
if(prior&&!prior.saved&&prior.stage!=='empty-confirmed')throw Error('上次写入未确认，请核对已有草稿 '+prior.url+'，未新建重复草稿');
const {name}=JSON.parse(await fs.readFile('private/active-profile.json','utf8'));if(!/^browser-profile(?:-\d+)?$/.test(name))throw Error('Invalid browser profile');
const b=await puppeteer.launch({headless:true,userDataDir:path.join(root,'private',name),args:['--no-sandbox','--disable-dev-shm-usage'],defaultViewport:{width:1280,height:900}});const p=await b.newPage();p.setDefaultTimeout(60000);let draftUrl=prior?.url;
try{
 await p.goto(draftUrl||'https://zhuanlan.zhihu.com/write',{waitUntil:'networkidle2',timeout:60000});await p.waitForSelector('textarea[placeholder*="请输入标题"]');
 if(!prior||!prior.saved){
  const initial=await imageState(p);if(initial?.text.trim()||initial?.images.length)throw Error('编辑器已有正文或图片，停止写入；需按已有内容核对恢复');
  const existingTitle=await p.$eval('textarea[placeholder*="请输入标题"]',n=>n.value);if(existingTitle.trim()&&existingTitle!==article.title)throw Error('编辑器标题不同，停止写入');
  await p.locator('textarea[placeholder*="请输入标题"]').fill(article.title);await p.click('[contenteditable="true"]');
  await p.waitForFunction(()=>/\/p\/\d+\/edit/.test(location.pathname));draftUrl=p.url();await record({saved:false,title:article.title,url:draftUrl,stage:'writing',published:false});
  for(let i=0;i<=article.blocks.length;i++){
   if(i)await p.keyboard.press('Enter');
   for(const im of article.illustrations.filter(x=>x.before_block===i)){
    const file=await fs.realpath(im.local_path);if(!file.startsWith(root+'/private/')&&!file.startsWith(root+'/reports/'))throw Error('Invalid image path');
    const before=(await imageState(p)).images.length;
    await p.$eval('input[type=file][accept^="image/"]',n=>n.value='');const input=await p.$('input[type=file][accept^="image/"]');await input.uploadFile(file);
    for(let attempt=0;attempt<3;attempt++){
     await p.waitForFunction(count=>{const root=document.querySelector('[contenteditable=true]');const imgs=[...root.querySelectorAll('img')];return imgs.length===count+1&&(root.querySelector('.Editable-imageUploader-status.is-error')||imgs.every(x=>{x.loading='eager';return x.complete&&x.naturalWidth&&/^https:\/\/(?:[^/]*zhimg\.com|pic-private\.zhihu\.com)\//.test(x.src)}))},{timeout:120000},before);
     const failed=await p.$$('[contenteditable=true] figure:has(.Editable-imageUploader-status.is-error)');if(!failed.length)break;
     if(attempt===2||failed.length!==1)throw Error('图片上传失败，已保留草稿，请稍后重试');
     const isLast=await failed[0].evaluate((f,count)=>[...f.closest('[contenteditable=true]').querySelectorAll('figure')].indexOf(f)===count,before);if(!isLast)throw Error('失败图片位置异常，停止重试');
     console.log('重试当前图片上传',before+1,attempt+1);await failed[0].click();await new Promise(r=>setTimeout(r,2000));
    }
    console.log('Uploaded image',before+1,'at block',i);
    // Move out of the atomic image into the trailing editable paragraph.
    await p.focus('[contenteditable=true]');await p.keyboard.down('Control');await p.keyboard.press('End');await p.keyboard.up('Control');await p.keyboard.press('ArrowDown');
   }
   if(hasRich(article)&&i<article.blocks.length){let end=i+1;while(end<article.blocks.length&&!article.illustrations.some(im=>im.before_block===end))end++;await pasteBlocks(p,article.blocks.slice(i,end));i=end-1;}
   else if(i<article.blocks.length){const block=article.blocks[i];if(block.type==='heading'){await p.keyboard.type('##');await p.keyboard.press('Space')}if(block.text)await p.keyboard.sendCharacter(block.text)}
   if(i%50===0)console.log('Written blocks',i,'/',article.blocks.length);
  }
  await p.click('textarea[placeholder*="请输入标题"]');await new Promise(r=>setTimeout(r,6000));
 }
 await p.reload({waitUntil:'networkidle2',timeout:60000});await p.waitForSelector('[contenteditable=true]');await p.waitForFunction(()=>[...document.querySelector('[contenteditable=true]').querySelectorAll('img')].every(x=>{x.loading='eager';return x.complete&&x.naturalWidth}));
 const state=await imageState(p);await fs.writeFile(path.join(path.dirname(recordPath),'editor-state.json'),JSON.stringify(state),{mode:0o600});const images=verifyImages(state,article,prior?.imageSources);const title=await p.$eval('textarea[placeholder*="请输入标题"]',n=>n.value);if(title!==article.title)throw Error('标题保存不一致');
 const richText=await verifyRich(p,article);
 const result={richText,saved:true,published:false,title,url:p.url(),verifiedByReload:true,imageSources:images,imageCount:images.length};await record(result);await p.screenshot({path:path.join(path.dirname(recordPath),'image-draft-verified.png')});console.log(JSON.stringify(result));
}catch(e){await p.screenshot({path:path.join(path.dirname(recordPath),'image-draft-error.png')}).catch(()=>{});await fs.writeFile(path.join(path.dirname(recordPath),'editor-state.json'),JSON.stringify(await imageState(p)),{mode:0o600}).catch(()=>{});console.error(e.message,draftUrl||p.url());process.exitCode=1}finally{await b.close()}
