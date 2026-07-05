# Stock Judge — 日米「儲かる20銘柄」選定＆答え合わせ（クラウド簡易版対応）

日本株・米国株から各20銘柄を選定し、7/30/90/180日後に自動で答え合わせするシステム。

- **フル版**: PCのClaude Codeで動作（サブエージェントによる赤信号チェック・手法改訂ガバナンス込み）。`CLAUDE.md` 参照。
- **クラウド簡易版**: GitHub Actionsが毎朝08:00 JSTに自動実行し、結果を `docs/`（GitHub Pages）に公開。
  iPhoneのClaudeアプリ（どのアカウントからでも）で結果を読んで対話分析できる。

## クラウド簡易版のアーキテクチャ

```
GitHub Actions (毎朝08:00 JST, .github/workflows/pipeline.yml)
  └ scripts/daily_job.py
      ├ 期日到来の答え合わせを自動実行（review CSV/JSON → data/snapshots/）
      ├ 土曜: スクリーニング→機械選定20+20→PER/PBR/時価総額/決算日付与→スナップショット
      └ scripts/make_dashboard.py → docs/index.html + docs/latest.json を再生成
  └ 結果をコミット（リポジトリが記録媒体）

iPhone Claudeアプリ（全アカウント共通・読み取り）
  ├ Safari: https://<USER>.github.io/<REPO>/          … ダッシュボード閲覧
  └ Claudeアプリ: CLAUDE_APP_PROMPT.md のプロンプトを貼る
      → 「儲かる株は？」で latest.json を取得して表提示
      → 「◯◯の悪材料調べて」で赤信号チェック（Web検索）を対話実行
```

フル版との違い（簡易版の制約）:
- 選定は**スコア機械選定**（上位20+セクター上限4）。サブエージェントの赤信号除外なし
  → 代わりにClaudeアプリ上で対話的にニュース確認する
- METHOD.mdの改訂ガバナンス（教訓2回再現+監査）はPC版でのみ実施

## セットアップ（初回のみ・PC側3ステップ）

### 1. GitHubに公開リポジトリを作成してpush
GitHub上で新規リポジトリ（**Public**・README等は追加しない）を作成後:
```
cd best_finde_stock
git remote add origin https://github.com/<USER>/<REPO>.git
git push -u origin main
```
> Publicにする理由: 別アカウントのClaudeアプリやSafariがログインなしで
> `raw.githubusercontent.com` / GitHub Pages を読めるようにするため。
> 銘柄リスト・スコアのみでキーや個人情報は含まれない。

### 2. APIキーをリポジトリのSecretsに保存
リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で3つ登録:
- `JQUANTS_API_KEY`
- `JQUANTS_MAIL`
- `JQUANTS_PASSWORD`

> ⚠️ キーはこの方式（リポジトリのSecrets）で保存する。**コードや.envとしてのコミットは厳禁**
> （Publicリポジトリでは世界中に公開されてしまう）。Secretsは暗号化保管され、Actionsの実行時のみ注入される。

### 3. PagesとActionsを有効化
- **Settings → Pages** → Source: `Deploy from a branch` / Branch: `main` / Folder: `/docs`
- **Actionsタブ** → workflowを有効化 → `stock-judge-pipeline` を **Run workflow**（初回手動実行、`force_pick`は既存スナップショットがあるためオフでよい）

## iPhoneでの使い方

- **ダッシュボード**: Safariで `https://<USER>.github.io/<REPO>/` を開く（ホーム画面に追加推奨）
- **Claudeアプリ**（両アカウント共通）: `CLAUDE_APP_PROMPT.md` の内容を新規プロジェクトの指示
  （またはチャット冒頭）に貼り付けて使う。「儲かる株は？」「答え合わせの結果は？」
  「マニーの悪材料を調べて」などがそのまま動く。

## ファイル構成

| パス | 役割 |
|---|---|
| `METHOD.md` / `LESSONS.md` | 投資分析方法の正典（バージョン管理）/ 教訓ノート |
| `scripts/daily_job.py` | クラウド用オーケストレータ（レビュー→選定→ダッシュボード） |
| `scripts/vendor/` | スクリーニング計算スクリプト一式（universe/technical/fundamental/merge/snapshot/review/rationale） |
| `scripts/finalize_picks.py` | 機械選定（上位20・セクター上限4） |
| `scripts/enrich_picks.py` | PER/PBR/時価総額/次回決算日の付与 |
| `scripts/make_dashboard.py` | docs/index.html + docs/latest.json 生成 |
| `scripts/check_due.py` | （PC版）セッション開始時の期日通知 |
| `data/snapshots/` | 選定スナップショット+レビュー結果（答え合わせの根拠。コミット対象） |
| `data/state.json` | クラウド実行の状態（各データの最終更新日） |
| `docs/` | 公開ダッシュボード（GitHub Pages） |
| `CLAUDE_APP_PROMPT.md` | iPhoneのClaudeアプリに貼るプロンプト |

## 免責
本システムはシグナル生成・記録・検証のみを行う。売買判断・結果は利用者の自己責任。
