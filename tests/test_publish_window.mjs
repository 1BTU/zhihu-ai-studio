import assert from 'node:assert/strict';
import {assertPublishWindow} from '../publish-window.mjs';
const env={ZHIHU_PUBLISH_AFTER:'2026-10-23T08:30:00+08:00',ZHIHU_PUBLISH_BEFORE:'2026-10-23T11:00:00+08:00'};
assertPublishWindow(env,Date.parse(env.ZHIHU_PUBLISH_AFTER));
assert.throws(()=>assertPublishWindow(env,Date.parse(env.ZHIHU_PUBLISH_BEFORE)));
assert.throws(()=>assertPublishWindow(env,Date.parse(env.ZHIHU_PUBLISH_AFTER)-1));
assert.throws(()=>assertPublishWindow({ZHIHU_PUBLISH_AFTER:'bad'}));
assertPublishWindow({});console.log('Publication time guard passed');
