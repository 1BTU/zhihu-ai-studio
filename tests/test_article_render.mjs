import assert from 'node:assert/strict';import puppeteer from 'puppeteer';import fs from 'node:fs/promises';import {verifyRich} from '../zhihu-richtext.mjs';
const b=await puppeteer.launch({headless:true,args:['--no-sandbox']});
try{const p=await b.newPage();await p.setContent('<meta charset="utf-8"><main id="root" contenteditable="true"></main>');await p.addScriptTag({content:await fs.readFile(new URL('../studio/article-format.js',import.meta.url),'utf8')});
const article={blocks:[{type:'paragraph',text:'<img src=x onerror=alert(1)>重点',emphasis:['重点']},{type:'quote',text:'引用内容'},{type:'bullet',text:'第一项'},{type:'bullet',text:'第二项'},{type:'ordered',text:'步骤甲'},{type:'ordered',text:'步骤乙'}]};
await p.evaluate(blocks=>blocks.forEach(block=>ArticleFormat.appendBlock(document.querySelector('#root'),block)),article.blocks);
assert.equal(await p.$$eval('img',xs=>xs.length),0);assert.equal(await p.$$eval('ul',xs=>xs.length),1);assert.equal(await p.$$eval('ol',xs=>xs.length),1);
assert.equal((await verifyRich(p,article)).verified,true);
await p.$eval('strong',n=>n.replaceWith(n.textContent));await assert.rejects(()=>verifyRich(p,article),/强调未保留/);
console.log('article-render: safe DOM, grouped lists, persisted style validation and missing-bold rejection passed');
}finally{await b.close()}
