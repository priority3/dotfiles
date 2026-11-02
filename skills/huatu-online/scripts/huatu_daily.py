#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""华图每日刷题日报：抓取 → 存快照 → 与上一次对比 → 生成结合讲义的 Markdown 日报

用法：
  python3 huatu_daily.py            # 抓取并出日报
  python3 huatu_daily.py --no-fetch # 只用库里已有快照重算（调试）
  python3 huatu_daily.py --json     # 输出机器可读的指标
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
RUN_SH = HERE / 'run.sh'
DB = pathlib.Path(os.path.expanduser('~/.workbuddy/data/huatu_daily.db'))
NOTES = pathlib.Path(os.path.expanduser('~/da-code/shengkao-roadmap/notes.js'))

MAJOR = ['资料分析', '综合分析类', '常识判断', '言语理解与表达',
         '数量关系', '判断推理', '政治理论']
TARGET_ACC, TARGET_SEC = 75.0, 50.0


# ---------- 抓取 ----------
def fetch() -> dict:
    r = subprocess.run([str(RUN_SH), 'all'], capture_output=True, text=True, timeout=600)
    if r.returncode == 0:
        try:
            return json.loads(r.stdout)
        except Exception:
            pass
    # 一次抓全失败时，分模块分别取（更稳，单次内存占用小）
    out = {}
    for mode in ('progress', 'report', 'records', 'errors'):
        rr = subprocess.run([str(RUN_SH), mode], capture_output=True, text=True, timeout=300)
        if rr.returncode != 0:
            raise RuntimeError(f'抓取失败（{mode}）：{(rr.stderr or "")[-200:]}')
        out.update(json.loads(rr.stdout))
    return out


# ---------- 逐题明细 ----------
def fetch_detail(max_papers: int = 6):
    """抓每份练习的逐题明细（考点/对错/耗时）。失败返回 None，不影响主流程。"""
    try:
        r = subprocess.run([str(RUN_SH), 'detail', str(max_papers)],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except Exception:
        return None


def store_detail(date: str, d: dict) -> None:
    if not d:
        return
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS questions (
            date TEXT, paper_id TEXT, qno INTEGER, module TEXT, kind TEXT,
            detail TEXT, ok INTEGER, seconds INTEGER, site_acc INTEGER, source TEXT,
            stem TEXT, options TEXT)""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_q_date ON questions(date)')
        cols = [r[1] for r in c.execute('PRAGMA table_info(questions)').fetchall()]
        for col in ('stem', 'options'):
            if col not in cols:
                c.execute(f'ALTER TABLE questions ADD COLUMN {col} TEXT')
        c.execute('DELETE FROM questions WHERE date=?', (date,))
        for paper in d.get('papers', []):
            for q in paper.get('questions', []):
                c.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (
                    date, paper.get('paperId', ''), q.get('n'), q.get('topicModule', ''),
                    q.get('topicKind', ''), q.get('topicDetail', ''),
                    None if q.get('ok') is None else int(bool(q['ok'])),
                    q.get('seconds'), q.get('siteAccuracy'), (q.get('source') or '')[:120],
                    (q.get('stem') or '')[:200],
                    json.dumps(q.get('options') or [], ensure_ascii=False)))


def detail_stats(date: str, d: dict) -> dict:
    """覆盖率、错题题型 TOP、最慢的题"""
    if not d:
        return {}
    papers = d.get('papers') or []
    caught = sum(len([q for q in p.get('questions', []) if q.get('ok') is not None]) for p in papers)
    expected = sum(m.get('total', 0) for p in papers for m in (p.get('modules') or []))
    wrong = {}
    slow = []
    for p in papers:
        for q in p.get('questions', []):
            if q.get('ok') is None:
                continue
            if q['ok'] is False:
                key = q.get('topicKind') or q.get('topicModule') or '其他'
                wrong[key] = wrong.get(key, 0) + 1
            if q.get('seconds'):
                slow.append({'n': q.get('n'), 'kind': q.get('topicKind') or q.get('topicModule'),
                             'sec': q['seconds'], 'stem': (q.get('stem') or '')[:28]})
    slow.sort(key=lambda x: -x['sec'])
    return {
        'papers': len(papers), 'caught': caught, 'expected': expected,
        'wrong_top': sorted(wrong.items(), key=lambda x: -x[1])[:4],
        'slowest': slow[:3],
        'over120': sum(1 for x in slow if x['sec'] > 120),
    }


