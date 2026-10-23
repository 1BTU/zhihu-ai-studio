import {hasRich,pasteBlocks,verifyRich} from './zhihu-richtext.mjs';
import puppeteer from 'puppeteer';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const articleFile = process.argv[2];
if (!articleFile) throw new Error('用法：node draft.mjs article.json');
const article = JSON.parse(await readFile(articleFile, 'utf8'));
if (typeof article.title !== 'string' || !article.title.trim() || [...article.title].length > 100 ||
    typeof article.body !== 'string' || !article.body.trim()) throw new Error('文章须包含 title（1–100字）和 body。');
if(article.illustrations?.length){await import('./draft-images.mjs');process.exit(process.exitCode||0)}
const artifacts = path.join(root, 'artifacts');
await mkdir(artifacts, { recursive: true, mode: 0o700 });
const savedProfile = await readFile(path.join(root, 'private/active-profile.json'), 'utf8').then(JSON.parse).catch(error => {
  if (error.code === 'ENOENT') return null;
  throw error;
});
const profileName = savedProfile?.name || 'browser-profile';
if (!/^browser-profile(?:-\d+)?$/.test(profileName)) throw new Error('无效的浏览器会话目录');
const browser = await puppeteer.launch({headless: true, userDataDir: path.join(root, 'private', profileName),
  args: ['--no-sandbox', '--disable-dev-shm-usage'], defaultViewport: {width: 1280, height: 900}});
const page = await browser.newPage();
page.setDefaultTimeout(30000);
const titleSelector = 'textarea[placeholder*="请输入标题"]';
const bodySelector = '[contenteditable="true"]';
function normalized(text) { return text.replace(/\s+/gu, ''); }
try {
  const resumeUrl = process.env.ZHIHU_DRAFT_URL;
  if (resumeUrl && !/^https:\/\/zhuanlan\.zhihu\.com\/p\/\d+\/edit$/.test(resumeUrl)) throw new Error('草稿恢复地址无效。');
  const response = await page.goto(resumeUrl || 'https://zhuanlan.zhihu.com/write', {waitUntil: 'domcontentloaded', timeout: 60000});
  if (response?.status() >= 400) throw new Error(`知乎返回 ${response.status()}`);
  await page.waitForSelector(titleSelector, {visible: true});
  await page.waitForSelector(bodySelector, {visible: true});
  const before = await page.evaluate((t, b) => ({title: document.querySelector(t).value, body: document.querySelector(b).innerText}), titleSelector, bodySelector);
  if (before.body.trim() || (before.title.trim() && !(resumeUrl && before.title === article.title))) throw new Error('编辑器已有内容，停止以避免覆盖现有草稿。');
  await page.locator(titleSelector).fill(article.title);
  await page.click(bodySelector);
  const lines = article.blocks || article.body.replace(/\r\n/g, '\n').split('\n').map(text => ({type:'paragraph', text}));
  if(hasRich(article))await pasteBlocks(page,lines);
  else {
  for (let i = 0; i < lines.length; i++) {
    if (await page.evaluate(() => document.body.innerText.includes('绑定手机号后'))) throw new Error('知乎要求绑定或验证手机号，请先在知乎 App 中完成账号验证。');
    if (i) await page.keyboard.press('Enter');
    const block = lines[i];
    if (block.type === 'heading') {
      await page.keyboard.type('##');
      await page.keyboard.press('Space');
    }
    if (block.text) await page.keyboard.sendCharacter(block.text);
  }
  }
  await page.click(titleSelector);
  // Wait for Zhihu to allocate a draft URL, then reload to verify server persistence.
  await page.waitForFunction(() => /\/p\/\d+\/edit/.test(location.pathname) || document.body.innerText.includes('绑定手机号后'), {timeout: 60000});
  if (await page.evaluate(() => document.body.innerText.includes('绑定手机号后'))) throw new Error('知乎要求绑定或验证手机号，请先在知乎 App 中完成账号验证。');
  await new Promise(r => setTimeout(r, 4000));
  const draftUrl = page.url();
  await page.reload({waitUntil: 'domcontentloaded', timeout: 60000});
  await page.waitForSelector(titleSelector, {visible: true});
  await page.waitForFunction((s, title) => document.querySelector(s)?.value === title, {timeout: 30000}, titleSelector, article.title);
  const saved = await page.evaluate((t, b) => ({title: document.querySelector(t).value, body: document.querySelector(b)?.innerText || ''}), titleSelector, bodySelector);
  if (normalized(saved.body) !== normalized(article.body)) throw new Error('重载后正文校验失败，不能确认草稿完整保存。');
  const richText=await verifyRich(page,article);
  await page.screenshot({path: path.join(artifacts, 'draft-saved.png'), fullPage: true});
  const result = {saved: true, published: false, title: saved.title, url: draftUrl, verifiedByReload: true,richText};
  await writeFile(process.env.ZHIHU_RESULT_PATH || path.join(artifacts, 'draft-result.json'), JSON.stringify(result, null, 2), {mode: 0o600});
  console.log(JSON.stringify(result));
} catch (error) {
  await page.screenshot({path: path.join(artifacts, 'draft-error.png'), fullPage: true}).catch(() => {});
  console.error(JSON.stringify({error: error.message, url: page.url()}));
  process.exitCode = 1;
} finally { await browser.close(); }
