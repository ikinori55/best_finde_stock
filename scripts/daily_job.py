# -*- coding: utf-8 -*-
"""クラウド簡易版オーケストレータ（GitHub Actionsから毎朝08:00 JSTに実行）
やること:
  1. 期日到来した答え合わせ（7/30/90/180日）を自動実行 → review CSV/JSON保存
  2. 週次（土曜、または前回選定から8日以上経過）でスクリーニング→20+20選定→スナップショット
  3. ダッシュボード（docs/index.html, docs/latest.json）を再生成
状態は data/state.json で管理（gitのファイル日付はcheckoutで壊れるため使わない）。

ローカル確認用: python scripts/daily_job.py --dry-run  （何をするかの表示のみ）
"""
import sys
import io
import os
import re
import json
import glob
import argparse
import subprocess
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(BASE, "scripts", "vendor")
WORK = os.path.join(BASE, "data", "work")
SNAP = os.path.join(BASE, "data", "snapshots")
STATE_PATH = os.path.join(BASE, "data", "state.json")

UNIVERSE_MAX_AGE = 30    # 日
FUNDAMENTAL_MAX_AGE = 90
PICK_INTERVAL = 7        # 週次
PICK_FALLBACK_AGE = 8    # 土曜実行を逃した場合の保険


def run(script, *args, cwd=BASE):
    cmd = [sys.executable, script, *args]
    print(f"[RUN] {' '.join(os.path.basename(str(a)) for a in cmd[1:])}")
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(f"failed: {script} (exit {r.returncode})")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def age_days(state, key, today):
    if key not in state:
        return 10 ** 6
    return (today - date.fromisoformat(state[key])).days


def due_reviews(today):
    """期日到来かつ未実施の (snapshot_csv, label) を列挙"""
    out = []
    metas = sorted(m for m in glob.glob(os.path.join(SNAP, "snapshot_*.json"))
                   if re.fullmatch(r"snapshot_\d{8}\.json", os.path.basename(m)))
    for mp in metas:
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)
        stem = os.path.splitext(os.path.basename(mp))[0]
        for label, d in meta.get("review_due", {}).items():
            if date.fromisoformat(d) <= today and not glob.glob(
                    os.path.join(SNAP, f"{stem}_review_{label}_*.csv")):
                out.append((os.path.join(SNAP, f"{stem}.csv"), label))
    return out


def refresh_picks(state, today):
    """スクリーニング→機械的20+20確定→情報付与→スナップショット→根拠表"""
    if age_days(state, "universe", today) > UNIVERSE_MAX_AGE:
        for m in ("jp", "us"):
            run(os.path.join(VENDOR, "universe.py"), "--market", m,
                "--out", os.path.join(WORK, f"{m}_universe.csv"))
        state["universe"] = today.isoformat()

    turnover = {"jp": "100000000", "us": "5000000"}
    for m in ("jp", "us"):
        run(os.path.join(VENDOR, "technical_screen.py"),
            "--universe", os.path.join(WORK, f"{m}_universe.csv"),
            "--out", os.path.join(WORK, f"{m}_technical.csv"),
            "--top", "150", "--min-turnover", turnover[m])
    state["technical"] = today.isoformat()

    if age_days(state, "fundamental", today) > FUNDAMENTAL_MAX_AGE:
        run(os.path.join(VENDOR, "fundamental_screen.py"), "--market", "jp",
            "--universe", os.path.join(WORK, "jp_universe.csv"),
            "--out", os.path.join(WORK, "jp_fundamental.csv"),
            "--cache", os.path.join(WORK, "jp_fins_raw.csv"))
        run(os.path.join(VENDOR, "fundamental_screen.py"), "--market", "us",
            "--universe", os.path.join(WORK, "us_universe.csv"),
            "--out", os.path.join(WORK, "us_fundamental.csv"), "--resume")
        state["fundamental"] = today.isoformat()

    for m in ("jp", "us"):
        run(os.path.join(VENDOR, "merge_candidates.py"),
            "--technical", os.path.join(WORK, f"{m}_technical.csv"),
            "--fundamental", os.path.join(WORK, f"{m}_fundamental.csv"),
            "--out", os.path.join(WORK, f"{m}_merged40.csv"), "--top", "40")
        run(os.path.join(BASE, "scripts", "finalize_picks.py"),
            "--merged", os.path.join(WORK, f"{m}_merged40.csv"),
            "--out", os.path.join(WORK, f"{m}_pick20.csv"))
        run(os.path.join(BASE, "scripts", "enrich_picks.py"),
            "--picks", os.path.join(WORK, f"{m}_pick20.csv"),
            "--fundamental", os.path.join(WORK, f"{m}_fundamental.csv"),
            "--out", os.path.join(WORK, f"{m}_pick20.csv"))

    run(os.path.join(VENDOR, "snapshot.py"),
        "--picks", os.path.join(WORK, "jp_pick20.csv"), os.path.join(WORK, "us_pick20.csv"),
        "--outdir", SNAP,
        "--note", "クラウド簡易版: 機械選定(スコア上位20/セクター上限4)。赤信号チェックはClaudeアプリで対話実施。")

    for m in ("jp", "us"):
        run(os.path.join(VENDOR, "rationale.py"),
            "--final", os.path.join(WORK, f"{m}_pick20.csv"),
            "--technical", os.path.join(WORK, f"{m}_technical.csv"),
            "--fundamental", os.path.join(WORK, f"{m}_fundamental.csv"),
            "--market", m,
            "--out", os.path.join(BASE, "reports",
                                  f"{m}_rationale_{today.strftime('%Y%m%d')}.md"))
    state["last_pick"] = today.isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-pick", action="store_true", help="週次判定を無視して選定を実行")
    args = ap.parse_args()

    today = date.today()
    state = load_state()

    reviews = due_reviews(today)
    pick_needed = (args.force_pick or
                   today.weekday() == 5 and age_days(state, "last_pick", today) >= PICK_INTERVAL or
                   age_days(state, "last_pick", today) >= PICK_FALLBACK_AGE)

    print(f"[PLAN] {today} 要レビュー={len(reviews)}件 選定更新={'する' if pick_needed else 'しない'}")
    for csv_path, label in reviews:
        print(f"  - review: {os.path.basename(csv_path)} {label}")
    if args.dry_run:
        return

    for csv_path, label in reviews:
        run(os.path.join(VENDOR, "review.py"), "--snapshot", csv_path, "--label", label)

    if pick_needed:
        refresh_picks(state, today)

    run(os.path.join(BASE, "scripts", "make_dashboard.py"))
    save_state(state)
    print("[DONE] daily_job 完了")


if __name__ == "__main__":
    main()
