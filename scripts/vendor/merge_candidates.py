# -*- coding: utf-8 -*-
"""テクニカル軸・ファンダ軸の統合ランキング
technical_screen.py / fundamental_screen.py の出力(各scoreカラム必須)を突き合わせ、
加重合計スコアで上位N銘柄を出す。片方にしか出てこない銘柄（=もう片方のスクリーニングで
足切りされた銘柄）は既定で除外(inner)。--method union なら和集合で拾い、欠けている方は0点扱い。

使い方:
  python merge_candidates.py --technical jp_technical.csv --fundamental jp_fundamental.csv \
      --out jp_final.csv --top 20
"""
import sys
import io
import argparse
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--technical", required=True)
    ap.add_argument("--fundamental", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--w-tech", type=float, default=0.5)
    ap.add_argument("--w-fund", type=float, default=0.5)
    ap.add_argument("--method", choices=["intersect", "union"], default="intersect")
    args = ap.parse_args()

    tech_all = pd.read_csv(args.technical)
    tech_cols = ["ticker", "score"] + [c for c in ["turnover20", "gc_recent", "ret20"]
                                        if c in tech_all.columns]
    tech = tech_all[tech_cols].rename(columns={"score": "technical_score"})

    fund_all = pd.read_csv(args.fundamental)
    name_col = "name" if "name" in fund_all.columns else ("CompanyName" if "CompanyName" in fund_all.columns else None)
    sector_col = next((c for c in ["sector33", "sector"] if c in fund_all.columns), None)
    fund_cols = ["ticker", "score"] + [c for c in [name_col, sector_col] if c]
    fund = fund_all[fund_cols].rename(columns={"score": "fundamental_score"})
    if name_col:
        fund = fund.rename(columns={name_col: "name"})
    if sector_col:
        fund = fund.rename(columns={sector_col: "sector"})

    how = "inner" if args.method == "intersect" else "outer"
    df = tech.merge(fund, on="ticker", how=how)
    df["technical_score"] = df["technical_score"].fillna(0)
    df["fundamental_score"] = df["fundamental_score"].fillna(0)

    total_w = args.w_tech + args.w_fund
    df["combined_score"] = (
        df["technical_score"] * args.w_tech + df["fundamental_score"] * args.w_fund
    ) / total_w
    df = df.sort_values("combined_score", ascending=False)

    cols = ["ticker", "name", "combined_score", "technical_score", "fundamental_score",
            "sector", "turnover20", "gc_recent", "ret20"]
    cols = [c for c in cols if c in df.columns]
    out = df[cols].head(args.top)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[OK] {args.method}統合 {len(df)}銘柄中、上位{len(out)}件を {args.out} に出力")


if __name__ == "__main__":
    main()
