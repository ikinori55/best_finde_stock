# -*- coding: utf-8 -*-
"""ファンダメンタル一括スクリーニング（横断パーセンタイル方式）
universe.py の出力(CSV, ticker列必須)を受け取り、母集団内での相対評価でスコアリングする。
固定の閾値(例: ROE>10%)ではなく、その時点の母集団内での順位(percentile)で採点するため、
相場全体の水準が変わっても常に「相対的に良い銘柄」を抽出できる。

JP: J-Quants /fins/summary (v2) を過去N日分（既定100日）日付スイープして直近開示を銘柄ごとに1件抽出。
    ROE・営業利益率・純利益率・自己資本比率を財務諸表から算出し、直近終値(yfinance)と合わせて
    PER・PBRも算出する。
    ※Freeプランはレートリミット5req/分のため、100日スイープに約20分かかる
      （JQUANTS_RPM環境変数で有料プランのレートに合わせて高速化可能）。
    ※制約: YoY成長率は「直近開示のみ」からは算出できないため score には含めない
      （前年同期比較には複数四半期分の突合が必要で将来拡張）。
US: yfinance の Ticker.info を銘柄ごとに取得（無料APIで全銘柄横断できる公式ソースが無いための代替）。
    1500銘柄規模だと時間がかかるため ThreadPoolExecutor で並列化し、--resume で中断再開できる。

使い方:
  python fundamental_screen.py --market jp --universe jp_universe.csv --out jp_fundamental.csv
  python fundamental_screen.py --market us --universe us_universe.csv --out us_fundamental.csv --resume
"""
import sys
import io
import os
import argparse
import time
import numpy as np
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

US_CHECKPOINT_EVERY = 100


def _f(v):
    try:
        if v is None or v == "":
            return np.nan
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def fetch_jp_statements(lookback_days, cache_path=None):
    from jquants_client import get_paginated, JQuantsError

    if cache_path and os.path.exists(cache_path):
        print(f"[INFO] キャッシュ使用: {cache_path}（再スイープ省略。最新化するにはファイルを削除）",
              file=sys.stderr)
        return pd.read_csv(cache_path, dtype=str)

    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=lookback_days)
    rows = []
    for d in dates:
        ds = d.strftime("%Y-%m-%d")
        try:
            recs = get_paginated("/fins/summary", {"date": ds})
        except JQuantsError as e:
            print(f"[WARN] {ds} 取得失敗、スキップ: {e}", file=sys.stderr)
            continue
        rows.extend(recs)
    df = pd.DataFrame(rows)
    if cache_path and not df.empty:
        df.to_csv(cache_path, index=False, encoding="utf-8-sig")
        print(f"[INFO] 生データを {cache_path} にキャッシュ（Freeプランは再スイープに~20分かかるため）",
              file=sys.stderr)
    return df


def score_jp(args):
    df = fetch_jp_statements(args.lookback_days, cache_path=args.cache)
    if df.empty:
        print("[ERROR] J-Quantsから開示データが0件でした。日付範囲や契約プランを確認してください。", file=sys.stderr)
        sys.exit(1)

    df["DiscDate"] = pd.to_datetime(df["DiscDate"])
    df = df.sort_values("DiscDate").drop_duplicates(subset="Code", keep="last")

    df["net_sales"] = df["Sales"].apply(_f)
    df["op_profit"] = df["OP"].apply(_f)
    df["profit"] = df["NP"].apply(_f)
    df["equity"] = df["Eq"].apply(_f)
    df["equity_ratio"] = df["EqAR"].apply(_f)
    df["bvps"] = df["BPS"].apply(_f)
    df["eps"] = df["EPS"].apply(_f)

    # IFRS採用企業等はBPSが空欄になるため、発行済株式数(自己株控除後)から自己算出で補完
    shares = df["ShOutFY"].apply(_f) - df["TrShFY"].apply(_f).fillna(0)
    bvps_calc = (df["equity"] / shares).where(shares > 0)
    df["bvps"] = df["bvps"].fillna(bvps_calc)

    df["roe"] = df["profit"] / df["equity"]
    df["op_margin"] = df["op_profit"] / df["net_sales"]
    df["net_margin"] = df["profit"] / df["net_sales"]

    df["ticker"] = df["Code"].astype(str).str[:4] + ".T"
    df = df.drop_duplicates(subset="ticker")

    uni_cols = [c for c in ["ticker", "name", "sector33", "market", "scale"]
                if c in pd.read_csv(args.universe, nrows=0).columns]
    uni = pd.read_csv(args.universe)[uni_cols]
    df = df.merge(uni, on="ticker", how="left")

    print(f"[INFO] 直近開示 {len(df)}銘柄。株価取得中(PER/PBR算出用)...", file=sys.stderr)
    prices = fetch_latest_prices(df["ticker"].tolist())
    df = df.merge(prices, on="ticker", how="left")
    df["per"] = df["price"] / df["eps"]
    df["pbr"] = df["price"] / df["bvps"]
    df.loc[df["eps"] <= 0, "per"] = np.nan
    df.loc[df["bvps"] <= 0, "pbr"] = np.nan

    return df


