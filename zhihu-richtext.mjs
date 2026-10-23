import './studio/article-format.js';
export const format=globalThis.ArticleFormat;
export const hasRich=article=>(article.blocks||[]).some(b=>['quote','bullet','ordered'].includes(b.type)||b.emphasis?.length);
export async function pasteBlocks(page,blocks){
 const html=format.blocksHtml(blocks),text=blocks.map(b=>b.text).join('\n');
 await page.evaluate(({html,text})=>{const root=document.querySelector('[contenteditable=true]');if(!root)throw Error('找不到编辑器');root.focus();const data=new DataTransfer();data.setData('text/html',html);data.setData('text/plain',text);root.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:data}));},{html,text});
}
export async function verifyRich(page,article){
 if(!hasRich(article))return null;
 const errors=await page.evaluate(blocks=>{
  const root=document.querySelector('[contenteditable=true]');if(!root)return ['编辑器缺失'];const norm=s=>s.replace(/[\s\u200b-\u200d\ufeff]/gu,'');const errors=[];
  for(const [i,b] of blocks.entries()){
   const selector={heading:'h1,h2,h3',quote:'blockquote',bullet:'ul > li',ordered:'ol > li'}[b.type];
   if(selector&&![...root.querySelectorAll(selector)].some(n=>norm(n.textContent)===norm(b.text)))errors.push('第'+(i+1)+'块样式未保留：'+b.type);
   const scopes=[...root.querySelectorAll('[data-block=true],p,h1,h2,h3,blockquote,li')].filter(n=>norm(n.textContent)===norm(b.text));
   for(const text of b.emphasis||[])if(!scopes.some(scope=>[...scope.querySelectorAll('strong,b,span')].some(n=>norm(n.textContent).includes(norm(text))&&Number.parseInt(getComputedStyle(n).fontWeight)>=600)))errors.push('第'+(i+1)+'块强调未保留');
  }return errors;
 },article.blocks);
 if(errors.length)throw Error('富文本重载核验失败：'+errors.join('；'));return {version:2,verified:true};
}
