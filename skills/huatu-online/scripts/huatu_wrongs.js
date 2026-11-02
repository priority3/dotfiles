/**
 * 抓错题本：展开三层结构 → 按子题型取题
 *
 * 结构：错题重练页 → 模块（资料分析）→ 子题型（比重 2 道）→ /tiku/errorlist/<id>
 * 用法：CDP_PORT=9231 node huatu_wrongs.js [最多几个子题型，默认 12]
 */
const http = require('http');
const fs = require('fs');

const PORT = Number(process.env.CDP_PORT || 9231);
const MAX_TOPICS = Number(process.argv[2] || 12);
const COOKIE_FILE = '/tmp/huatu_cookies.json';

const jget = (p) => new Promise((res, rej) => {
  http.get({ host: '127.0.0.1', port: PORT, path: p }, (r) => {
    let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => res(JSON.parse(d)));
  }).on('error', rej);
});

// 从页面纯文本里切题（与 huatu_detail.js 同一套锚点）
const PARSE = String.raw`(() => {
  const t = (document.body.innerText || '').replace(/\r/g, '');
  const parts = t.split(/\n(?=\d+\s*、\s*（)/);
  const qs = [];
  for (const part of parts) {
    const head = part.match(/^(\d+)\s*、\s*(?:（([^）]+)）)?([\s\S]*?)\n\s*A[.、]/);
    if (!head) continue;
    const ans = part.match(/正确答案：([A-D])/);
    const mine = part.match(/我的选择：([A-D]?)/);
    const site = part.match(/全站正确率：(\d+)%/);
    const sec = part.match(/答题时间：(\d+)秒/);
    const topicBlock = (part.split(/考点\s*\n/)[1] || '').split(/\n来源/)[0];
    const topics = topicBlock.split(/\n/).map(x => x.trim()).filter(Boolean).slice(0, 3);
    const m0 = part.match(/\n\s*A[.、][\s\S]*/);
    const optText = (m0 ? m0[0] : '').split(/\n\s*(?:收起解析|展开解析|展开全部解析)/)[0];
    const options = [...optText.matchAll(/(?:^|\n)\s*([ABCD])[.、]\s*([^\n]{1,60})/g)]
      .map(m => ({ k: m[1], t: m[2].trim() })).slice(0, 4);
    qs.push({
      n: +head[1],
      stem: (head[3] || '').replace(/\n/g, ' ').slice(0, 220),
      options,
      answer: ans ? ans[1] : '',
      mine: mine ? (mine[1] || '') : '',
      ok: /回答正确/.test(part) ? true : (/回答错误/.test(part) ? false : null),
      seconds: sec ? +sec[1] : null,
      siteAccuracy: site ? +site[1] : null,
      topicModule: topics[0] || '',
      topicKind: topics[1] || '',
      topicDetail: (topics[2] || '').split(/[,，]/)[0] || '',
    });
  }
  return JSON.stringify(qs);
})()`;

(async () => {
  const cookies = JSON.parse(fs.readFileSync(COOKIE_FILE, 'utf8'));
  const page = (await jget('/json/list')).find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0; const pend = new Map();
  const send = (m, p = {}) => new Promise((res, rej) => {
    const i = ++id; pend.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method: m, params: p }));
  });
  await new Promise((r) => ws.addEventListener('open', r));
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) {
      const { res, rej } = pend.get(m.id); pend.delete(m.id);
      m.error ? rej(new Error(m.error.message)) : res(m.result);
    }
  });
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');

  for (const c of cookies) {
    const v = String(c.value);
    if (/[\x00-\x08\x0e-\x1f\x7f]/.test(v)) continue;
    try {
      await send('Network.setCookie', {
        name: c.name, value: v, domain: c.host.replace(/^\./, ''), path: '/',
        secure: c.host.includes('huatu'), httpOnly: false, sameSite: 'Lax',
      });
    } catch (e) { /* ignore */ }
  }

  // 1) 错题重练页：展开三层，收集子题型
  await send('Page.navigate', { url: 'https://v.huatu.com/tiku/myerror' });
  await new Promise((r) => setTimeout(r, 5200));
  for (let i = 0; i < 3; i += 1) {
    await send('Runtime.evaluate', {
      expression: `document.querySelectorAll('i.point-icon').forEach(e => e.click())`,
      returnByValue: true,
    });
    await new Promise((r) => setTimeout(r, 1500));
  }

  const listRes = await send('Runtime.evaluate', {
    expression: String.raw`(() => {
      const rows = [...document.querySelectorAll('section')].map(sec => {
        const name = (sec.querySelector('.point-name') || {}).textContent || '';
        const link = sec.querySelector('a[href*="errorlist"]');
        const href = link ? (link.getAttribute('href') || '') : '';
        const cnt = +(name.match(/共(\d+)道/) || [0, 0])[1];
        return { name: name.trim(), count: cnt, href };
      }).filter(x => x.count > 0 && /errorlist/.test(x.href));
      // 去掉总览行（名字恰好等于模块名、且包含子项），保留最细的题型
      const seen = new Set();
      return JSON.stringify(rows.filter(r => { if (seen.has(r.href)) return false; seen.add(r.href); return true; }));
    })()`, returnByValue: true,
  });
  // 优先取「模块级」行（名字去掉（共N道错题）后正好等于模块名），保证每天基准一致
  const MODULES = ['资料分析', '常识判断', '言语理解与表达', '数量关系', '判断推理', '政治理论'];
  const all = JSON.parse(listRes.result.value);
  const isModule = (t) => MODULES.includes(t.name.replace(/（共\d+道错题）\s*$/, '').trim());
  const topics = [
    ...all.filter(isModule).sort((a, b) => b.count - a.count),
    ...all.filter((t) => !isModule(t)).sort((a, b) => b.count - a.count),
  ].slice(0, MAX_TOPICS);

  // 2) 逐个打开子题型，抓题目
  const out = [];
  for (const tp of topics) {
    await send('Page.navigate', { url: 'https://v.huatu.com' + tp.href });
    await new Promise((r) => setTimeout(r, 4200));
    await send('Runtime.evaluate', {
      expression: String.raw`(() => {
        const all = [...document.querySelectorAll('a,button,span,div')]
          .find(e => e.children.length === 0 && /展开全部解析/.test(e.textContent || ''));
        if (all) all.click();
        document.querySelectorAll('a,button,span,div').forEach(e => {
          if (e.children.length === 0 && /^展开解析$/.test((e.textContent || '').trim())) e.click();
        });
        return true;
      })()`, returnByValue: true,
    });
    await new Promise((r) => setTimeout(r, 2200));

    const qsRes = await send('Runtime.evaluate', { expression: PARSE, returnByValue: true });
    let qs = JSON.parse(qsRes.result.value);
    if (!qs.length) {   // 有些题没解析按钮，退回取题干
      const raw = await send('Runtime.evaluate', {
        expression: `(document.body.innerText||'').slice(0, 600)`, returnByValue: true,
      });
      out.push({ ...tp, questions: [], note: raw.result.value.slice(0, 80) });
      continue;
    }
    out.push({ ...tp, questions: qs });
  }

  console.log(JSON.stringify({ fetchedAt: new Date().toISOString(), topics: out }, null, 2));
  ws.close();
})().catch((e) => { console.error('错题抓取失败:', e.message); process.exit(1); });
