# -*- coding: utf-8 -*-
"""選定銘柄への情報付与
picksCSVに PER・PBR・時価総額・次回決算日 を追加する。
PER/PBRはスクリーニング時のfundamental CSVを優先し、欠損はyfinanceで補完。
時価総額・次回決算日はyfinanceから取得。

使い方:
  python enrich_picks.py --picks data/work/jp_pick20.csv \
      --fundamental data/work/jp_fundamental.csv --out data/work/jp_pick20.csv
"""
import sys
import io
import argparse
import pandas as pd
import yfinance as yf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)


def fmt_mcap(v, is_jp):
    if v is None or pd.isna(v):
        return None
    if is_jp:
        return round(v / 1e8, 0)      # 億円
    return round(v / 1e9, 2)          # $B


def next_earnings(t):
    today = pd.Timestamp.now().date()
    try:
        cal = t.calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        future = [d for d in (dates or []) if d >= today]
        if future:
            return min(future).isoformat()
    except Exception:
        pass
    try:
        ed = t.get_earnings_dates(limit=8)
        if ed is not None and len(ed):
            future = ed.index[ed.index.tz_localize(None) >= pd.Timestamp.now()]
            if len(future):
                return min(future).date().isoformat()
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", required=True)
    ap.add_argument("--fundamental", help="スクリーニング時のfundamental CSV(PER/PBR取得元)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    picks = pd.read_csv(args.picks)
    fund = None
    if args.fundamental:
        fund = pd.read_csv(args.fundamental).set_index("ticker")

    rows = []
    for tk in picks["ticker"]:
        is_jp = str(tk).endswith(".T")
        per = pbr = None
        if fund is not None and tk in fund.index:
            per = fund.at[tk, "per"] if "per" in fund.columns else None
            pbr = fund.at[tk, "pbr"] if "pbr" in fund.columns else None
        mcap = earn = None
        try:
            t = yf.Ticker(tk)
            info = t.info or {}
            mcap = fmt_mcap(info.get("marketCap"), is_jp)
            if per is None or pd.isna(per):
                per = info.get("trailingPE")
            if pbr is None or pd.isna(pbr):
                pbr = info.get("priceToBook")
            earn = next_earnings(t)
        except Exception as e:
            print(f"[WARN] {tk}: {e}", file=sys.stderr)
        # 負のPER/PBR(赤字・債務超過)は指標として無意味なので欠損扱い
        if per is not None and not pd.isna(per) and per <= 0:
            per = None
        if pbr is not None and not pd.isna(pbr) and pbr <= 0:
            pbr = None
        rows.append({"ticker": tk,
                     "per": round(per, 1) if per is not None and not pd.isna(per) else None,
                     "pbr": round(pbr, 2) if pbr is not None and not pd.isna(pbr) else None,
                     "mcap": mcap,   # JP=億円 / US=$B
                     "next_earnings": earn})
        print(f"[OK] {tk} PER={rows[-1]['per']} PBR={rows[-1]['pbr']} "
              f"時価総額={mcap} 次回決算={earn}")

    extra = pd.DataFrame(rows).set_index("ticker")
    picks = picks.set_index("ticker")
    for c in extra.columns:
        picks[c] = extra[c]
    picks.reset_index().to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[OK] 保存: {args.out}")


if __name__ == "__main__":
    main()
