// Public dictionary reader only: fresh browser, no account profile or credentials.
import puppeteer from 'puppeteer';
const target=new URL(process.argv[2]);
if(target.protocol!=='https:'||target.hostname!=='yougengbaike.com'||target.username||target.password||target.port)throw Error('Dictionary host is not allowed');
const browser=await puppeteer.launch({headless:true,acceptInsecureCerts:true,args:['--no-sandbox','--disable-setuid-sandbox']});
try{
 const page=await browser.newPage();await page.setRequestInterception(true);
 page.on('request',r=>{const u=new URL(r.url());if(u.hostname===target.hostname&&u.protocol==='https:'&&!['image','media','font'].includes(r.resourceType()))r.continue();else r.abort();});
 const response=await page.goto(target.href,{waitUntil:'networkidle2',timeout:10000});
 if(!response||response.status()!==200){
  if(!target.pathname.startsWith('/article/'))throw Error('Dictionary page unavailable');
  await page.goto(target.origin+'/',{waitUntil:'networkidle2',timeout:10000});
  const clicked=await page.evaluate(path=>{const link=[...document.querySelectorAll('a[href]')].find(a=>new URL(a.href).pathname===path);if(!link)return false;link.click();return true;},target.pathname);
  if(!clicked)throw Error('Dictionary entry not found');
  await page.waitForNetworkIdle({idleTime:800,timeout:5000}).catch(()=>{});
  if(new URL(page.url()).pathname!==target.pathname)throw Error('Entry navigation failed');
 }
 if((await page.title()).includes('404'))throw Error('Dictionary entry unavailable');
 const result=await page.evaluate(()=>({url:location.href,title:document.title,text:document.body.innerText.slice(0,50000),links:[...document.querySelectorAll('a[href]')].map(a=>({title:a.innerText,url:a.href,date:null})).filter(a=>a.title).slice(0,200)}));
 if(target.pathname.startsWith('/article/')&&result.title==='有梗百科 - 让有梗青年快人一步')throw Error('Only directory loaded, not entry body');
 result.retrieval='独立浏览器（站点证书异常，仅作释义线索）';result.transport_verified=false;
 console.log(JSON.stringify(result));
}finally{await browser.close();}
