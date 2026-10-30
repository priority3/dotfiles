/**
 * 用已解密的 cookie 打开华图在线，抓取刷题数据，输出 JSON 到 stdout。
 *
 * 用法：CDP_PORT=9231 node huatu_fetch.js [progress|report|records|errors|all]
 * 前置：先跑 huatu_cookies.py 生成 /tmp/huatu_cookies.json
 */
const http = require('http');
const fs = require('fs');

const PORT = Number(process.env.CDP_PORT || 9231);
const MODE = process.argv[2] || 'all';
const COOKIE_FILE = '/tmp/huatu_cookies.json';

const PAGES = {
  progress: 'https://v.huatu.com/tiku/',
  report: 'https://v.huatu.com/tiku/myreport',
  records: 'https://v.huatu.com/tiku/myxlist',
  errors: 'https://v.huatu.com/tiku/myerror',
};

const jget = (p) => new Promise((res, rej) => {
  http.get({ host: '127.0.0.1', port: PORT, path: p }, (r) => {
    let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => res(JSON.parse(d)));
  }).on('error', rej);
});

(async () => {
  const cookies = JSON.parse(fs.readFileSync(COOKIE_FILE, 'utf8'));
  const targets = await jget('/json/list');
  const page = targets.find((t) => t.type === 'page');
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

  await send('Page.enable');
  await send('Runtime.enable');

  // 注入登录 cookie（跳过二进制值）
  let ok = 0;
  for (const c of cookies) {
    const v = String(c.value);
    if (/[\x00-\x08\x0e-\x1f\x7f]/.test(v)) continue;
    try {
      await send('Network.setCookie', {
        name: c.name, value: v,
        domain: c.host.replace(/^\./, ''), path: '/',
        secure: c.host.includes('huatu'), httpOnly: false, sameSite: 'Lax',
      });
      ok += 1;
    } catch (e) { /* 单条失败不影响整体 */ }
  }

  await send('Page.navigate', { url: PAGES.progress });
  await new Promise((r) => setTimeout(r, 4000));
  const login = await send('Runtime.evaluate', {
    expression: `JSON.stringify({name:(document.cookie.match(/UserName=([^;]*)/)||[])[1]||'', uid:(document.cookie.match(/UserID=([^;]*)/)||[])[1]||''})`,
    returnByValue: true,
  });

  const result = {
    fetchedAt: new Date().toISOString(),
    cookiesInjected: ok,
    account: JSON.parse(login.result.value),
    mode: MODE,
  };

  const grab = async (url, expr, wait = 4200) => {
    await send('Page.navigate', { url });
    await new Promise((r) => setTimeout(r, wait));
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
    return JSON.parse(r.result.value);
  };

  const want = (k) => MODE === 'all' || MODE === k;

  if (want('progress')) {
    result.progress = await grab(PAGES.progress, `(() => {
      const text = document.body.innerText || '';
      const rows = (text.match(/[\\u4e00-\\u9fa5A-Za-z（）()·]{2,16}\\s*已做\\s*\\d+\\s*\\/\\s*\\d+\\s*题/g) || [])
        .map(s => { const m = s.match(/^(.+?)\\s*已做\\s*(\\d+)\\s*\\/\\s*(\\d+)/); return { name: m[1].trim(), done: +m[2], total: +m[3] }; });
      const top = rows.slice(0, 12);
      const sumDone = rows.reduce((a, r) => a + r.done, 0);
      return JSON.stringify({ rows, top, sumDone, rowCount: rows.length });
    })()`);
  }

  if (want('report')) {
    result.report = await grab(PAGES.report, `(() => {
      const t = (document.body.innerText || '').replace(/\\u00a0/g, ' ');
      const pick = (label, next) => {
        const re = new RegExp('([^\\\\n]{1,20})\\\\n' + label);
        const m = t.match(re);
        return m ? m[1].trim() : '';
      };
      const num = (s) => (s.match(/[\\d.]+/) || [''])[0];
      const total = pick('做题数量', 1);
      const acc = pick('正确率', 1);
      const speed = pick('做题速度', 1);
      const rank = pick('全站排名', 1);
      const dur = pick('累计做题时长', 1);
      const days = pick('练习天数', 1);
      return JSON.stringify({
        totalQuestions: num(total), totalRaw: total,
        accuracy: num(acc), accuracyRaw: acc,
        secPerQuestion: num(speed), speedRaw: speed,
        rank: rank, duration: dur, practiceDays: num(days),
        hasWeekly: /周数据报表/.test(t),
      });
    })()`);
  }

  if (want('records')) {
    result.records = await grab(PAGES.records, `(() => {
      const t = (document.body.innerText || '').replace(/\\n{2,}/g, '\\n');
      const blocks = t.split(/\\n(?=(?:智能刷题|新人练习|专项练习|历年真题|错题重练|模考)[—-])/g).slice(0, 60);
      const items = [];
      for (const b of blocks) {
        const name = (b.match(/^(\\S+?)--?\\d{6,}/) || [])[1];
        if (!name) continue;
        const submitted = /交卷时间/.test(b);
        const time = (b.match(/(?:交卷时间|练习时间)：([^\\n]+)/) || [])[1] || '';
        const right = (b.match(/做对\\s*(\\d+)\\s*道\\s*\\/\\s*共\\s*(\\d+)\\s*道/) || []);
        items.push({
          title: (b.split('\\n')[0] || '').trim(),
          type: name,
          submitted,
          at: time,
          correct: right[1] ? +right[1] : null,
          total: right[2] ? +right[2] : null,
        });
      }
      return JSON.stringify({ count: items.length, items });
    })()`, 5000);
  }

  if (want('errors')) {
    result.errors = await grab(PAGES.errors, `(() => {
      const t = (document.body.innerText || '').replace(/\\n{2,}/g, '\\n');
      const list = [...t.matchAll(/([\\u4e00-\\u9fa5]{2,10})\\s*（共\\s*(\\d+)\\s*道错题）/g)]
        .map(m => ({ module: m[1], count: +m[2] }));
      return JSON.stringify({ total: list.reduce((a, x) => a + x.count, 0), list });
    })()`, 4500);
  }

  console.log(JSON.stringify(result, null, 2));
  ws.close();
})().catch((e) => {
  console.error('抓取失败:', e.message);
  process.exit(1);
});
