import assert from 'node:assert/strict';import '../studio/article-format.js';
const f=globalThis.ArticleFormat;
assert.equal(f.blocksHtml([{type:'paragraph',text:'<script>事实</script>',emphasis:['事实']}]),'<p>&lt;script&gt;<strong>事实</strong>&lt;/script&gt;</p>');
assert.equal(f.blocksHtml([{type:'bullet',text:'甲'},{type:'bullet',text:'乙'},{type:'ordered',text:'丙'},{type:'quote',text:'丁'}]),'<ul><li>甲</li><li>乙</li></ul><ol><li>丙</li></ol><blockquote>丁</blockquote>');
assert.throws(()=>f.blocksHtml([{type:'paragraph',text:'原文',emphasis:['没有']} ]));
assert.throws(()=>f.blocksHtml([{type:'paragraph',text:'原文内容',emphasis:['原文','文内容']} ]));
console.log('article-format: escaped HTML, list grouping, invalid emphasis passed');
