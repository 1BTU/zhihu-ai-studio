import puppeteer from 'puppeteer';
import {readFile, mkdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2]);
await mkdir(out, {recursive:true, mode:0o700});
const {name} = JSON.parse(await readFile(path.join(root,'private/active-profile.json'),'utf8'));
if (!/^browser-profile(?:-\d+)?$/.test(name)) throw new Error('Invalid profile');
const browser = await puppeteer.launch({headless:true,userDataDir:path.join(root,'private',name),args:['--no-sandbox','--disable-dev-shm-usage']});
const page = await browser.newPage();
const qrLimit = Math.max(1,Math.min(2,Number(process.env.ZHIHU_QR_LIMIT)||2));
const waitMs = Math.max(60,Math.min(300,Number(process.env.ZHIHU_LOGIN_WAIT)||180))*1000;
const emit = obj => console.log(JSON.stringify(obj));
try {
  await page.goto('https://zhuanlan.zhihu.com/write',{waitUntil:'domcontentloaded',timeout:60000});
  if (await page.waitForSelector('textarea[placeholder*="请输入标题"]',{timeout:15000}).catch(()=>null)) {
    emit({status:'ready'});
  } else {
    if (!/signin|signup/.test(page.url())) {
      await page.screenshot({path:path.join(out,'access-blocked.png')});
      emit({status:'blocked',message:'知乎编辑器不可访问，未确认是登录过期；未绕过验证。'});
      process.exitCode=2;
    } else {
      // The original page stays alive while Python sends the QR email.
      for (let attempt=1;attempt<=qrLimit;attempt++) {
        await page.goto('https://www.zhihu.com/signin',{waitUntil:'domcontentloaded',timeout:60000});
        await new Promise(r=>setTimeout(r,2000));
        const qr=await page.waitForSelector('canvas.Qrcode-qrcode',{timeout:15000}).catch(()=>null);
        if (!qr) throw new Error('没有可用的扫码登录二维码，可能需要其他验证');
        const image=path.join(out,`login-qr-${attempt}.png`);
        await qr.screenshot({path:image});
        emit({status:'qr',path:image,attempt,createdAt:new Date().toISOString()});
        const deadline=Date.now()+waitMs;
        while(Date.now()<deadline) {
          const cookies=await browser.cookies();
          if(cookies.some(c=>c.name==='z_c0' && c.value && /(^|\.)zhihu\.com$/.test(c.domain.replace(/^\./,'')))) {
            await page.goto('https://zhuanlan.zhihu.com/write',{waitUntil:'domcontentloaded',timeout:60000});
            if(await page.waitForSelector('textarea[placeholder*="请输入标题"]',{timeout:20000}).catch(()=>null)) {emit({status:'ready'});process.exitCode=0;break;}
            throw new Error('扫码后编辑器仍不可用，可能需要手机号验证');
          }
          await new Promise(r=>setTimeout(r,3000));
        }
        if(process.exitCode===0) break;
        if(attempt===qrLimit) throw new Error('二维码等待结束，草稿保留在本地，稍后可重新运行恢复');
      }
    }
  }
} catch(e) {emit({status:'error',message:e.message});process.exitCode=1;}
finally {await browser.close();}
