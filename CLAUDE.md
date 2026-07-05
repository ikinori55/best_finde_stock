# best_finde_stock — 日米株「儲かる銘柄」選定＆答え合わせシステム

日本株・米国株からそれぞれ「最も儲かる20銘柄」を選定し、7日/30日/90日後に答え合わせして
投資分析方法（METHOD.md）を継続改善するプロジェクト。

## セッション開始時の必須動作（最優先）

SessionStartフックが `scripts/check_due.py` を実行し、期日到来レビューを通知する。
**「要答え合わせ」が1件でもあれば、ユーザーの依頼に着手する前に必ず:**
1. `answer-check` スキルを実行して答え合わせ（リターン検証→敗因分析→教訓化→必要なら手法改訂）
2. 結果をユーザーへ報告してから本題に入る

## トリガーと実行スキル

| ユーザーの発話 | 実行するもの |
|---|---|
| 「儲かる株は？」「儲かる株教えて」「銘柄選んで」「有望株は？」 | `best-five` スキル（各市場20銘柄選定） |
| 「答え合わせして」「レビューして」「なぜ外れた？」 | `answer-check` スキル |
| 「手法を見直して」「METHODを改訂して」 | `answer-check` スキルの改訂パート（教訓2回再現ルール厳守） |
| 個別銘柄の深掘り | グローバル `stock-analysis` スキル |

## エージェントチーム構成（モデル割当）

| 役割 | 実行主体 | モデル | 備考 |
|---|---|---|---|
| 全体統括・最終20銘柄確定・手法改訂判断 | メインエージェント | Fable/Opus | セクター分散と赤信号の横断判断 |
| 候補の赤信号チェック（市場別に並列） | `candidate-analyst` サブエージェント | Sonnet | Web検索で決算・ニュース確認 |
| 敗因診断（ワースト銘柄ごとに並列） | `loss-analyst` サブエージェント | Sonnet | 敗因を6分類 |
| 手法改訂の監査（改訂前に必須） | `method-auditor` サブエージェント | Opus | 過剰適合を却下する敵対的レビュー |
| 指標計算・価格取得・記録 | Pythonスクリプト | LLM不使用 | 数値は必ずスクリプトで |

並列サブエージェントは1メッセージ内で同時起動する（JP/US同時、敗因診断は銘柄バッチ同時）。

## ファイル配置

- `METHOD.md` — 投資分析方法の正典（バージョン管理、改訂履歴付き）
- `LESSONS.md` — 答え合わせから得た教訓（選定前に必読）
- `data/work/` — スクリーニング中間ファイル（universe/technical/fundamental/final CSV）
- `data/snapshots/` — 選定スナップショット（snapshot_YYYYMMDD.csv/.json、review結果CSV/JSON）
- `reports/` — 選定根拠表・レビューレポート（Markdown）
- `scripts/check_due.py` — 期日到来レビューの検出（SessionStartフック）
- `scripts/enrich_picks.py` — 選定銘柄にPER・PBR・時価総額・次回決算日を付与

## 共有基盤（グローバルスキルのスクリプトを利用）

スクリーニング計算は `C:\Users\iki_n\.claude\skills\stock-screener\scripts\` を使う:
universe.py / technical_screen.py / fundamental_screen.py / merge_candidates.py /
snapshot.py / review.py / rationale.py。使い方は各スキルのSKILL.md参照。
J-Quants APIキーは環境変数 `JQUANTS_API_KEY` 設定済み。

## 鉄の掟

1. **選定したら必ず snapshot を取る**（取らないと答え合わせ不能）
2. **数値計算はPython、判断はLLM**。LLMが暗算でリターンを出さない
3. **1回のレビューで手法を変えない**（教訓2回再現 + method-auditor監査が改訂の条件）
4. 検証はフォワードテスト。過去に遡って「当たったことにする」ことを禁ずる
