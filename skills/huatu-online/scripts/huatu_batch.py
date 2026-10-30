#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""华图题型批量分析：把最近 N 份练习的逐题明细按题型聚合，
输出「最该补的题型」与「最该提速的题型」，并对每个薄弱题型给方法卡。

用法：
  python3 huatu_batch.py                 # 抓最近 10 份，出报告
  python3 huatu_batch.py --papers 20
  python3 huatu_batch.py --from-db       # 不抓取，用库里已有数据（调试）
  python3 huatu_batch.py --json
"""
import argparse
import json
import pathlib
import sqlite3
import statistics
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
RUN_SH = HERE / 'run.sh'
METHODS = HERE.parent / 'references' / 'methods.json'
DB = pathlib.Path.home() / '.workbuddy/data/huatu_daily.db'

SLOW_SEC = 90          # 单题目标上限
OUTLIER_SEC = 600      # 超过这个时长视为「人走开了」，不计入平均
MIN_SAMPLE = 3         # 少于 3 题不做结论


def load_methods() -> list:
    return json.loads(METHODS.read_text(encoding='utf-8'))['topics']


def pick_method(kind: str, module: str, methods: list):
    text = f'{kind} {module}'
    for m in methods:
        if any(k in text for k in m['match']):
            return m
    return None


def fetch(papers: int) -> dict:
    r = subprocess.run([str(RUN_SH), 'detail', str(papers)],
                       capture_output=True, text=True, timeout=1500)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or '')[-300:])
    return json.loads(r.stdout)


def load_from_db() -> dict:
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute('SELECT * FROM questions').fetchall()
    papers = {}
    for r in rows:
        p = papers.setdefault(r['paper_id'], {'paperId': r['paper_id'], 'modules': [], 'questions': []})
        p['questions'].append({
            'n': r['qno'], 'topicModule': r['module'], 'topicKind': r['kind'],
            'topicDetail': r['detail'], 'ok': None if r['ok'] is None else bool(r['ok']),
            'seconds': r['seconds'], 'siteAccuracy': r['site_acc'],
        })
    return {'papers': list(papers.values())}


def aggregate(d: dict) -> dict:
    """按题型（kind）聚合：题量、错题数、错误率、耗时中位数、全站正确率"""
    stats = {}
    for p in d.get('papers', []):
        for q in p.get('questions', []):
            if q.get('ok') is None:
                continue
            kind = (q.get('topicKind') or q.get('topicModule') or '其他').strip()
            s = stats.setdefault(kind, {'kind': kind, 'module': q.get('topicModule') or '',
                                        'n': 0, 'wrong': 0, 'secs': [], 'site': [], 'items': []})
            s['items'].append({
                'n': q.get('n'), 'stem': (q.get('stem') or '').strip(),
                'options': q.get('options') or [], 'mine': q.get('mine') or '',
                'answer': q.get('answer') or '', 'ok': q.get('ok'),
                'seconds': q.get('seconds'), 'siteAcc': q.get('siteAccuracy'),
            })
            s['n'] += 1
            if q['ok'] is False:
                s['wrong'] += 1
            if q.get('seconds') and q['seconds'] < OUTLIER_SEC:
                s['secs'].append(q['seconds'])
            if q.get('siteAccuracy'):
                s['site'].append(q['siteAccuracy'])

    for s in stats.values():
        s['wrongRate'] = round(s['wrong'] / s['n'] * 100, 1) if s['n'] else 0
        s['medSec'] = round(statistics.median(s['secs'])) if s['secs'] else None
        s['avgSec'] = round(sum(s['secs']) / len(s['secs'])) if s['secs'] else None
        s['siteAcc'] = round(sum(s['site']) / len(s['site'])) if s['site'] else None
    return stats


def save_stats(date: str, stats: dict) -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS topic_stats (
            date TEXT, kind TEXT, n INTEGER, wrong INTEGER,
            wrong_rate REAL, med_sec INTEGER, PRIMARY KEY (date, kind))""")
        c.execute('DELETE FROM topic_stats WHERE date=?', (date,))
        for s in stats.values():
            c.execute('INSERT OR REPLACE INTO topic_stats VALUES (?,?,?,?,?,?)',
                      (date, s['kind'], s['n'], s['wrong'], s['wrongRate'], s['medSec']))


