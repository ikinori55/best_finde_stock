# -*- coding: utf-8 -*-
"""答え合わせ（スナップショット検証）
snapshot.py が記録した選定リストについて、現在価格でリターンを計算し、
ベンチマーク(日経225/S&P500)対比の超過リターン・勝率を市場別に集計する。
出力はレビューCSV+サマリーJSON。**なぜ外れたかの解釈はLLM(エージェント)の仕事**で、
このスクリプトは事実(数字)だけを揃える。

使い方:
  python review.py --snapshot data/snapshots/snapshot_20260705.csv
  python review.py --snapshot-dir data/snapshots            # 最新スナップショットを自動選択
  オプション: --label 30d  (レビューのラベル。省略時は経過日数から自動判定)
"""
import sys
import io
import os
import json
import glob
import argparse
from datetime import date
import numpy as np
import pandas as pd
import yfinance as yf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

HORIZONS = [7, 30, 90, 180]


def fetch_closes(tickers):
    data = yf.download(tickers=tickers, period="5d", group_by="ticker",
                       threads=True, progress=False, auto_adjust=True)
    out = {}
    for t in tickers:
        try:
            sub = data[t] if len(tickers) > 1 else data
            out[t] = float(sub["Close"].dropna().iloc[-1])
        except (KeyError, IndexError):
            out[t] = None
    return out


def nearest_horizon(elapsed_days):
    return min(HORIZONS, key=lambda h: abs(h - elapsed_days))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--snapshot", help="スナップショットCSVパス")
    g.add_argument("--snapshot-dir", help="ディレクトリ内の最新snapshot_*.csvを使う")
    ap.add_argument("--label", default=None, help="レビューラベル(例 7d/30d)。省略時は自動")
    ap.add_argument("--outdir", default=None, help="省略時はスナップショットと同じ場所")
    args = ap.parse_args()

    snap_path = args.snapshot
    if args.snapshot_dir:
        candidates = sorted(glob.glob(os.path.join(args.snapshot_dir, "snapshot_*.csv")))
        if not candidates:
            print("[ERROR] snapshot_*.csv が見つかりません", file=sys.stderr)
            sys.exit(1)
        snap_path = candidates[-1]

    snap = pd.read_csv(snap_path)
    snap_date = pd.to_datetime(snap["snapshot_date"].iloc[0]).date()
    elapsed = (date.today() - snap_date).days
    label = args.label or f"{nearest_horizon(elapsed)}d"
    print(f"[INFO] スナップショット {snap_path} ({snap_date}, {elapsed}日経過) → レビューラベル {label}",
          file=sys.stderr)

    snap = snap.dropna(subset=["entry_close"]).copy()
    tickers = snap["ticker"].tolist()
    benches = snap["benchmark"].dropna().unique().tolist()
    closes = fetch_closes(tickers + benches)

    snap["current_close"] = snap["ticker"].map(closes)
    snap["benchmark_current_close"] = snap["benchmark"].map(closes)
    snap = snap.dropna(subset=["current_close", "benchmark_current_close"]).copy()

    snap["return_pct"] = (snap["current_close"] / snap["entry_close"] - 1) * 100
    snap["benchmark_return_pct"] = (
        snap["benchmark_current_close"] / snap["benchmark_entry_close"] - 1) * 100
    snap["excess_return_pct"] = snap["return_pct"] - snap["benchmark_return_pct"]
    snap["beat_benchmark"] = snap["excess_return_pct"] > 0

    snap = snap.sort_values("excess_return_pct", ascending=False)

    outdir = args.outdir or os.path.dirname(snap_path)
    stem = os.path.splitext(os.path.basename(snap_path))[0]
    out_csv = os.path.join(outdir, f"{stem}_review_{label}_{date.today().strftime('%Y%m%d')}.csv")
    snap.to_csv(out_csv, index=False, encoding="utf-8-sig")

    summary = {"review_date": date.today().isoformat(), "snapshot_date": str(snap_date),
               "label": label, "elapsed_days": elapsed, "markets": {}}
    for mkt, g in snap.groupby("market"):
        summary["markets"][mkt] = {
            "n": len(g),
            "avg_return_pct": round(g["return_pct"].mean(), 2),
            "median_return_pct": round(g["return_pct"].median(), 2),
            "benchmark_return_pct": round(g["benchmark_return_pct"].iloc[0], 2),
            "avg_excess_pct": round(g["excess_return_pct"].mean(), 2),
            "win_rate_absolute": round((g["return_pct"] > 0).mean() * 100, 1),
            "win_rate_vs_benchmark": round(g["beat_benchmark"].mean() * 100, 1),
            "best": g.nlargest(3, "excess_return_pct")[
                ["ticker", "name", "return_pct", "excess_return_pct"]].to_dict("records"),
            "worst": g.nsmallest(3, "excess_return_pct")[
                ["ticker", "name", "return_pct", "excess_return_pct"]].to_dict("records"),
        }
        # スコア要因との相関: 選定時スコアが高いほど実際に勝ったか（判断の質の検証材料）
        for col in ["combined_score", "technical_score", "fundamental_score"]:
            if col in g.columns and g[col].notna().sum() >= 5:
                corr = g[col].corr(g["excess_return_pct"], method="spearman")
                summary["markets"][mkt][f"rank_corr_{col}"] = round(corr, 3) if pd.notna(corr) else None

    out_json = out_csv[:-4] + ".json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    print(f"[OK] レビュー保存: {out_csv}")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
