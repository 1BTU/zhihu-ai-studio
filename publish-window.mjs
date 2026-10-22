export function assertPublishWindow(env=process.env,now=Date.now()) {
  const after=env.ZHIHU_PUBLISH_AFTER,before=env.ZHIHU_PUBLISH_BEFORE;
  if(!after&&!before)return;
  const start=Date.parse(after),end=Date.parse(before);
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)throw Error('发布时间窗口无效');
  if(now<start||now>=end)throw Error('当前不在本次发布时间窗口内，保留草稿，不补发');
}
