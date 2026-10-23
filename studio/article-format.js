/* Shared semantic format: plain text stays authoritative; all HTML is escaped. */
(function(g){
 const types=['paragraph','heading','quote','bullet','ordered'];
 const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function parts(b){
  if(!types.includes(b.type)||typeof b.text!=='string')throw Error('不支持的正文块');
  const ranges=[];if(b.emphasis!==undefined&&(!Array.isArray(b.emphasis)||b.emphasis.length>3))throw Error('强调字段无效');
  for(const text of b.emphasis||[]){if(typeof text!=='string'||!text||Array.from(text).length>80)throw Error('强调文字无效');const start=b.text.indexOf(text);if(start<0||ranges.some(r=>start<r.end&&start+text.length>r.start))throw Error('强调文字不在正文或存在重叠');ranges.push({start,end:start+text.length});}
  ranges.sort((a,b)=>a.start-b.start);const result=[];let from=0;for(const r of ranges){if(r.start>from)result.push({text:b.text.slice(from,r.start),bold:false});result.push({text:b.text.slice(r.start,r.end),bold:true});from=r.end;}if(from<b.text.length)result.push({text:b.text.slice(from),bold:false});return result;
 }
 function inline(b){return parts(b).map(x=>(x.bold?'<strong>':'')+escape(x.text).replace(/\n/g,'<br>')+(x.bold?'</strong>':'')).join('');}
 function blocksHtml(blocks){let html='',list=null;for(const b of blocks){const tag=b.type==='bullet'?'ul':b.type==='ordered'?'ol':null;if(list&&list!==tag){html+='</'+list+'>';list=null;}if(tag&&!list){html+='<'+tag+'>';list=tag;}const t=tag?'li':b.type==='heading'?'h2':b.type==='quote'?'blockquote':'p';html+='<'+t+'>'+inline(b)+'</'+t+'>';}if(list)html+='</'+list+'>';return html;}
 function appendBlock(root,b){const tag=b.type==='bullet'?'ul':b.type==='ordered'?'ol':null;let parent=root;if(tag){parent=root.lastElementChild;if(!parent||parent.tagName.toLowerCase()!==tag){parent=document.createElement(tag);root.append(parent);}}const node=document.createElement(tag?'li':b.type==='heading'?'h2':b.type==='quote'?'blockquote':'p');for(const part of parts(b)){if(part.bold){const strong=document.createElement('strong');strong.textContent=part.text;node.append(strong);}else node.append(document.createTextNode(part.text));}parent.append(node);return node;}
 g.ArticleFormat={parts,blocksHtml,appendBlock,types};
})(globalThis);
