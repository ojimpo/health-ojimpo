# Oura Ring スコアリング調査・設計ドキュメント

> 2026-03-12 作成。health-ojimpoでOuraデータをどう扱うかの根拠資料。
> LLM引継ぎ用：このドキュメントを読めばOuraスコアリングの設計意図が分かる。

## 1. Oura公式スコアの仕組み

### Sleep Score（0-100）

7つのコントリビューターの重み付き合算（具体的な重みは非公開、ML ベース）。

| コントリビューター | 概要 | 最適値 |
|---|---|---|
| Total Sleep | Light + REM + Deep 合計 | 7-9時間（最重要） |
| Sleep Efficiency | ベッド内実睡眠割合 | 85%以上 |
| Restfulness | 中途覚醒の少なさ | 少ないほど良い |
| REM Sleep | REM睡眠時間/割合 | 90分以上（20-25%） |
| Deep Sleep | 深い睡眠時間/割合 | 若年90分/高齢45分以上 |
| Latency | 入眠までの時間 | 15-20分以内 |
| Timing | 概日リズムとの一致 | 個人の最適時間帯 |

### Readiness Score（0-100）

Sleep + HRV + 体温 + 活動量を統合した**複合指標**。「今日の体の準備度」を示す。

**短期コントリビューター（当日/前日）:**
- Resting Heart Rate: 前夜の最低心拍 vs 長期平均
- Sleep: 直近24時間の睡眠量
- Previous Day Activity: 前日の活動量 vs 長期平均
- Recovery Index: 安静時心拍が夜の前半で最低値に到達するか
- Body Temperature: 前夜の体温変化 vs 長期平均

**長期コントリビューター（14日加重平均 vs 2ヶ月平均）:**
- HRV Balance: 直近14日のHRV平均 vs 3ヶ月平均
- Sleep Balance: 過去2週間の睡眠量（睡眠負債の検出）
- Activity Balance: 過去14日の運動負荷 vs 慣れ
- Sleep Regularity: 就寝・起床時刻の一貫性

### Stress（stress_high 秒数）

- HRV + 心拍 + 動作 + 皮膚温から交感神経優位（ストレス状態）の時間を算出
- `stress_high`: 覚醒中に「高ストレス」と判定された累計秒数
- `restored`: 副交感神経優位（回復状態）の累計秒数
- 個人ベースライン相対評価、15分間隔更新、安静時のみ測定
- **低いほど良い**（他のスコアとは逆方向）

### 公式の閾値

| スコア | 評価 |
|---|---|
| 85以上 | Optimal |
| 70-84 | Good |
| 60-69 | Pay attention |
| 60未満 | Take it easy |

## 2. 学術的バリデーション

### 睡眠追跡の精度

| 研究 | 結果 |
|---|---|
| 東京大学 Gen3 検証 (2024) | 感度94.4%、特異度73.0%、精度91.8%。睡眠段階精度75-91% |
| Brigham and Women's Hospital (2024) | 4段階分類で**消費者ウェアラブル中最高精度**（PSG一致率79%） |
| メタ分析 (Khan 2025, 6研究/388名) | TST, SE, SOL, WASOいずれもPSGと有意差なし |

### HRV精度

| デバイス | CCC | MAPE |
|---|---|---|
| Oura Gen4 | 0.99 | 5.96% |
| Oura Gen3 | 0.97 | - |
| 他社ウェアラブル | 0.80-0.95 | - |

ECGとの相関が全ウェアラブル中最高。

### 注意点

- **覚醒検出は弱い**（特異度73%）→ 睡眠時間を過大評価する傾向
- Sleep/Readiness Scoreの**臨床的バリデーションは限定的**（生理指標の要約であり診断ツールではない）
- ストレス検出のAUROCは0.95程度だが、心理的ストレスと生理的ストレスの区別は不可能

## 3. health-ojimpo での実装設計

