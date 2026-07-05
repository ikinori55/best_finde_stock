# -*- coding: utf-8 -*-
"""選定スナップショット記録（答え合わせの起点）
merge_candidates.py の最終候補リストを「その日の判断」として固定記録する。
記録するもの: 選定日・銘柄・各スコア・選定時終値・ベンチマーク終値・検証予定日(7/30/90/180日後)。
review.py がこのスナップショットを読んで答え合わせする。

使い方:
  python snapshot.py --picks jp_final.csv us_final.csv --outdir data/snapshots \
      --note "初回スクリーニング"
出力: <outdir>/snapshot_YYYYMMDD.csv と同名.json(メタ情報)
"""
import sys
import io
import os
import json
import argparse
from datetime import date, timedelta
import pandas as pd
import yfinance as yf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

BENCHMARKS = {"jp": "^N225", "us": "^GSPC"}
HORIZONS = [7, 30, 90, 180]


def market_of(ticker):
    return "jp" if str(ticker).endswith(".T") else "us"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", nargs="+", required=True, help="merge_candidates.py出力CSV(複数可)")
    ap.add_argument("--outdir", default="snapshots")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    frames = []
    for p in args.picks:
        df = pd.read_csv(p)
        df["source_file"] = os.path.basename(p)
        frames.append(df)
    picks = pd.concat(frames, ignore_index=True).drop_duplicates(subset="ticker")
    picks["market"] = picks["ticker"].map(market_of)

    today = date.today()
    print(f"[INFO] {len(picks)}銘柄+ベンチマークの終値取得中...", file=sys.stderr)
    closes = fetch_closes(picks["ticker"].tolist())
    picks["entry_close"] = picks["ticker"].map(closes)

    bench_closes = fetch_closes(list(BENCHMARKS.values()))
    picks["benchmark"] = picks["market"].map(BENCHMARKS)
    picks["benchmark_entry_close"] = picks["benchmark"].map(bench_closes)

    picks["snapshot_date"] = today.isoformat()
    missing = picks["entry_close"].isna().sum()
    if missing:
        print(f"[WARN] {missing}銘柄で終値が取得できませんでした（レビュー時に除外されます）",
              file=sys.stderr)

    os.makedirs(args.outdir, exist_ok=True)
    stem = f"snapshot_{today.strftime('%Y%m%d')}"
    csv_path = os.path.join(args.outdir, f"{stem}.csv")
    picks.to_csv(csv_path, index=False, encoding="utf-8-sig")

    meta = {
        "snapshot_date": today.isoformat(),
        "note": args.note,
        "n_picks": len(picks),
        "markets": picks["market"].value_counts().to_dict(),
        "review_due": {f"{h}d": (today + timedelta(days=h)).isoformat() for h in HORIZONS},
        "benchmarks": BENCHMARKS,
    }
    with open(os.path.join(args.outdir, f"{stem}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[OK] スナップショット保存: {csv_path}")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
