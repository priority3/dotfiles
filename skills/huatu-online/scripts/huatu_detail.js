/**
 * 逐题明细抓取：打开每份已交卷练习的解析页，展开全部解析，解析每题
 *  - 正确答案 / 我的选择 / 对错
 *  - 答题用时（秒）、全站正确率、易错项
 *  - 考点三级标签（模块 → 题型 → 细分）
 *  - 题目来源（真题年份地区）
 *
 * 用法：CDP_PORT=9231 node huatu_detail.js [maxPapers]   → 输出 JSON
 */
const http = require('http');
const fs = require('fs');

const PORT = Number(process.env.CDP_PORT || 9231);
const MAX = Number(process.argv[2] || 8);
const COOKIE_FILE = '/tmp/huatu_cookies.json';

const jget = (p) => new Promise((res, rej) => {
  http.get({ host: '127.0.0.1', port: PORT, path: p }, (r) => {
    let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => res(JSON.parse(d)));
  }).on('error', rej);
});

const PARSE = String.raw`(() => {
  const t = (document.body.innerText || '').replace(/\r/g, '');
  // 以「题号 、 （题型）」为分题锚点，纯文本切分最稳
  const parts = t.split(/\n(?=\d+\s*、\s*（)/);
  const questions = [];
  for (const part of parts) {
    const head = part.match(/^(\d+)\s*、\s*(?:（([^）]+)）)?([\s\S]*?)\n\s*A[.、]/);
    if (!head) continue;
    if (!/正确答案|展开解析|回答正确|回答错误/.test(part)) continue;
    const ans = part.match(/正确答案：([A-D])[，,]\s*我的选择：([A-D]?)/);
    const sec = part.match(/答题时间：(\d+)秒/);
    const site = part.match(/全站正确率：(\d+)%/);
    const easy = part.match(/易错项：([A-D])/);
    const topicBlock = (part.split(/考点\s*\n/)[1] || '').split(/\n来源/)[0];
    const topics = topicBlock.split(/\n/).map(x => x.trim()).filter(Boolean).slice(0, 3);
    const source = (part.split(/\n来源\s*\n/)[1] || '').split(/\n/)[0].trim();
    questions.push({
      n: +head[1],
      type: (head[2] || '').trim(),
      topicModule: topics[0] || '',
      topicKind: topics[1] || '',
      topicDetail: (topics[2] || '').split(/[,，]/)[0] || '',
      answer: ans ? ans[1] : '',
      mine: ans ? (ans[2] || '') : '',
      ok: /回答正确/.test(part) ? true : (/回答错误/.test(part) ? false : null),
      seconds: sec ? +sec[1] : null,
      siteAccuracy: site ? +site[1] : null,
      easyWrong: easy ? easy[1] : '',
      source,
      stem: (head[3] || '').replace(/\n/g, ' ').slice(0, 220),
      options: (() => {
        const m0 = part.match(/\n\s*A[.、][\s\S]*/);
        const head4 = (m0 ? m0[0] : '').split(/\n\s*(?:收起解析|展开解析|展开全部解析)/)[0];
        const found = [...head4.matchAll(/(?:^|\n)\s*([ABCD])[.、]\s*([^\n]{1,60})/g)]
          .map(m => ({ k: m[1], t: m[2].trim() }));
        return found.slice(0, 4);
      })(),
    });
  }
  return JSON.stringify({ count: questions.length, questions });
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

  // 1) 答题记录页：拿到已交卷的解析链接
  await send('Page.navigate', { url: 'https://v.huatu.com/tiku/myxlist' });
  await new Promise((r) => setTimeout(r, 4500));
  const list = await send('Runtime.evaluate', {
    expression: `JSON.stringify([...document.querySelectorAll('a')]
      .filter(a => /查看解析/.test(a.textContent))
      .map(a => (a.getAttribute('href') || ''))
      .filter(h => /analysis\\/\\d+/.test(h))
      .map(h => ({ href: h, id: (h.match(/analysis\\/(\\d+)/) || [])[1] })))`,
    returnByValue: true,
  });
  const papers = JSON.parse(list.result.value).slice(0, MAX);
  const out = [];
  const seen = new Set();

  for (const p of papers) {
    if (!p.id || seen.has(p.id)) continue;
    seen.add(p.id);
    await send('Page.navigate', { url: 'https://v.huatu.com/tiku/analysis/' + p.id });
    await new Promise((r) => setTimeout(r, 5200));

    // 展开解析：先用宽松匹配点「展开全部解析」，再逐题兜底点「展开解析」
    for (let round = 0; round < 6; round += 1) {
      const r = await send('Runtime.evaluate', {
        expression: String.raw`(() => {
          const pick = (re) => [...document.querySelectorAll('a,button,span,div')]
            .find(e => e.children.length === 0 && re.test(e.textContent || '')
                       && (e.textContent || '').trim().length <= 8);
          const all = pick(/展开全部解析/);
          if (all) all.click();
          let n = 0;
          document.querySelectorAll('a,button,span,div').forEach(e => {
            if (e.children.length === 0 && /^展开解析$/.test((e.textContent || '').trim())) { e.click(); n += 1; }
          });
          window.scrollTo(0, document.body.scrollHeight);
          return JSON.stringify({ expandAll: !!all, perQ: n,
            answers: (document.body.innerText.match(/正确答案：/g) || []).length,
            qs: (document.body.innerText.match(/\n\d+\s*、\s*（/g) || []).length });
        })()`, returnByValue: true,
      });
      const st = JSON.parse(r.result.value);
      if (process.env.HUATU_DEBUG) console.error('  round', round, JSON.stringify(st));
      await new Promise((res) => setTimeout(res, 1500));
      // 翻页/加载更多（解析页分段渲染）
      await send('Runtime.evaluate', {
        expression: String.raw`(() => {
          const hit = [...document.querySelectorAll('a,button,li,div,span')]
            .find(e => e.children.length === 0 && /^(下一页|查看下一题|加载更多|查看更多|下一组)$/.test((e.textContent||'').trim()));
          if (hit) { hit.click(); return true; } return false;
        })()`, returnByValue: true,
      });
      if (st.answers >= st.qs && st.qs > 0) break;
    }
    await send('Runtime.evaluate', { expression: 'window.scrollTo(0,0)' });

    const header = await send('Runtime.evaluate', {
      expression: `(() => {
        const t = (document.body.innerText || '').replace(/\\n{2,}/g, '\\n').split('\\n');
        const title = t.find(x => /--\\d{6,}/.test(x)) || '';
        const line = t.find(x => /^[^\\n]*\\d+\\/\\d+.*\\d+\\/\\d+/.test(x) && /(关系|理论|言语|判断|资料|常识|分析)/.test(x)) || '';
        const mods = [...line.matchAll(/([\\u4e00-\\u9fa5]+?)\\s*(\\d+)\\/(\\d+)/g)]
          .map(m => ({ name: m[1].trim(), right: +m[2], total: +m[3] }));
        return JSON.stringify({ title, modules: mods });
      })()`, returnByValue: true,
    });
    const h = JSON.parse(header.result.value);

    const detail = await send('Runtime.evaluate', { expression: PARSE, returnByValue: true });
    const d = JSON.parse(detail.result.value);

    out.push({ paperId: p.id, title: h.title, modules: h.modules,
               questionCount: d.count, questions: d.questions });
  }

  console.log(JSON.stringify({ fetchedAt: new Date().toISOString(), papers: out }, null, 2));
  ws.close();
})().catch((e) => { console.error('逐题抓取失败:', e.message); process.exit(1); });
