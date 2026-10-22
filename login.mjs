import puppeteer from 'puppeteer';
import { mkdir, chmod, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const privateDir = path.join(root, 'private');
const artifacts = path.join(root, 'artifacts');
const profileFile = path.join(privateDir, 'active-profile.json');
const savedProfile = await readFile(profileFile, 'utf8').then(JSON.parse).catch(error => {
  if (error.code === 'ENOENT') return null;
  throw error;
});
const profileName = process.argv.includes('--new-account') ? `browser-profile-${Date.now()}` : (savedProfile?.name || 'browser-profile');
if (!/^browser-profile(?:-\d+)?$/.test(profileName)) throw new Error('无效的浏览器会话目录');
await mkdir(privateDir, { recursive: true, mode: 0o700 });
await mkdir(artifacts, { recursive: true, mode: 0o700 });
await chmod(privateDir, 0o700);
await chmod(artifacts, 0o700);
const browser = await puppeteer.launch({
  headless: true,
  userDataDir: path.join(privateDir, profileName),
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
  defaultViewport: { width: 1280, height: 900 },
});
const page = await browser.newPage();
page.setDefaultTimeout(20000);
async function snapshot(name) {
  const screenshot = path.join(artifacts, `${name}.png`);
  await page.screenshot({ path: screenshot, fullPage: false });
  const info = await page.evaluate(() => ({
    url: location.origin + location.pathname,
    title: document.title,
    buttons: [...document.querySelectorAll('button')].map(b => b.innerText.trim()).filter(Boolean),
    fields: [...document.querySelectorAll('input,textarea,[contenteditable="true"]')].map(e => ({
      tag: e.tagName, type: e.type, placeholder: e.getAttribute('placeholder'),
      editable: e.getAttribute('contenteditable'),
    })),
  }));
  console.log(JSON.stringify({ screenshot, ...info }));
  await writeFile(path.join(artifacts, `${name}.json`), JSON.stringify(info, null, 2), { mode: 0o600 });
}
try {
  const response = await page.goto('https://www.zhihu.com/signin', { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log(JSON.stringify({ stage: 'signin', status: response?.status() }));
  await new Promise(resolve => setTimeout(resolve, 4000));
  // Only select an explicit QR login control. Never guess a positional button.
  const controls = await page.$$('button, [role="tab"]');
  for (const control of controls) {
    if (/^(扫码登录|二维码登录)$/.test(await control.evaluate(e => e.innerText.trim()))) {
      await control.click();
      break;
    }
  }
  await snapshot('login');
  const qr = await page.$('canvas.Qrcode-qrcode');
  if (qr) {
    await qr.screenshot({ path: path.join(artifacts, 'zhihu-login-qr.png') });
    console.log('QR_READY: artifacts/zhihu-login-qr.png');
  }
  if (response?.status() >= 400) {
    console.log('BLOCKED: 知乎拒绝当前服务器访问，未尝试登录或写入。');
    process.exitCode = 2;
  } else {
    console.log('WAITING_FOR_LOGIN: 请查看 login.png；等待扫码，最多十分钟。');
    const deadline = Date.now() + 10 * 60 * 1000;
    let loggedIn = false;
    while (Date.now() < deadline) {
      const cookies = await browser.cookies();
      if (cookies.some(c => c.name === 'z_c0' && c.value && /(^|\.)zhihu\.com$/.test(c.domain.replace(/^\./, '')))) {
        loggedIn = true;
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 5000));
    }
    if (!loggedIn) throw new Error('扫码登录未完成；可重新运行，不会输出或导出 Cookie。');
    await writeFile(profileFile, JSON.stringify({name: profileName}), { mode: 0o600 });
    console.log('LOGIN_OK: 已检测到登录状态，正在验证编辑器。');
    const editorResponse = await page.goto('https://zhuanlan.zhihu.com/write', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await new Promise(resolve => setTimeout(resolve, 4000));
    await snapshot('editor');
    const editable = await page.$('[contenteditable="true"]');
    if (!editable || editorResponse?.status() >= 400) throw new Error('登录后未能访问文章编辑器，请检查 editor.png。');
    console.log('EDITOR_OK: 编辑器可访问；尚未填稿或发布。');
  }
} catch (error) {
  await snapshot('error').catch(() => {});
  console.error(error.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
