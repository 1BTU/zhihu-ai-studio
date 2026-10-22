import puppeteer from 'puppeteer';import fs from 'node:fs/promises';
const {name}=JSON.parse(await fs.readFile('private/active-profile.json','utf8'));
if(!/^browser-profile(?:-\d+)?$/.test(name))throw Error('无效会话');
const browser=await puppeteer.launch({headless:true,userDataDir:`${process.cwd()}/private/${name}`,args:['--no-sandbox','--disable-dev-shm-usage']});
try{const p=await browser.newPage();await p.goto('https://www.zhihu.com/creator/manage/creation/column',{waitUntil:'networkidle2',timeout:60000});if(/signin|signup/.test(p.url()))throw Error('知乎登录已失效');await p.waitForFunction(()=>document.body.innerText.includes('创建专栏')||document.querySelector('a[href*="zhuanlan.zhihu.com/"]'),{timeout:20000});
const columns=await p.evaluate(()=>[...document.querySelectorAll('a[href]')].filter(a=>/^https:\/\/zhuanlan.zhihu.com\/(?!p\/|write|drafts)[\w-]+\/?$/.test(a.href)&&a.innerText.trim()).map(a=>({id:a.href.split('/').filter(Boolean).at(-1),name:a.innerText.trim().split('\n')[0],url:a.href})));
console.log(JSON.stringify({observed_at:new Date().toISOString(),columns:[...new Map(columns.map(c=>[c.id,c])).values()],source:'知乎创作中心 / 专栏',empty:await p.evaluate(()=>document.body.innerText.includes('你还没有专栏'))}));}finally{await browser.close()}