def fetch_latest_prices(tickers, chunk_size=150):
    out = []
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        try:
            data = yf.download(tickers=chunk, period="5d", group_by="ticker",
                                threads=True, progress=False, auto_adjust=True)
        except Exception as e:
            print(f"[WARN] 株価チャンク取得失敗: {e}", file=sys.stderr)
            continue
        for t in chunk:
            try:
                sub = data[t] if len(chunk) > 1 else data
                price = float(sub["Close"].dropna().iloc[-1])
                out.append({"ticker": t, "price": price})
            except (KeyError, IndexError):
                continue
        time.sleep(1)
    return pd.DataFrame(out)


def fetch_us_one(ticker):
    try:
        info = yf.Ticker(ticker).get_info()
    except Exception:
        return {"ticker": ticker}
    return {
        "ticker": ticker,
        "roe": info.get("returnOnEquity"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "per": info.get("trailingPE"),
        "pbr": info.get("priceToBook"),
        "debt_to_equity": info.get("debtToEquity"),
    }


def score_us(args):
    uni = pd.read_csv(args.universe)
    tickers = uni["ticker"].dropna().unique().tolist()
    if args.limit:
        tickers = tickers[:args.limit]

    done = {}
    if args.resume and os.path.exists(args.out):
        prev = pd.read_csv(args.out)
        done = {row["ticker"]: row.to_dict() for _, row in prev.iterrows()}
        tickers = [t for t in tickers if t not in done]
        print(f"[INFO] --resume: {len(done)}銘柄は取得済みとしてスキップ", file=sys.stderr)

    rows = list(done.values())
    print(f"[INFO] 残り{len(tickers)}銘柄をyfinanceから取得(並列8)...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_us_one, t): t for t in tickers}
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % US_CHECKPOINT_EVERY == 0:
                print(f"[INFO] {i}/{len(tickers)} 完了、中間保存...", file=sys.stderr)
                pd.DataFrame(rows).to_csv(args.out, index=False, encoding="utf-8-sig")

    df = pd.DataFrame(rows).merge(uni, on="ticker", how="left")
    return df


def add_composite_score(df, higher_better, lower_better):
    pct_cols = []
    for col in higher_better:
        if col in df.columns:
            df[f"_pct_{col}"] = df[col].rank(pct=True)
            pct_cols.append(f"_pct_{col}")
    for col in lower_better:
        if col in df.columns:
            df[f"_pct_{col}"] = 1 - df[col].rank(pct=True)
            pct_cols.append(f"_pct_{col}")
    df["score"] = (df[pct_cols].mean(axis=1, skipna=True) * 100).round(1)
    df = df.drop(columns=pct_cols)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["jp", "us"], required=True)
    ap.add_argument("--universe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=0, help="0なら全件出力")
    ap.add_argument("--lookback-days", type=int, default=100, help="JP: 開示スイープする営業日数")
    ap.add_argument("--limit", type=int, default=0, help="US: テスト用に先頭N銘柄のみ処理")
    ap.add_argument("--resume", action="store_true", help="US: 既存--outを読み既取得銘柄をスキップ")
    ap.add_argument("--cache", default=None,
                    help="JP: fins/summary生データのキャッシュCSVパス。存在すれば再スイープせず読む")
    args = ap.parse_args()

    if args.market == "jp":
        df = score_jp(args)
        df = add_composite_score(
            df,
            higher_better=["roe", "op_margin", "net_margin", "equity_ratio"],
            lower_better=["per", "pbr"],
        )
        cols = ["ticker", "name", "score", "roe", "op_margin", "net_margin",
                "equity_ratio", "per", "pbr", "price", "sector33", "market", "scale"]
    else:
        df = score_us(args)
        for c in ["roe", "revenue_growth", "earnings_growth", "per", "pbr", "debt_to_equity"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        # 純資産マイナス企業(自社株買い過多等)のPBRは負になり「低いほど良い」評価を歪めるため欠測扱い
        df.loc[df["pbr"] <= 0, "pbr"] = np.nan
        df.loc[df["per"] <= 0, "per"] = np.nan
        df = add_composite_score(
            df,
            higher_better=["roe", "revenue_growth", "earnings_growth"],
            lower_better=["per", "pbr", "debt_to_equity"],
        )
        cols = ["ticker", "name", "score", "roe", "revenue_growth", "earnings_growth",
                "per", "pbr", "debt_to_equity", "sector", "index"]

    cols = [c for c in cols if c in df.columns]
    df = df.sort_values("score", ascending=False)
    if args.top > 0:
        df = df.head(args.top)
    df[cols].to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[OK] {len(df)}銘柄 → {args.out} に出力")


if __name__ == "__main__":
    main()
