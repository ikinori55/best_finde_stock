# -*- coding: utf-8 -*-
"""期日到来レビューの検出（SessionStartフック用）
data/snapshots/ の snapshot_*.json を走査し、7/30/90/180日レビューのうち
「期日到来かつ未実施」のものを一覧表示する。出力はセッション開始時の文脈に注入される。
"""
import sys
import io
import os
import re
import json
import glob
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP_DIR = os.path.join(BASE, "data", "snapshots")


def main():
    metas = sorted(m for m in glob.glob(os.path.join(SNAP_DIR, "snapshot_*.json"))
                   if re.fullmatch(r"snapshot_\d{8}\.json", os.path.basename(m)))
    if not metas:
        print("[best_finde_stock] スナップショットなし。銘柄選定がまだ実行されていません。")
        return

    today = date.today()
    due, done, future = [], [], []
    for mp in metas:
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)
        stem = os.path.splitext(os.path.basename(mp))[0]
        for label, d in sorted(meta.get("review_due", {}).items(),
                               key=lambda kv: kv[1]):
            due_date = date.fromisoformat(d)
            reviewed = glob.glob(os.path.join(SNAP_DIR, f"{stem}_review_{label}_*.csv"))
            item = f"{stem} の {label} レビュー（期日 {d}）"
            if reviewed:
                done.append(item)
            elif due_date <= today:
                due.append(item)
            else:
                future.append((due_date, item))

    if due:
        print("[best_finde_stock] ★要答え合わせ★ 以下のレビューが期日到来・未実施です。")
        print("ユーザーの依頼より先に answer-check スキルを実行してください:")
        for x in due:
            print(f"  - {x}")
    else:
        print("[best_finde_stock] 期日到来の未実施レビューはありません。")
        if future:
            nd, ni = min(future, key=lambda t: t[0])
            print(f"  次回予定: {ni}")
    if done:
        print(f"  実施済みレビュー: {len(done)}件")


if __name__ == "__main__":
    main()
