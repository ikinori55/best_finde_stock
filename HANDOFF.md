# 引き継ぎメモ（別アカウント/別セッション向け）

最終更新: 2026-07-05

このファイルは、会話を別アカウントで継続するための引き継ぎ資料。
まずこれと `CLAUDE.md` `METHOD.md` を読めば現状に追いつける。

## これまでに実装・実行済みのこと（完了）

1. **システム構築完了**（日米株「儲かる銘柄」選定→答え合わせ→手法改訂サイクル）
   - `METHOD.md`（現行 **v1.1**）: 投資分析方法の正典。テクニカル軸50%（GC+モメンタム+52週高値圏+RSI帯域+流動性）×ファンダ軸50%（ROE/利益率/自己資本/PER/PBRのパーセンタイル）
   - `LESSONS.md`: 教訓ノート（まだレビュー実績なし）
   - `CLAUDE.md`: プロジェクト運用ルール
   - スキル2つ: `.claude/skills/best-five/`（選定）、`.claude/skills/answer-check/`（答え合わせ+改訂）
   - サブエージェント3つ: `.claude/agents/` に candidate-analyst(Sonnet,赤信号)/loss-analyst(Sonnet,敗因)/method-auditor(Opus,改訂監査)
   - `scripts/check_due.py`（SessionStartフックで期日到来レビューを通知。`.claude/settings.json`に登録済み）
   - `scripts/enrich_picks.py`（PER/PBR/時価総額/次回決算日を付与）

2. **v1.0→v1.1改訂**: ユーザー指示で選定数を各市場 **5→20銘柄** に拡大（候補プール40、セクター上限4、4指標付与を追加）。改訂履歴はMETHOD.md末尾に記録済み。

3. **2026-07-05に20+20銘柄を選定・記録済み**
   - スナップショット: `data/snapshots/snapshot_20260705.csv/.json`（選定時終値・ベンチマーク固定済み）
   - 根拠表: `reports/picks_20260705.md`（全40銘柄のPER/PBR/時価総額/次回決算日入り）
   - US除外4: DUOL/PM/EBAY/KHC（赤信号）。JP入替3: あさひ/丸大食品/東映→因幡電機/ライト工業/おきなわFG
   - **答え合わせ予定日: 7d=2026-07-12 / 30d=2026-08-04 / 90d=2026-10-03**（この日以降に開くと check_due が自動で促す）

## クラウド簡易版（iPhone Claudeアプリ対応）— 2026-07-05 実装完了

ユーザーの決定: iPhoneの**Claudeアプリ**（Claude Code Cloudではなく通常アプリ）で動く簡易版とし、
APIキーはGitHubリポジトリ（のSecrets）に保存する方式。別アカウントのClaudeアプリからも閲覧したい。

実装したアーキテクチャ:
- **GitHub Actions**（`.github/workflows/pipeline.yml`、毎朝08:00 JST）が `scripts/daily_job.py` を実行:
  期日到来の答え合わせを自動実行 + 土曜に週次選定（機械選定: スコア上位20/セクター上限4、
  `finalize_picks.py`）+ `make_dashboard.py` で `docs/index.html`（GitHub Pages）と
  `docs/latest.json` を再生成 → 結果をコミット
- **iPhone Claudeアプリ**（両アカウント共通）: `CLAUDE_APP_PROMPT.md` のプロンプトを貼ると
  「儲かる株は？」でlatest.jsonを取得して表提示、「◯◯の悪材料調べて」でWeb検索の赤信号チェック
- 簡易版の制約: LLMサブエージェントの赤信号自動除外なし（アプリ上で対話補完）、
  METHOD.md改訂ガバナンスはPC版のみ
- vendorスクリプト: `scripts/vendor/`（stock-screenerから移植、review.pyはJSON出力追加パッチ済み）
- 状態管理: `data/state.json`（gitのmtimeが使えないため日付を明示管理）

**ユーザーに残っている手動3ステップ（README.md「セットアップ」参照）**:
1. GitHubでPublicリポジトリ作成 → `git remote add origin ...` → `git push -u origin main`
2. Settings→Secrets→Actions に `JQUANTS_API_KEY` / `JQUANTS_MAIL` / `JQUANTS_PASSWORD` を登録
3. Settings→Pages で main の /docs を公開 + Actionsタブで初回 Run workflow

→ **次セッションは「push完了したか」の確認から再開**。完了していればActionsの初回実行ログ確認と
CLAUDE_APP_PROMPT.md の `<USER>/<REPO>` 置換を手伝う。

## 環境メモ
- Python 3.10.11 / yfinance 1.4.1（このPC）
- 環境変数 `JQUANTS_API_KEY` 設定済み（このPCのみ。クラウドには別途登録が必要）
- 共有スクリプト実体: `C:\Users\iki_n\.claude\skills\stock-screener\scripts\`
