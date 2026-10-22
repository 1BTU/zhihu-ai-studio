// Read-only activity verification. Caller must hold private/daily.lock.
import puppeteer from 'puppeteer';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const folder=path.resolve(process.argv[2]);
const config=JSON.parse(await fs.readFile(path.join(root,'daily-config.json'),'utf8'));
const url=config.challenge?.url;
if(!/^https:\/\/www\.zhihu\.com\/parker\/campaign\/\d+(?:\?[^#]*)?$/.test(url||''))throw Error('无效挑战赛网址');
const {name}=JSON.parse(await fs.readFile(path.join(root,'private/active-profile.json'),'utf8'));
if(!/^browser-profile(?:-\d+)?$/.test(name))throw Error('无效账号目录');
await fs.mkdir(folder,{recursive:true,mode:0o700});
const b=await puppeteer.launch({headless:true,userDataDir:path.join(root,'private',name),args:['--no-sandbox','--disable-dev-shm-usage']});
try{const p=await b.newPage();await p.goto(url,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForFunction(()=>document.body.innerText.includes('今日任务')||/登录|请求存在异常|活动已结束/.test(document.body.innerText),{timeout:15000});await new Promise(r=>setTimeout(r,2500));const data=await p.evaluate(()=>({url:location.href,text:document.body.innerText}));data.checked_at=new Date().toISOString();await fs.writeFile(path.join(folder,'probe.json'),JSON.stringify(data,null,2),{mode:0o600});await p.screenshot({path:path.join(folder,'activity.png'),fullPage:true});console.log(JSON.stringify({url:data.url,checked_at:data.checked_at}));}finally{await b.close()}
