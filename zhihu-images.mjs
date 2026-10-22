export const imageIdentity=src=>{try{const u=new URL(src);if(!(/(^|\.)zhimg\.com$/.test(u.hostname)||u.hostname==='pic-private.zhihu.com'))return null;return u.pathname.match(/v2-[a-f0-9]+/)?.[0]||u.origin+u.pathname}catch{return null}};
export async function imageState(page){return page.evaluate(()=>{const root=document.querySelector('[contenteditable="true"]');if(!root)return null;const plain=node=>{const clone=node.cloneNode(true);clone.querySelectorAll('figure').forEach(n=>n.remove());return clone.textContent};return {text:plain(root),images:[...root.querySelectorAll('img')].map(img=>({src:img.currentSrc||img.src,width:img.naturalWidth,complete:img.complete,before:(()=>{const r=document.createRange();r.setStart(root,0);r.setEndBefore(img.closest('figure')||img);return plain(r.cloneContents())})()}))}})}
export function verifyImages(state,article,expectedSources=null){
 const clean=s=>s.replace(/[\s\u200b-\u200d\ufeff]/gu,'');
 if(!state||clean(state.text)!==clean(article.body))throw Error('正文与本地审阅稿不一致');
 const expected=article.illustrations||[];if(state.images.length!==expected.length)throw Error('图片数量不一致');
 for(let i=0;i<expected.length;i++){
  const actual=state.images[i];if(!actual.complete||!actual.width||!imageIdentity(actual.src))throw Error('图片尚未完成知乎转存');
  const prefix=article.blocks.slice(0,expected[i].before_block||0).map(b=>b.text).join('');if(clean(actual.before)!==clean(prefix))throw Error('第'+(i+1)+'幅图片位置不一致');
  if(expectedSources&&imageIdentity(actual.src)!==expectedSources[i])throw Error('知乎图片版本与已验证草稿不一致');
 }
 return state.images.map(img=>imageIdentity(img.src));
}
