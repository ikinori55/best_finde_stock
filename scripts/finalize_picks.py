# -*- coding: utf-8 -*-
"""機械的な最終選定（クラウド簡易版）
merged40（統合ランキング上位40）から、セクター上限4銘柄のルールで上位20を機械的に確定する。
LLMによる赤信号チェック・入替はクラウドでは行わない（Claudeアプリ上で対話的に行う）。

使い方:
  python finalize_picks.py --merged data/work/jp_merged40.csv --out data/work/jp_pick20.csv
"""
import sys
import io
import argparse
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

TOP_N = 20
SECTOR_CAP = 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=TOP_N)
    ap.add_argument("--sector-cap", type=int, default=SECTOR_CAP)
    args = ap.parse_args()

    df = pd.read_csv(args.merged).sort_values("combined_score", ascending=False)
    picked, counts = [], {}
    for _, row in df.iterrows():
        sec = row.get("sector", "unknown")
        if counts.get(sec, 0) >= args.sector_cap:
            continue
        picked.append(row)
        counts[sec] = counts.get(sec, 0) + 1
        if len(picked) >= args.top:
            break

    out = pd.DataFrame(picked)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[OK] {len(out)}銘柄確定 → {args.out}")
    print(out.groupby("sector").size().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    main()
