# -*- coding: utf-8 -*-
"""選定根拠の簡易表を生成（毎サイクル必須の成果物）
final20（merge_candidates.py→セクター上限適用後）にテクニカル/ファンダの詳細指標を結合し、
「なぜこの銘柄が選ばれたか」を1銘柄1行のMarkdown表にする。答え合わせ時に
「選定時に何を見ていたか」を振り返る一次資料にもなる。

使い方:
  python rationale.py --final jp_final20.csv --technical jp_technical.csv \
      --fundamental jp_fundamental.csv --market jp --out jp_rationale.md
"""
import sys
import io
import argparse
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)


def _fmt(v, pct=False, digits=1):
    if v is None or pd.isna(v):
        return "—"
    return f"{v*100:.{digits}f}%" if pct else f"{v:.{digits}f}"


def tech_evidence(row):
    parts = []
    if row.get("gc_recent"):
        parts.append("GC直後")
    elif row.get("trend_aligned"):
        parts.append("上昇配列")
    ret20 = row.get("ret20")
    if pd.notna(ret20):
        parts.append(f"20日{ret20:+.1f}%")
    d52 = row.get("pct_from_52w_high")
    if pd.notna(d52) and d52 >= -10:
        parts.append("52週高値圏")
    rsi = row.get("rsi")
    if pd.notna(rsi) and 50 <= rsi <= 70:
        parts.append(f"RSI適温{rsi:.0f}")
    elif pd.notna(rsi):
        parts.append(f"RSI{rsi:.0f}")
    return "・".join(parts) if parts else "—"


def fund_evidence(row, market):
    parts = []
    roe = row.get("roe")
    if pd.notna(roe):
        parts.append(f"ROE{roe*100:.0f}%")
    if market == "jp":
        opm = row.get("op_margin")
        if pd.notna(opm) and opm >= 0.10:
            parts.append(f"営利率{opm*100:.0f}%")
        eqr = row.get("equity_ratio")
        if pd.notna(eqr) and eqr >= 0.5:
            parts.append(f"自己資本{eqr*100:.0f}%")
    else:
        rg = row.get("revenue_growth")
        if pd.notna(rg) and rg > 0:
            parts.append(f"増収{rg*100:.0f}%")
        eg = row.get("earnings_growth")
        if pd.notna(eg) and eg > 0:
            parts.append(f"増益{eg*100:.0f}%")
    per = row.get("per")
    if pd.notna(per):
        parts.append(f"PER{per:.1f}")
    pbr = row.get("pbr")
    if pd.notna(pbr) and 0 < pbr < 1.5:
        parts.append(f"PBR{pbr:.2f}")
    return "・".join(parts) if parts else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", required=True)
    ap.add_argument("--technical", required=True)
    ap.add_argument("--fundamental", required=True)
    ap.add_argument("--market", choices=["jp", "us"], required=True)
    ap.add_argument("--out", default=None, help="Markdown出力先(省略時は標準出力のみ)")
    args = ap.parse_args()

    final = pd.read_csv(args.final)
    tech = pd.read_csv(args.technical).set_index("ticker")
    fund = pd.read_csv(args.fundamental).set_index("ticker")

    lines = [
        f"# スクリーニング選定根拠（{args.market.upper()} / {len(final)}銘柄）",
        "",
        "| # | 銘柄 | セクター | 総合 | 技/財 | テクニカル根拠 | ファンダ根拠 |",
        "|---|------|----------|------|-------|----------------|--------------|",
    ]
    for i, row in final.reset_index(drop=True).iterrows():
        t = row["ticker"]
        trow = tech.loc[t] if t in tech.index else pd.Series(dtype=object)
        frow = fund.loc[t] if t in fund.index else pd.Series(dtype=object)
        name = row.get("name") or trow.get("name") or t
        lines.append(
            f"| {i+1} | {name} ({t}) | {row.get('sector', '—')} "
            f"| {row['combined_score']:.1f} "
            f"| {row['technical_score']:.0f}/{row['fundamental_score']:.0f} "
            f"| {tech_evidence(trow)} | {fund_evidence(frow, args.market)} |"
        )
    lines += [
        "",
        "凡例: 総合=技術50%+財務50%の加重。技/財=各軸スコア(技術は実測配点0-100、財務は母集団内",
        "パーセンタイル)。テクニカル根拠はchart-analysis Tier1条件、ファンダ根拠は目立つ強みのみ表示。",
    ]

    md = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"[OK] {args.out} に保存", file=sys.stderr)
    print(md)


if __name__ == "__main__":
    main()
