---
name: best-five
description: >-
  日本株・米国株それぞれから「最も儲かる20銘柄」を選定するプロジェクトスキル。
  ユーザーが「儲かる株は？」「儲かる株教えて」「銘柄選んで」「20銘柄選んで」「有望株は？」
  「おすすめ銘柄」などと言ったら必ず使う。METHOD.mdの手法に従いスクリーニング→赤信号チェック→
  最終20+20選定→PER/PBR/時価総額/次回決算日の付与→スナップショット記録→根拠表提示まで
  一気通貫で実行する。
---

# best-five（日米「儲かる20銘柄」選定）

## 事前に必ず読むもの
1. `METHOD.md` — 現行の投資分析方法（バージョン確認）
2. `LESSONS.md` — 過去の答え合わせの教訓（選定判断に反映）

## 実行手順

スクリーニング計算にはグローバルスキルのスクリプトを使う:
`SCR = C:\Users\iki_n\.claude\skills\stock-screener\scripts`

### 1. データ鮮度確認と再スクリーニング判断
`data/work/` の各CSVの更新日を確認:
- universe: 30日以内ならそのまま。古ければ `python $SCR/universe.py --market jp|us --out data/work/xx_universe.csv`
- technical: **7日以内**ならそのまま。古ければ
  `python $SCR/technical_screen.py --universe data/work/jp_universe.csv --out data/work/jp_technical.csv --top 150 --min-turnover 100000000`
  （US は `--min-turnover 5000000`）
- fundamental: **90日以内**ならそのまま。古ければ
  `python $SCR/fundamental_screen.py --market jp --universe data/work/jp_universe.csv --out data/work/jp_fundamental.csv --cache data/work/jp_fins_raw.csv`
  （JPはJ-Quantsレート制限で約20分かかる。USは `--resume` 付き）

### 2. 統合ランキング（候補プール上位40/市場）
```
python $SCR/merge_candidates.py --technical data/work/jp_technical.csv --fundamental data/work/jp_fundamental.csv --out data/work/jp_merged40.csv --top 40
python $SCR/merge_candidates.py --technical data/work/us_technical.csv --fundamental data/work/us_fundamental.csv --out data/work/us_merged40.csv --top 40
```

### 3. 赤信号チェック（並列サブエージェント）
`candidate-analyst` サブエージェントを **1体あたり最大10銘柄で分割し、1メッセージで同時起動**
（各市場の上位30をチェック → JP3体+US3体の計6体並列）。
渡すもの: ticker・銘柄名・セクター・スコア・20日リターン。

### 4. 最終20+20確定（メインエージェントの判断）
METHOD.md §4 のルールで各市場20銘柄に絞る:
- セクター最大4銘柄・「除外」判定は次点繰り上げ・スコア差5点以内なら赤信号なしを優先
- 「警戒」はリスクを根拠表に明記した上で採否判断

### 5. 情報付与と記録（必須・スキップ禁止）
最終20銘柄×2市場を `data/work/jp_pick20.csv` / `us_pick20.csv` に保存
（merged40と同じ列構成のまま行を絞る）してから:
```
python scripts/enrich_picks.py --picks data/work/jp_pick20.csv --fundamental data/work/jp_fundamental.csv --out data/work/jp_pick20.csv
python scripts/enrich_picks.py --picks data/work/us_pick20.csv --fundamental data/work/us_fundamental.csv --out data/work/us_pick20.csv
python $SCR/snapshot.py --picks data/work/jp_pick20.csv data/work/us_pick20.csv --outdir data/snapshots --note "METHOD vX.X による20+20選定"
```
enrich_picks.py が PER・PBR・時価総額・次回決算日 を各銘柄に付与する。

### 6. 報告
- 選定根拠表を `reports/picks_YYYYMMDD.md` に保存し、**チャットにも表で提示**:
  `| 銘柄 | セクター | 総合 | PER | PBR | 時価総額 | 次回決算 | 根拠 | リスク/警戒点 |`
- 時価総額の表記: JPは億円、USは$B
- 答え合わせ予定日（7d/30d/90d）を明示して締める。

## 禁止事項
- スナップショットなしで選定を終えること
- スコア計算をLLMの暗算で代替すること
- METHOD.mdに書かれていない独自基準の無断使用（気付きはLESSONS.mdに書き、改訂手続きへ）
