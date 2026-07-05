# -*- coding: utf-8 -*-
"""テクニカル一括スクリーニング
universe.py の出力(CSV, ticker列必須)を受け取り、yfinanceで一括取得したOHLCVから
chart-analysisスキルのTier1実測条件（GC+モメンタム+52週高値圏+RSI帯域）でスコアリングする。

使い方:
  python technical_screen.py --universe jp_universe.csv --out jp_technical.csv --top 80
  python technical_screen.py --universe us_universe.csv --out us_technical.csv --top 80

スコア配分の根拠は chart-analysis スキル (references/patterns.md) の実測値:
  GC発生(直近10営業日以内)          +40
  直近20日リターン>0(モメンタム)     +20  ※層別分析で最重要フィルターと確認済み
  52週高値比 -10%以内                +15
  RSI 50〜70(適温ゾーン)             +15
  GC日の出来高が過熱していない       +10  ※低出来高GCの方が安定という実測に基づく
  (GC無しでも5>25>75の並びなら)      +20  ※継続中の強トレンドを拾う代替パス
禁忌条件（大きく減点）:
  直近20日リターン<-10%(崩落中)      -30
  75日線が下向き(下降トレンド中)     -20
"""
import sys
import io
import time
import argparse
import numpy as np
import pandas as pd
import yfinance as yf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

CHUNK_SIZE = 150
CHUNK_SLEEP_SEC = 2


def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - (100 / (1 + g / l))


def score_one(close, volume):
    if len(close) < 210:
        return None  # 上場間もない・データ不足はスコア対象外

    # 20日平均売買代金(現地通貨)。流動性が無い銘柄は約定コストが高くスコアが良くても実運用不可
    turnover20 = float((close.tail(20) * volume.tail(20)).mean())

    ma5 = close.rolling(5).mean()
    ma25 = close.rolling(25).mean()
    ma75 = close.rolling(75).mean()
    r = rsi(close, 14)

    gc_series = (ma5 > ma25).astype(int).diff()
    recent_gc_idx = gc_series.tail(10)
    gc_recent = bool((recent_gc_idx == 1).any())

    ret20 = close.iloc[-1] / close.iloc[-21] - 1
    window = close.tail(252)
    pct_from_52w_high = close.iloc[-1] / window.max() - 1
    ma75_slope_up = bool(ma75.iloc[-1] > ma75.iloc[-11])
    trend_aligned = bool(ma5.iloc[-1] > ma25.iloc[-1] > ma75.iloc[-1])
    rsi_last = float(r.iloc[-1]) if not np.isnan(r.iloc[-1]) else None

    vol_ratio = None
    if gc_recent:
        gc_days = recent_gc_idx[recent_gc_idx == 1].index
        if len(gc_days) > 0:
            gc_day = gc_days[-1]
            pos = close.index.get_loc(gc_day)
            if pos >= 20:
                base_vol = volume.iloc[pos - 20:pos].mean()
                gc_vol = volume.iloc[pos]
                if base_vol > 0:
                    vol_ratio = float(gc_vol / base_vol)

    score = 0
    if gc_recent:
        score += 40
    elif trend_aligned:
        score += 20
    if ret20 > 0:
        score += 20
    if pct_from_52w_high >= -0.10:
        score += 15
    if rsi_last is not None and 50 <= rsi_last <= 70:
        score += 15
    if vol_ratio is not None and vol_ratio < 1.3:
        score += 10
    if ret20 < -0.10:
        score -= 30
    if not ma75_slope_up:
        score -= 20
    score = max(0, min(100, score))

    return {
        "score": score,
        "gc_recent": gc_recent,
        "trend_aligned": trend_aligned,
        "rsi": round(rsi_last, 1) if rsi_last is not None else None,
        "ret20": round(float(ret20) * 100, 1),
        "pct_from_52w_high": round(float(pct_from_52w_high) * 100, 1),
        "vol_ratio_on_gc": round(vol_ratio, 2) if vol_ratio is not None else None,
        "close": round(float(close.iloc[-1]), 2),
        "turnover20": round(turnover20),
    }


def download_chunk(tickers, period="2y"):
    for attempt in range(2):
        try:
            return yf.download(
                tickers=tickers, period=period, group_by="ticker",
                threads=True, progress=False, auto_adjust=True,
            )
        except Exception as e:
            if attempt == 0:
                time.sleep(5)
                continue
            print(f"[WARN] チャンクDL失敗、スキップ: {e}", file=sys.stderr)
            return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=0, help="0なら全件出力")
    ap.add_argument("--period", default="2y")
    ap.add_argument("--min-turnover", type=float, default=0,
                    help="20日平均売買代金の下限(現地通貨)。目安: 日本株1e8(1億円)、米国株5e6($5M)。0で無効")
    args = ap.parse_args()

    uni = pd.read_csv(args.universe)
    tickers = uni["ticker"].dropna().unique().tolist()
    print(f"[INFO] 対象銘柄数: {len(tickers)}", file=sys.stderr)

    rows = []
    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i:i + CHUNK_SIZE]
        print(f"[INFO] {i}〜{i+len(chunk)}/{len(tickers)} 取得中...", file=sys.stderr)
        data = download_chunk(chunk, args.period)
        if data is None:
            continue
        for t in chunk:
            try:
                sub = data[t] if len(chunk) > 1 else data
                close = sub["Close"].dropna()
                volume = sub["Volume"].reindex(close.index).fillna(0)
                result = score_one(close, volume)
            except (KeyError, IndexError):
                result = None
            if result:
                result["ticker"] = t
                rows.append(result)
        if i + CHUNK_SIZE < len(tickers):
            time.sleep(CHUNK_SLEEP_SEC)

    if not rows:
        print("[ERROR] スコア算出できた銘柄が0件でした。", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(rows).merge(uni, on="ticker", how="left")
    if args.min_turnover > 0:
        before = len(df)
        df = df[df["turnover20"] >= args.min_turnover]
        print(f"[INFO] 流動性フィルター: {before}→{len(df)}銘柄 (売買代金>={args.min_turnover:,.0f})",
              file=sys.stderr)
    df = df.sort_values("score", ascending=False)
    if args.top > 0:
        df = df.head(args.top)

    cols = ["ticker", "name", "score", "gc_recent", "trend_aligned", "rsi",
            "ret20", "pct_from_52w_high", "vol_ratio_on_gc", "close", "turnover20",
            "sector33", "sector", "market", "scale", "index"]
    cols = [c for c in cols if c in df.columns]
    df[cols].to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[OK] {len(rows)}銘柄採点 → 上位{len(df)}件を {args.out} に出力")


if __name__ == "__main__":
    main()
