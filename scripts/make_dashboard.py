# -*- coding: utf-8 -*-
"""ダッシュボード生成
最新スナップショット＋全レビュー結果から、
  docs/latest.json  … Claudeアプリが読む機械可読サマリー
  docs/index.html   … iPhoneのSafariでそのまま見られる静的ダッシュボード（GitHub Pages用）
を生成する。外部アセット依存なし。
"""
import sys
import io
import os
import re
import json
import glob
import html
from datetime import date
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(BASE, "data", "snapshots")
DOCS = os.path.join(BASE, "docs")

MKT_LABEL = {"jp": "日本株", "us": "米国株"}


def method_version():
    try:
        with open(os.path.join(BASE, "METHOD.md"), encoding="utf-8") as f:
            m = re.search(r"現行バージョン:\s*(v[\d.]+)", f.read())
            return m.group(1) if m else "?"
    except OSError:
        return "?"


def latest_snapshot():
    csvs = sorted(p for p in glob.glob(os.path.join(SNAP, "snapshot_*.csv"))
                  if re.fullmatch(r"snapshot_\d{8}\.csv", os.path.basename(p)))
    if not csvs:
        return None, None
    path = csvs[-1]
    with open(path[:-4] + ".json", encoding="utf-8") as f:
        meta = json.load(f)
    return pd.read_csv(path), meta


def all_reviews():
    out = []
    for p in sorted(glob.glob(os.path.join(SNAP, "snapshot_*_review_*.json"))):
        with open(p, encoding="utf-8") as f:
            out.append(json.load(f))
    out.sort(key=lambda r: (r.get("snapshot_date", ""), r.get("elapsed_days", 0)))
    return out


def fnum(v, fmt="{:.1f}"):
    return fmt.format(v) if v is not None and not pd.isna(v) else "—"


def build_latest_json(snap, meta, reviews):
    picks = {}
    if snap is not None:
        for mkt, g in snap.groupby("market"):
            picks[mkt] = [
                {k: (None if pd.isna(row.get(k)) else row.get(k)) for k in
                 ("ticker", "name", "sector", "combined_score", "technical_score",
                  "fundamental_score", "ret20", "per", "pbr", "mcap",
                  "next_earnings", "entry_close")}
                for _, row in g.iterrows()]
    return {
        "generated": date.today().isoformat(),
        "method_version": method_version(),
        "snapshot_date": meta.get("snapshot_date") if meta else None,
        "note": meta.get("note") if meta else None,
        "benchmarks": meta.get("benchmarks") if meta else None,
        "review_due": meta.get("review_due") if meta else None,
        "mcap_unit": {"jp": "億円", "us": "$B"},
        "picks": picks,
        "reviews": reviews,
    }


def pick_table(g, is_jp):
    rows = []
    for i, (_, r) in enumerate(g.iterrows(), 1):
        rows.append(
            f"<tr><td>{i}</td><td>{html.escape(str(r['name']))}<br>"
            f"<span class=t>{html.escape(str(r['ticker']))}</span></td>"
            f"<td>{html.escape(str(r.get('sector', '')))}</td>"
            f"<td>{fnum(r.get('combined_score'))}</td>"
            f"<td>{fnum(r.get('per'))}</td><td>{fnum(r.get('pbr'), '{:.2f}')}</td>"
            f"<td>{fnum(r.get('mcap'), '{:,.0f}' if is_jp else '{:,.1f}')}</td>"
            f"<td>{r.get('next_earnings') if isinstance(r.get('next_earnings'), str) else '—'}</td></tr>")
    unit = "億円" if is_jp else "$B"
    return (f"<div class=scroll><table><thead><tr><th>#</th><th>銘柄</th><th>セクター</th>"
            f"<th>総合</th><th>PER</th><th>PBR</th><th>時価総額({unit})</th><th>次回決算</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>")