# ---------- 存储 ----------
def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS snapshots (
          date TEXT PRIMARY KEY,
          ts TEXT, total_q INTEGER, accuracy REAL, sec_q REAL,
          duration TEXT, practice_days INTEGER, errors_total INTEGER,
          modules TEXT, records TEXT, unsubmitted INTEGER, submitted INTEGER,
          errors_json TEXT
        );
        ''')


def save(date: str, d: dict) -> None:
    rep, prog, err, rec = d['report'], d['progress'], d['errors'], d['records']
    modules = {r['name']: r for r in prog['rows'] if r['name'] in MAJOR}
    items = rec.get('items') or []
    with sqlite3.connect(DB) as c:
        cols = [r[1] for r in c.execute('PRAGMA table_info(snapshots)').fetchall()]
        if 'errors_json' not in cols:      # 老库补列
            c.execute('ALTER TABLE snapshots ADD COLUMN errors_json TEXT')
        c.execute('INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (
            date,
            d.get('fetchedAt', ''),
            int(float(rep.get('totalQuestions') or 0)),
            float(rep.get('accuracy') or 0),
            float(rep.get('secPerQuestion') or 0),
            rep.get('duration') or '',
            int(float(rep.get('practiceDays') or 0)),
            int(err.get('total') or 0),
            json.dumps(modules, ensure_ascii=False),
            json.dumps(items, ensure_ascii=False),
            sum(1 for i in items if not i.get('submitted')),
            sum(1 for i in items if i.get('submitted')),
            json.dumps(err.get('list') or [], ensure_ascii=False),
        ))


def prev_snapshot(date: str):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        row = c.execute('SELECT * FROM snapshots WHERE date < ? ORDER BY date DESC LIMIT 1',
                        (date,)).fetchone()
        return dict(row) if row else None


# ---------- 讲义索引 ----------
def lecture_index() -> list:
    """从 notes.js 读取讲义目录：返回 [{course, page, title, duration}]"""
    if not NOTES.exists():
        return []
    s = NOTES.read_text(encoding='utf-8')
    m = re.search(r'const COURSE_NOTES = (\{.*\});', s, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    out = []
    for cat in data.get('categories', []):
        for ep in cat.get('episodes', []):
            out.append({'course': cat.get('title', ''), 'id': ep.get('id'),
                        'page': ep.get('page'), 'title': ep.get('title', ''),
                        'duration': ep.get('duration', '')})
    return out


def pick(lectures, keyword):
    for lec in lectures:
        if keyword in lec['title']:
            return lec
    return None


def cite(lec, why: str) -> str:
    if not lec:
        return ''
    name = lec['course'].split('（')[0].replace('2027 ', '')
    return f'→ 看《{name}》第 {lec["page"]} 讲「{lec["title"].split("·")[-1].strip()}」（{lec["duration"]}）：{why}'


# ---------- 分析 ----------
def parse_duration(t: str) -> int:
    """'55′05″' / '1小时2分' → 秒"""
    t = t or ''
    h = re.search(r'(\d+)\s*小时', t)
    m = re.search(r'(\d+)[′\']', t)
    s = re.search(r'(\d+)[″"]', t)
    return (int(h.group(1)) * 3600 if h else 0) + (int(m.group(1)) * 60 if m else 0) + (int(s.group(1)) if s else 0)


def build(date, cur, prev, lectures) -> dict:
    total_q = int(float(cur['report'].get('totalQuestions') or 0))
    acc = float(cur['report'].get('accuracy') or 0)
    sec_q = float(cur['report'].get('secPerQuestion') or 0)
    err_total = int(cur['errors'].get('total') or 0)
    items = cur['records'].get('items') or []
    unsub = sum(1 for i in items if not i.get('submitted'))
    sub = sum(1 for i in items if i.get('submitted'))

    today_q = today_acc = today_sec = err_delta = None
    if prev:
        total_q0 = prev['total_q'] or 0
        today_q = total_q - total_q0
        if today_q > 0:
            c_now = total_q * acc / 100
            c_prev = total_q0 * (prev['accuracy'] or 0) / 100
            today_acc = (c_now - c_prev) / today_q * 100
            d_cur, d_prev = parse_duration(cur['report'].get('duration')), parse_duration(prev['duration'])
            if d_cur and d_prev:
                today_sec = (d_cur - d_prev) / today_q
        err_delta = err_total - (prev['errors_total'] or 0)

    # 错题：模块级 diff（区分"清掉"和"新增"，净变化看不出这个）
    err_modules = {e['module']: e['count'] for e in (cur['errors'].get('list') or [])}
    err_cleared = err_added = None
    if prev and prev.get('errors_json'):
        old_map = {e['module']: e['count'] for e in json.loads(prev['errors_json'])}
        for k in set(list(old_map) + list(err_modules)):
            d = err_modules.get(k, 0) - old_map.get(k, 0)
            if d < 0:
                err_cleared = (err_cleared or 0) - d
            elif d > 0:
                err_added = (err_added or 0) + d

    # 今天有没有专门做"错题重练"
    redo_items = [i for i in items if '错题' in str(i.get('type') or '')]
    redo_q = sum(i.get('total') or 0 for i in redo_items)

    modules_now = {r['name']: r for r in cur['progress']['rows'] if r['name'] in MAJOR}
    module_delta = {}
    if prev and prev.get('modules'):
        old = json.loads(prev['modules'])
        for k, v in modules_now.items():
            module_delta[k] = v['done'] - (old.get(k, {}).get('done', 0))

    return {
        'date': date, 'total_q': total_q, 'accuracy': acc, 'sec_q': sec_q,
        'duration': cur['report'].get('duration'), 'days': cur['report'].get('practiceDays'),
        'rank': cur['report'].get('rank'), 'errors': cur['errors'].get('list') or [],
        'err_total': err_total, 'today_q': today_q, 'today_acc': today_acc,
        'today_sec': today_sec, 'err_delta': err_delta, 'module_delta': module_delta,
        'modules': modules_now, 'unsub': unsub, 'sub': sub, 'records': items,
        'err_modules': err_modules, 'err_cleared': err_cleared, 'err_added': err_added,
        'redo_papers': len(redo_items), 'redo_q': redo_q,
        'has_prev': bool(prev),
    }


def advice(r, lectures) -> list:
    out = []
    # 首次运行没有当日增量，就用累计值判断，避免日报空转
    acc = r['today_acc'] if r['today_acc'] is not None else r['accuracy']
    sec = r['today_sec'] if r['today_sec'] is not None else r['sec_q']
    label = '' if r['today_acc'] is not None else '（累计）'
    g_quant = pick(lectures, '点与线') or pick(lectures, '数量规律')
    g_pos = pick(lectures, '位置规律')
    g_sym = pick(lectures, '对称')
    s_step = pick(lectures, '四步解题法')
    s_red = pick(lectures, '红格纸') or pick(lectures, '书写')

    if r['today_q'] == 0:
        out.append('**今天 0 道题**。最小动作：打开题库做 10 道资料分析，20 分钟内交卷——'
                   '不交卷等于没做，数据也不进统计。')
    if sec and sec > TARGET_SEC * 1.6:
        line = f'**速度{label} {sec:.0f} 秒/题，是目标（{TARGET_SEC:.0f} 秒）的 {sec/TARGET_SEC:.1f} 倍**。'
        line += '资料分析限时练：用站内「第 3 天 · 比重与平均数」15 题，限 20 分钟，超时直接交卷。'
        c = cite(s_step, '把这套「审题定向→扫描定位→加工提炼→规范书写」的顺序搬到资料分析：先看问什么，再回材料找数，别从头读。')
        if c:
            line += c
        out.append(line)
    if acc is not None and acc < 70:
        line = f'**正确率{label} {acc:.0f}%，低于 70%**。先别刷新题，把错题本里同类题重做一遍。'
        gnum = sum(x['count'] for x in r['errors'] if x['module'] == '判断推理')
        if gnum:
            c = cite(g_quant, f'你错题本里判断推理有 {gnum} 道，数量规律（点线/面素角/一笔画）是最容易靠口诀提分的板块。')
            if c:
                line += c
        out.append(line)
    if r['unsub'] >= 2:
        line = f'**{r["unsub"]} 次练习没交卷（占 {r["unsub"]/(r["unsub"]+r["sub"] or 1)*100:.0f}%）**。'
        line += '开了题不交卷，既不计分也不生成错题，等于白开。'
        c = cite(s_red, '限时训练的意义就在这：平时不掐表，考场一定写不完。')
        if c:
            line += c
        out.append(line)
    if r.get('err_cleared') and r['err_cleared'] >= 5:
        out.insert(0, f'**清掉 {r["err_cleared"]} 道错题**，这是今天最值钱的进展——'
                       '错题本降下来，比多刷 20 道新题有用。')
    if (r.get('err_added') or 0) > (r.get('err_cleared') or 0) and r.get('err_added'):
        out.append(f'**新增错题 {r["err_added"]} 道，多于清理的 {r.get("err_cleared") or 0} 道**。'
                   '按这个速度错题本只会越来越厚，明天必须先清 5 道再做新题。')
    if r.get('redo_q') == 0 and r.get('err_total', 0) >= 20:
        out.append(f'**今天没有专门重做错题**（错题本已 {r["err_total"]} 道）。'
                   '华图错题重练每份只要十来分钟，比刷新题提分快。')
    if r['err_delta'] is not None and r['err_delta'] > 0:
        out.append(f'**错题本净增 {r["err_delta"]} 道**（现共 {r["err_total"]} 道）。'
                   '错题在涨说明在刷新题但没消化，明天先清 5 道再开新题。')
    elif r['err_delta'] is not None and r['err_delta'] < 0:
        out.append(f'**错题清了 {abs(r["err_delta"])} 道**，这是今天最值钱的进展。')
    if r['sec_q'] > 0 and r['sec_q'] <= TARGET_SEC * 1.2:
        out.append(f'速度已经接近目标（{r["sec_q"]:.0f} 秒/题），接下来抓正确率。')
    return out[:4]


def fetch_wrongs(max_topics: int = 8):
    """抓错题本（按子题型分组的原题）。失败返回 []。"""
    try:
        r = subprocess.run([str(RUN_SH), 'wrongs', str(max_topics)],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            return []
        return json.loads(r.stdout).get('topics') or []
    except Exception:
        return []


def group_wrongs(topics: list) -> list:
    """把子题型下的题按 题型 归类，去重后每类留一道代表题"""
    seen_stem = set()
    groups = {}
    for tp in topics:
        for q in tp.get('questions') or []:
            key = (q.get('topicKind') or q.get('topicModule') or tp['name'].split('（')[0]).strip()
            stem_key = (q.get('stem') or '')[:40]
            if not stem_key or stem_key in seen_stem:
                continue
            seen_stem.add(stem_key)
            g = groups.setdefault(key, {'kind': key, 'module': q.get('topicModule') or '',
                                        'n': 0, 'rep': None})
            g['n'] += 1
            if g['rep'] is None:
                g['rep'] = q
    return sorted(groups.values(), key=lambda x: -x['n'])


def wrongs_by_topic(date: str) -> list:
    """从 questions 表取当日错题，按题型归类，每类只留一道代表题（耗时最长的）"""
    try:
        with sqlite3.connect(DB) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                'SELECT * FROM questions WHERE date=? AND ok=0 ORDER BY seconds DESC', (date,)
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    groups = {}
    for r in rows:
        key = r['kind'] or r['module'] or '其他'
        g = groups.setdefault(key, {'kind': key, 'module': r['module'], 'n': 0,
                                    'maxSec': 0, 'rep': None})
        g['n'] += 1
        if (r['seconds'] or 0) >= g['maxSec']:
            g['maxSec'] = r['seconds'] or 0
            g['rep'] = {'qno': r['qno'], 'seconds': r['seconds'],
                        'siteAcc': r['site_acc'], 'source': (r['source'] or '')[:40],
                        'stem': (r['stem'] or '') if 'stem' in r.keys() else '',
                        'options': json.loads(r['options']) if ('options' in r.keys() and r['options']) else []}
    return sorted(groups.values(), key=lambda x: -x['n'])


def _method_for(kind: str, module: str):
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('hb', HERE / 'huatu_batch.py')
        hb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hb)
        return hb.pick_method(kind, module, hb.load_methods())
    except Exception:
        return None


def render(r, tips) -> str:
    L = []
    L.append(f'# 华图刷题日报 · {r["date"]}')
    L.append('')
    if r['has_prev']:
        dq = r['today_q']
        sign = '+' if (dq or 0) >= 0 else ''
        L.append(f'**今日 {sign}{dq} 题**'
                 + (f'，正确率 {r["today_acc"]:.0f}%' if r['today_acc'] is not None else '')
                 + (f'，{r["today_sec"]:.0f} 秒/题' if r['today_sec'] else '')
                 + '。')
    else:
        L.append(f'**首次记录**，今天是基线：累计 {r["total_q"]} 题、正确率 {r["accuracy"]:.2f}%、'
                 f'{r["sec_q"]:.0f} 秒/题。明天开始有对比。')
    L.append('')
    L.append('| 指标 | 当前 | 目标 | 差距 |')
    L.append('|---|---|---|---|')
    L.append(f'| 累计题量 | {r["total_q"]} | 37 天 ≥ 1500 | {max(0, 1500 - r["total_q"])} |')
    L.append(f'| 正确率 | {r["accuracy"]:.2f}% | {TARGET_ACC:.0f}% | {r["accuracy"] - TARGET_ACC:+.1f} pt |')
    L.append(f'| 速度 | {r["sec_q"]:.0f} 秒/题 | {TARGET_SEC:.0f} 秒 | {r["sec_q"] - TARGET_SEC:+.0f} 秒 |')
    L.append(f'| 错题本 | {r["err_total"]} 道 | 个位数 | {r["err_total"] - 9:+d} |')
    L.append(f'| 练习天数 | {r["days"]} 天 | 连续 | — |')
    L.append('')
    moved = {k: v for k, v in (r.get('module_delta') or {}).items() if v}
    if moved:
        L.append('**模块增量**：' + '、'.join(f'{k} {v:+d}' for k, v in moved.items()))
        L.append('')
    elif r.get('has_prev'):
        L.append('> 题库页的「已做」只统计章节练习，智能刷题不计入，所以模块增量常为 0——'
                 '模块分布请看下面的错题分布。')
        L.append('')
    if r['errors']:
        L.append('**错题分布**：' + '、'.join(f'{e["module"]} {e["count"]}' for e in r['errors']))
        L.append('')
        bits = []
        if r.get('err_cleared'):
            bits.append(f'清掉 {r["err_cleared"]} 道')
        if r.get('err_added'):
            bits.append(f'新增 {r["err_added"]} 道')
        if bits:
            L.append('**错题变化**：' + '、'.join(bits) +
                     (f'（净 {"+" if (r["err_added"] or 0) - (r["err_cleared"] or 0) >= 0 else ""}'
                      f'{(r["err_added"] or 0) - (r["err_cleared"] or 0)}）' if bits else ''))
            L.append('')
        if r.get('redo_q'):
            L.append(f'**今天专门重做了 {r["redo_papers"]} 份错题、共 {r["redo_q"]} 道**。')
            L.append('')
    d = r.get('detail') or {}
    if d.get('caught'):
        L.append('## 题型级诊断')
        L.append('')
        L.append(f'本轮解析 {d["papers"]} 份练习，取到 {d["caught"]}/{d["expected"]} 题明细'
                 '（解析页分段渲染，覆盖率不满时按可见部分统计）。')
        L.append('')
        if d.get('wrong_top'):
            L.append('**错题集中在**：' + '、'.join(f'{k} {v} 道' for k, v in d['wrong_top']))
            L.append('')
        if d.get('slowest'):
            L.append('**最慢的题**：')
            for x in d['slowest']:
                L.append(f'- 第 {x["n"]} 题 · {x["kind"]} · {x["sec"]} 秒 · {x["stem"]}')
            L.append('')
        if d.get('over120'):
            L.append(f'**超过 120 秒的题有 {d["over120"]} 道**——这些是真正拖垮行测的题，'
                     '考场上超过 90 秒就该跳过。')
            L.append('')

    wg = r.get('wrong_groups') or []
    if wg:
        L.append(f'## 错题复盘（{len(wg)} 类 / {sum(g["n"] for g in wg)} 道）')
        L.append('')
        L.append('同一类只讲一道，其余同类题错因相同。')
        L.append('')
        for g in wg:
            q = g['rep'] or {}
            L.append(f"### {g['kind']}（{g['n']} 道）")
            L.append('')
            if q.get('stem'):
                L.append(f"> {q['stem']}")
                if q.get('options'):
                    L.append('> ' + '　'.join(f"{o.get('k')}.{o.get('t')}" for o in q['options'] if o.get('k')))
                L.append('')
            meta = []
            if q.get('answer'):
                meta.append(f"正确答案 {q['answer']}")
            if q.get('siteAccuracy'):
                meta.append(f"全站正确率 {q['siteAccuracy']}%")
            if meta:
                L.append('　'.join(meta))
                L.append('')
            m = _method_for(g['kind'], g['module'])
            if m:
                L.append('**这一类的方法**')
                for x in m['must'][:3]:
                    L.append(f'- {x}')
                L.append('')

    w = [] if wg else (r.get('wrongs') or [])
    if w:
        L.append(f'## 昨日错题复盘（{len(w)} 类）')
        L.append('')
        L.append('同一类只挑一道讲，其余同类题的错因是一样的。')
        L.append('')
        for g in w:
            rep = g['rep'] or {}
            L.append(f"### {g['kind']}（{g['n']} 道）")
            L.append('')
            L.append(f"代表题：第 {rep.get('qno')} 题 · 用时 {rep.get('seconds')} 秒 · "
                     f"全站正确率 {rep.get('siteAcc') or '—'}%")
            if rep.get('stem'):
                L.append('')
                L.append(f"> {rep['stem']}")
                if rep.get('options'):
                    L.append('> ' + '　'.join(f"{o.get('k')}.{o.get('t')}" for o in rep['options'] if o.get('k')))
            m = _method_for(g['kind'], g['module'])
            if m:
                L.append('')
                L.append('**这一类的方法**')
                for x in m['must'][:3]:
                    L.append(f'- {x}')
            L.append('')

    if tips:
        L.append('## 今天该做什么')
        L.append('')
        for t in tips:
            L.append(f'- {t}')
        L.append('')
    L.append(f'> 数据源：华图在线评估报告 / 答题记录 / 错题本，抓取于 {dt.datetime.now():%Y-%m-%d %H:%M}')
    return '\n'.join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-fetch', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--date', default=dt.date.today().isoformat())
    ap.add_argument('--papers', type=int, default=6, help='逐题抓取最近几份练习')
    ap.add_argument('--wrong-topics', type=int, default=8, help='错题本最多抓几个子题型')
    args = ap.parse_args()

    init_db()
    if args.no_fetch:
        with sqlite3.connect(DB) as c:
            c.row_factory = sqlite3.Row
            row = c.execute('SELECT * FROM snapshots WHERE date=?', (args.date,)).fetchone()
            if not row:
                print('没有该日快照', file=sys.stderr)
                return 1
            cur = {'report': {'totalQuestions': row['total_q'], 'accuracy': row['accuracy'],
                              'secPerQuestion': row['sec_q'], 'duration': row['duration'],
                              'practiceDays': row['practice_days'], 'rank': ''},
                   'progress': {'rows': list(json.loads(row['modules']).values())},
                   'errors': {'total': row['errors_total'],
                              'list': json.loads(row['errors_json']) if ('errors_json' in row.keys() and row['errors_json']) else []},
                   'records': {'items': json.loads(row['records'])}, 'fetchedAt': row['ts']}
    else:
        cur = fetch()

    date = args.date
    lectures = lecture_index()
    prev = prev_snapshot(date)
    if not args.no_fetch:      # 调试模式只重算，不回写快照（否则会把错题明细覆盖成空）
        save(date, cur)

    det = None if args.no_fetch else fetch_detail(args.papers)
    store_detail(date, det)
    r = build(date, cur, prev, lectures)
    r['detail'] = detail_stats(date, det)
    # 错题：优先昨天，没有就用今天抓到的
    r['wrongs'] = wrongs_by_topic((dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()) \
        or wrongs_by_topic(date)
    if not args.no_fetch:
        r['wrong_groups'] = group_wrongs(fetch_wrongs(args.wrong_topics))

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(render(r, advice(r, lectures)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