### 問題: Ouraスコアは他ソースと性質が違う

| | Last.fm等 | Oura |
|---|---|---|
| 単位 | 分、回数、k tokens（量） | 0-100スコア（質） |
| 合算方法 | SUM（累積量が意味を持つ） | AVG（日次スコアの平均が意味を持つ） |
| 欠損の意味 | 活動していない（低下シグナル） | 同期切れ（無視すべき） |

→ 専用の `score_method = 'daily_avg'` を導入。

### Readiness と Sleep の二重カウント問題

Readiness Score は**既に Sleep の要素を含む複合指標**。両方を等価に扱うと Sleep の影響が過大になる。

ただし Sleep Score には Readiness に直接含まれない独自要素がある:
- Latency（入眠時間）
- Timing（就寝タイミング）
- Restfulness（中途覚醒）

→ **Readiness 0.6 / Sleep 0.4** の重み付けを採用。

### 計算式

```
weighted_daily = readiness * 0.6 + sleep * 0.4

例: readiness=75, sleep=68 の日
→ 75 * 0.6 + 68 * 0.4 = 45 + 27.2 = 72.2

base_value = 80（1日あたりの期待値）
score = 72.2 / 80 * 100 = 90.3%
```

7日間の平均:
```
score = AVG(各日の weighted_daily) / 80 * 100
```

### Stress の扱い

**健康指標（NORMAL/CAUTION/CRITICAL）からは除外**。理由:
1. 低いほど良い → 他ソースと逆方向で合算不可
2. Readiness の HRV Balance に間接的に反映済み → 入れると二重カウント
3. 覚醒時間の長さに依存 → 絶対値での比較が不安定

→ 状態系グラフ（折れ線）でのモニタリング専用。

### 欠損耐性

`daily_avg` はデータがある日のみで平均を取る:
- 7日中7日データあり → 7日の平均（最も正確）
- 7日中3日データあり → 3日の平均（精度は下がるが壊れない）
- 0日 → スコア0

同期切れで数日データがなくても、ある日のスコアが正常ならスコアは崩壊しない。

### 設定値

```
source_settings:
  id: oura
  score_method: daily_avg
  base_value: 80
  category_weights: {"readiness": 0.6, "sleep": 0.4}
  classification: baseline
  aggregation_period: 7
```

## 4. 将来の改善案

### Stress の割合ベース化

現在: `stress_high` 秒数（覚醒時間に依存）
改善案: `stress_high / (stress_high + restored)` の割合を取得・保存

→ Oura API v2 の `daily_stress` から `stress_high` と `recovery_high` が取れる。
割合にすれば覚醒時間の長さに依存しない指標になる。

### ベースライン自動調整

設定画面に直近30日のOura平均値を表示し、ユーザーが base_value を調整しやすくする。
Oura公式が70=Good、85=Optimal としているので、80は合理的な出発点。

### Readiness/Sleep 重みの根拠更新

Ouraがアルゴリズムを更新した場合（Gen4以降でReadinessの構成が変わるなど）、
重み比率の見直しが必要。現在の 0.6/0.4 はGen3時点の構成に基づく。

## 参考文献

- [Sleep Score - Oura Help](https://support.ouraring.com/hc/en-us/articles/360025445574)
- [Readiness Score - Oura Help](https://support.ouraring.com/hc/en-us/articles/360025589793)
- [Readiness Contributors - Oura Help](https://support.ouraring.com/hc/en-us/articles/360057791533)
- [Inside the Ring: Daytime Stress](https://ouraring.com/blog/inside-the-ring-daytime-stress/)
- Gen3 OSSA 2.0 Validation Study - Sleep Medicine 2024 (PMID: 38382312)
- Oura Ring vs Medical-Grade Sleep Studies: Systematic Review & Meta-Analysis 2025 (PMC12602993)
- Nocturnal RHR and HRV Validation 2025 (PMC12367097)