def review_section(reviews):
    if not reviews:
        return "<p>答え合わせ実績はまだありません。</p>"
    blocks = []
    for r in reviews:
        rows = []
        for mkt, s in r.get("markets", {}).items():
            corr = s.get("rank_corr_combined_score")
            rows.append(
                f"<tr><td>{MKT_LABEL.get(mkt, mkt)}</td>"
                f"<td>{s.get('avg_return_pct')}%</td>"
                f"<td>{s.get('benchmark_return_pct')}%</td>"
                f"<td>{s.get('avg_excess_pct')}%</td>"
                f"<td>{s.get('win_rate_vs_benchmark')}%</td>"
                f"<td>{corr if corr is not None else '—'}</td></tr>")
        worst = []
        for mkt, s in r.get("markets", {}).items():
            for w in s.get("worst", [])[:3]:
                worst.append(f"{html.escape(str(w['name']))} {w['return_pct']:+.1f}%")
        blocks.append(
            f"<h3>{r.get('snapshot_date')} 選定分 — {r.get('label')} レビュー"
            f"（{r.get('review_date')}実施）</h3>"
            f"<div class=scroll><table><thead><tr><th>市場</th><th>平均リターン</th>"
            f"<th>ベンチ</th><th>超過</th><th>勝率(対ベンチ)</th><th>スコア順位相関</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
            f"<p class=t>ワースト: {html.escape(' / '.join(worst))}</p>")
    return "".join(blocks)


def build_html(snap, meta, reviews):
    ver = method_version()
    pick_html = ""
    if snap is not None:
        for mkt in ("jp", "us"):
            g = snap[snap["market"] == mkt]
            if len(g):
                pick_html += f"<h3>{MKT_LABEL[mkt]} {len(g)}銘柄</h3>" + pick_table(g, mkt == "jp")
    due = meta.get("review_due", {}) if meta else {}
    due_html = " / ".join(f"{k}: {v}" for k, v in due.items())
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stock Judge 簡易ダッシュボード</title>
<style>
body{{font-family:-apple-system,'Hiragino Sans',sans-serif;margin:0;padding:14px;
background:#f6f7f9;color:#1c1e21;font-size:14px}}
h1{{font-size:18px}} h2{{font-size:16px;border-bottom:2px solid #2f6fed;padding-bottom:4px;
margin-top:26px}} h3{{font-size:14px;margin:14px 0 6px}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{border-collapse:collapse;white-space:nowrap;background:#fff;font-size:12px}}
th,td{{border:1px solid #dde1e6;padding:5px 8px;text-align:right}}
th{{background:#eef2f8}} td:nth-child(2),td:first-child{{text-align:left}}
.t{{color:#667085;font-size:11px}}
.meta{{background:#fff;border:1px solid #dde1e6;border-radius:8px;padding:10px;font-size:12px}}
footer{{margin-top:30px;font-size:11px;color:#667085}}
</style></head><body>
<h1>📈 Stock Judge — 日米「儲かる20銘柄」簡易ダッシュボード</h1>
<div class=meta>
手法: METHOD {ver}（テクニカル50%×ファンダ50%の機械選定・セクター上限4）<br>
選定日: {meta.get('snapshot_date') if meta else '—'} ／ 更新: {date.today().isoformat()}<br>
答え合わせ予定: {due_html or '—'}<br>
⚠️ 簡易版はスコア機械選定です。決算ミス・不祥事等の赤信号チェックは
Claudeアプリで「この銘柄の悪材料を調べて」と依頼して補完してください。投資は自己責任で。
</div>
<h2>最新選定</h2>
{pick_html or '<p>選定データなし</p>'}
<h2>答え合わせ結果</h2>
{review_section(reviews)}
<footer>machine-readable: <a href="latest.json">latest.json</a> ／
生成: GitHub Actions（毎朝08:00 JST）</footer>
</body></html>"""


def main():
    os.makedirs(DOCS, exist_ok=True)
    snap, meta = latest_snapshot()
    reviews = all_reviews()
    with open(os.path.join(DOCS, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(build_latest_json(snap, meta, reviews), f,
                  ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_html(snap, meta, reviews))
    print(f"[OK] docs/latest.json / docs/index.html 生成（レビュー{len(reviews)}件）")


if __name__ == "__main__":
    main()
