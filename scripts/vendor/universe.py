# -*- coding: utf-8 -*-
"""母集団（ユニバース）リスト取得
使い方:
  python universe.py --market jp --out jp_universe.csv
  python universe.py --market us --out us_universe.csv

JP: J-Quants /equities/master (v2) から全上場銘柄を取得し、商品区分コード(ProdCat)で
    内国株券(011)のみに絞る（ETF/REIT/外国株等を除外、実質フルユニバース、~3900銘柄）。
    要 JQUANTS_API_KEY 環境変数（ダッシュボード > 設定 > APIキー で発行）。
US: Wikipedia の S&P500 + S&P400(MidCap) + S&P600(SmallCap) 構成銘柄表を統合した
    S&P Composite 1500 を母集団として使う（Russell1000相当・無料で安定取得できる代替）。
"""
import sys
import io
import argparse
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

DOMESTIC_STOCK_PRODCAT = "011"  # 内国株券（ETF=014, REIT=013, 外国株=021等を除外）

WIKI_TABLES = {
    "S&P500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "S&P400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "S&P600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
}


def fetch_jp():
    from jquants_client import get_paginated, JQuantsError

    try:
        rows = get_paginated("/equities/master")
    except JQuantsError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(rows)
    if df.empty:
        print("[ERROR] J-Quantsから銘柄が0件しか取得できませんでした。契約プランを確認してください。", file=sys.stderr)
        sys.exit(1)

    df = df[df["ProdCat"] == DOMESTIC_STOCK_PRODCAT].copy()
    # TOKYO PRO MARKETはプロ投資家向け(適格機関投資家等特例業務)で流動性が低く一般的な
    # スクリーニング対象になじまないため除外。プライム/スタンダード/グロースのみ残す。
    df = df[df["MktNm"] != "TOKYO PRO MARKET"].copy()

    out = pd.DataFrame({
        "ticker": df["Code"].astype(str),
        "name": df["CoName"],
        "market": df["MktNm"],
        "sector33": df.get("S33Nm"),
        "scale": df.get("ScaleCat"),
    })
    # J-Quantsの銘柄コードは5桁(末尾0埋め)。yfinanceの.Tティッカーは先頭4桁を使う。
    out["ticker"] = out["ticker"].str[:4] + ".T"
    out = out.drop_duplicates(subset="ticker")
    return out


def fetch_us():
    frames = []
    for idx_name, url in WIKI_TABLES.items():
        try:
            tables = pd.read_html(url, storage_options={"User-Agent": "Mozilla/5.0"})
        except Exception as e:
            print(f"[WARN] {idx_name} 取得失敗、スキップ: {e}", file=sys.stderr)
            continue
        df = tables[0]
        sym_col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        name_col = "Security" if "Security" in df.columns else df.columns[1]
        sector_col = "GICS Sector" if "GICS Sector" in df.columns else None
        frame = pd.DataFrame({
            "ticker": df[sym_col].astype(str).str.replace(".", "-", regex=False),
            "name": df[name_col],
            "sector": df[sector_col] if sector_col else None,
            "index": idx_name,
        })
        frames.append(frame)

    if not frames:
        print("[ERROR] S&P500/400/600 いずれも取得できませんでした。ネットワーク接続を確認してください。", file=sys.stderr)
        sys.exit(1)

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset="ticker")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["jp", "us"], required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.market == "jp":
        df = fetch_jp()
        out_path = args.out or "jp_universe.csv"
    else:
        df = fetch_us()
        out_path = args.out or "us_universe.csv"

    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[OK] {args.market} universe: {len(df)}銘柄 → {out_path}")


if __name__ == "__main__":
    main()