def prev_stats(date: str) -> dict:
    try:
        with sqlite3.connect(DB) as c:
            c.row_factory = sqlite3.Row
            row = c.execute('SELECT MAX(date) d FROM topic_stats WHERE date < ?', (date,)).fetchone()
            if not row or not row['d']:
                return {}
            rows = c.execute('SELECT * FROM topic_stats WHERE date=?', (row['d'],)).fetchall()
            return {'date': row['d'], 'rows': {r['kind']: dict(r) for r in rows}}
    except sqlite3.OperationalError:      # 首次运行还没有 topic_stats 表
        return {}


def build_report(d: dict, methods: list, prev: dict = None) -> tuple[str, dict]:
    stats = aggregate(d)
    usable = [s for s in stats.values() if s['n'] >= MIN_SAMPLE]

    by_wrong = sorted([s for s in usable if s['wrong'] > 0],
                      key=lambda s: (-s['wrongRate'], -s['n']))
    by_slow = sorted([s for s in usable if s['medSec'] and s['medSec'] > SLOW_SEC],
                     key=lambda s: -s['medSec'])

    total_q = sum(s['n'] for s in stats.values())
    total_wrong = sum(s['wrong'] for s in stats.values())
    papers = len(d.get('papers') or [])

    L = ['# 华图题型体检（批量）', '']
    L.append(f'样本：最近 {papers} 份练习、{total_q} 题明细（错 {total_wrong} 题，'
             f'总体错误率 {total_wrong/total_q*100:.1f}%）。'
             f'耗时统计已剔除 >{OUTLIER_SEC} 秒的「人走开了」异常值。')
    L.append('')

    L.append('| 题型 | 做题数 | 错题 | 错误率 | 耗时中位 | 全站正确率 | 判断 |')
    L.append('|---|---|---|---|---|---|---|')
    for s in sorted(usable, key=lambda x: (-x['n'])):
        verdict = []
        if s['wrongRate'] >= 40:
            verdict.append('**重点补**')
        elif s['wrong'] >= 2:
            verdict.append('待补')
        if s['medSec'] and s['medSec'] > SLOW_SEC:
            verdict.append('**偏慢**')
        elif s['medSec'] and s['medSec'] <= 20 and s['wrongRate'] >= 30:
            verdict.append('**快而错**')
        if not verdict:
            verdict.append('稳')
        L.append(f"| {s['kind']} | {s['n']} | {s['wrong']} | {s['wrongRate']}% | "
                 f"{s['medSec'] if s['medSec'] else '—'} 秒 | "
                 f"{s['siteAcc'] if s['siteAcc'] else '—'}% | {' '.join(verdict)} |")
    L.append('')

    # 方法卡：先错题，再慢题，去重
    seen = set()

    def cases_html(s, limit=2):
        """挑最值得讲的案例：先错题（耗时长的优先），再最慢的题"""
        bad = [x for x in s['items'] if x['ok'] is False]
        bad.sort(key=lambda x: -(x['seconds'] or 0))
        slow = [x for x in s['items'] if x['ok'] is not False]
        slow.sort(key=lambda x: -(x['seconds'] or 0))
        picks = (bad + slow)[:limit]
        if not picks:
            return []
        out = ['**你的案例**', '']
        for i, q in enumerate(picks, 1):
            opts = '　'.join(f"{o['k']}.{o['t']}" for o in q['options'] if o.get('k'))
            mark = '错' if q['ok'] is False else '对'
            out.append(f"{i}. 第 {q['n']} 题（{q['seconds'] or '—'} 秒，全站正确率 {q['siteAcc'] or '—'}%，{mark}）")
            out.append(f"   题干：{q['stem'][:120]}")
            if opts:
                out.append(f"   选项：{opts}")
            out.append(f"   你选 {q['mine'] or '—'}，正确 {q['answer'] or '—'}")
            out.append('')
        return out

    def card(s, reason, only_speed=False):
        m = pick_method(s['kind'], s['module'], methods)
        head = f"### {s['kind']}（{reason}）"
        if not m:
            return [head, '', '- 方法库暂无该题型的专项卡，按通用策略：先求对再求快，单题 90 秒上限。', '']
        out = [head, '']
        out += cases_html(s, 2 if not only_speed else 1)
        if not only_speed:
            out.append(f"**同类方法：{m['title']}**")
            for x in m['must']:
                out.append(f'- {x}')
            out.append('')
        out.append('**提速**')
        for x in m['speed']:
            out.append(f'- {x}')
        out.append('')
        return out

    if by_wrong:
        L.append('## 一、反复做错的题型：先把方法补上')
        L.append('')
        for s in by_wrong[:3]:
            if s['kind'] in seen:
                continue
            seen.add(s['kind'])
            L += card(s, f"{s['n']} 题错 {s['wrong']}，错误率 {s['wrongRate']}%")
    else:
        L.append('## 一、反复做错的题型')
        L.append('')
        L.append('样本里没有稳定出错的题型，先把题量刷起来再判断。')
        L.append('')

    if by_slow:
        L.append('## 二、做得慢的题型：换算法、设上限')
        L.append('')
        shown = 0
        for s in by_slow:
            if shown >= 3:
                break
            already = s['kind'] in seen
            seen.add(s['kind'])
            L += card(s, f"耗时中位 {s['medSec']} 秒/题，目标 {SLOW_SEC} 秒", only_speed=already)
            shown += 1
    else:
        L.append('## 二、做得慢的题型')
        L.append('')
        L.append(f'可用样本里没有中位耗时超过 {SLOW_SEC} 秒的题型。')
        L.append('')

    if prev:
        L.append(f"## 四、与上次（{prev['date']}）相比")
        L.append('')
        L.append('| 题型 | 错误率变化 | 耗时变化 | 说明 |')
        L.append('|---|---|---|---|')
        moved = False
        for k, cur_s in sorted(stats.items()):
            old_s = prev['rows'].get(k)
            if not old_s or cur_s['n'] < MIN_SAMPLE:
                continue
            dr = cur_s['wrongRate'] - (old_s['wrong_rate'] or 0)
            ds = (cur_s['medSec'] or 0) - (old_s['med_sec'] or 0)
            if abs(dr) < 5 and abs(ds) < 10:
                continue
            moved = True
            hint = []
            if dr <= -10:
                hint.append('错误率明显下降')
            elif dr >= 10:
                hint.append('错误率上升')
            if ds <= -15:
                hint.append('提速了')
            elif ds >= 15:
                hint.append('变慢了')
            L.append(f"| {k} | {dr:+.1f} pt | {ds:+d} 秒 | {'、'.join(hint) or '小幅变化'} |")
        if not moved:
            L.append('| — | 无明显变化 | — | 各题型基本持平 |')
        L.append('')

    if by_wrong:
        first = by_wrong[0]
        L.append(f"## 三、先补这一个")
        L.append('')
        L.append(f"**{first['kind']}**——{first['n']} 题错 {first['wrong']} 道、错误率 {first['wrongRate']}%，"
                 f"是全站正确率 {first['siteAcc'] or '—'}% 的题型。先把方法卡里的公式抄到一张纸上，"
                 '明天做同类题时对照着用，做对 10 道再谈提速。')
        L.append('')
    L.append('> 题型标签来自华图解析页的「考点」三级分类；一份 10 题的练习解析页通常只渲染前 5 题，'
             '样本会随份数增加而变大。')
    return '\n'.join(L), {'total': total_q, 'wrong': total_wrong,
                          'topics': {k: {'n': v['n'], 'wrong': v['wrong'],
                                         'wrongRate': v['wrongRate'], 'medSec': v['medSec']}
                                     for k, v in stats.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--papers', type=int, default=10)
    ap.add_argument('--from-db', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--compare', action='store_true', help='与上次统计对比')
    args = ap.parse_args()

    methods = load_methods()
    try:
        d = load_from_db() if args.from_db else fetch(args.papers)
    except Exception as e:
        print(f'抓取失败：{e}', file=sys.stderr)
        return 1

    today = __import__('datetime').date.today().isoformat()
    if not args.from_db:
        save_stats(today, aggregate(d))
    prev = prev_stats(today) if args.compare else {}
    text, summary = build_report(d, methods, prev)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
