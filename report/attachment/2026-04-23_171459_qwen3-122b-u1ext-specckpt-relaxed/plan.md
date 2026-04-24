# Phase U-1-ext: 緩和 VRAM 構成で spec checkpointing A/B 完走

## Context

直前 Phase U-1 ([report/2026-04-23_132933_qwen3-122b-u1-specckpt-baseline.md](../../../projects/llm-server-ops/report/2026-04-23_132933_qwen3-122b-u1-specckpt-baseline.md)) は以下の状況で区切られた:

- llama.cpp を `6217b4958` まで再ビルド成功（PR #19493 + 関連 fix 4 件取り込み済）
- OFF baseline は B14b_ts_alt で 18.542 / 18.940 / 18.726 t/s (1k/code/repetitive)、cross-session drift -0.65% 以内
- **ON (spec decoding) は全試行で 5-run eval 未完走**: B14b_ts_alt の GPU3 残 1260 MiB に対し spec decoding ephemeral + ngram cache 16 MiB + context checkpoint 149 MiB/slot + prompt cache 153 MiB が累積して Run 2 以降で CUDA OOM
- 軽量化 5 段階（ctx-ckpt 4→1→0 / cache-ram 0 / draft-max 16）すべて Run 2 以降 OOM
- **warmup Run1 単発では ON が OFF より +0.86〜+1.35% 高い兆候あり** (haiku ~80 tok、単サンプル)

本 Phase U-1-ext のゴール: **VRAM に余裕を持たせた構成で OFF/ON を prompt_1k + prompt_code + prompt_repetitive の 3 種 × warmup 2 + eval 5 完走させ、spec ckpt の task 依存効果と acceptance rate を確定する**。副次的に B14b OFF 歴代最良 18.664 t/s を spec ON で更新できるか評価する。

ロードマップ上は U-1-ext 完了後 → U-2 (--cache-ram サイズ影響単独測定) → U-3 (spec ckpt パラメータ sweep) → U-4 (gate/up fused GGUF) の順（auto-memory 参照）。

## Goals / Non-Goals

**Goals**
- spec ckpt ON の eval 5-run 統計値 (mean ± stdev) を最低 1 つの緩和構成で取得
- 3 prompt それぞれで OFF/ON A/B を完走させ task 依存性を示す
- acceptance rate（サーバログ `statistics ngram_mod: #gen/#acc drafts`）を 3 prompt 別に抽出
- 緩和構成の OFF に対する ON の speedup を定量化、B14b OFF 18.664 t/s との比較
- eval_tps の raw + drift 補正後（OFF baseline との cross-session 差分で補正）を両方提示

**Non-Goals**
- `--spec-ngram-size-n/m` / `--draft-min/max` / `--ctx-checkpoints` の sweep（Phase U-3）
- `--cache-ram` 単独での影響測定（Phase U-2）
- 長コンテキスト (≥ ctx 16k) での spec ckpt 動作（Phase U-3 以降）
- gate/up fused GGUF 再変換（Phase U-4）

## 構成選定

U-1 で判明した制約条件:

| 構成 | OT CPU offload | GPU0 free | GPU1 free | GPU2 free | GPU3 free | 備考 |
|------|---------------:|----------:|----------:|----------:|----------:|------|
| B14b_ts_alt (U-1) | 14 layers | 1164 | 2035 | 4693 | **1260** | OFF 18.664 t/s、ON OOM |
| B18 (T-5a-ub 参考) | 18 layers | **834** | 4722 | 6114 | 2662 | OFF 18.103 t/s |

spec ckpt が必要とする最低 VRAM 余裕（U-1 観測から逆算）: 1 GPU あたり **ckpt 149 + prompt cache ~150 + draft ephemeral ~100 = 400〜500 MiB** を既存残に加える必要がある。B14b でも片方の GPU (GPU3) に 1.8 GiB 以上確保できれば完走する見込み。

### Config A (主、記録更新狙い): B14b_ctx16k_cacheram256

- Base: B14b_ts_alt (OT 14 layers, -ts 11,12,13,14, ub=256, threads 40, KV q8_0, fa 1, sm layer)
- **変更点**:
  - `--ctx-size 16384` (KV 半減 → 各 GPU ~400〜800 MiB 解放、GPU3 推定残 1.7〜2.0 GiB)
  - `--cache-ram 256` (prompt cache 上限を 256 MiB に絞る、ただし ON; 無効化ではない)
  - ON 時さらに `--ctx-checkpoints 4 --spec-type ngram-mod --spec-ngram-size-n 24 --draft-min 48 --draft-max 64` (U-1 の推奨値)
- **期待**: OFF ~18.4〜18.55 t/s (ctx 半減による小規模影響 + 18.664 からの drift 込み)。ON がこれを +1.3% 超えれば B14b 歴代最良更新。
- **Risks**: GPU3 残が推定より小さく Run 2 以降で OOM、`--cache-ram` が expected MB 単位でなく KB / バイト単位のリスク（dry probe で確認）。

### Config B (副、完走保証): B18_ts_balanced

- Base: B18 (OT 18 layers, `OT_REGEX='blk\.([0-3]|2[0-4]|3[1-9])\.ffn_.*_exps\.weight=CPU'`, ctx=32768, ub=256, threads 40, KV q8_0, fa 1, sm layer)
- **変更点**:
  - `--tensor-split 11,14,14,11` (GPU0 / GPU3 を軽く、GPU1 / GPU2 を重く。B18 default 測定時 GPU0 残 834 MiB だったため)
  - ON 時 Config A と同じ spec flags
- **期待**: OFF ~18.1 t/s (B18 T-5a-ub 18.103 baseline)。GPU 全 ch に 1.5 GiB 以上残る見込みで spec ckpt は確実に完走。ON が B18 OFF より +3% 以上なら 18.6 超え。
- **Risks**: `-ts 11,14,14,11` は B18 で未実測なので OFF ts2 と異なる挙動の可能性。保険として挙動がおかしければ `--tensor-split 12,14,14,10` 等にフォールバック。

### 実行順序

1. **Config A dry probe** → OFF 1 prompt (prompt_1k) × warmup 1 + eval 2 で VRAM / 完走可否を確認 (計 5-10 分)
2. Config A が完走可能なら: **Config A full A/B** (3 prompt × 2 mode × warmup 2 + eval 5)
3. Config A が OOM なら: Config B に即切替。または Config A 軽量化 (`--cache-ram 128` 等 1 段のみ試行)
4. Config A 完走後、時間に余裕があれば Config B も full A/B を追加実施（比較の厚みを出すため）
5. 集計・レポート

## Critical files / paths

### 既存再利用 (Phase U-1 attachment からコピー、改変しない)

```
report/attachment/2026-04-23_132933_qwen3-122b-u1-specckpt-baseline/
├── start_phaseU1.sh           # EXTRA_ARGS 注入 I/F 完備、そのまま使用
├── run_all_phaseU1.sh         # WARMUP 2 + EVAL 5 フレーム、そのまま使用
├── measure_phaseT5.sh         # .timings 抽出、そのまま使用
├── prompts/prompt_1k.txt
├── prompts/prompt_code.txt
└── prompts/prompt_repetitive.txt
```

### 新規作成 (/tmp/phaseU1ext/ 配下)

```
/tmp/phaseU1ext/
├── start_phaseU1ext.sh              # start_phaseU1.sh を軽微改変 (CTX env var 受け入れ、リモートログ path 変更)
├── run_all_phaseU1ext.sh            # run_all_phaseU1.sh とほぼ同じ (TAG_PREFIX 変更のみ)
├── measure_phaseT5.sh               # U-1 からコピー (変更なし)
├── batch_phaseU1ext_A.sh            # Config A: B14b_ctx16k_cacheram256, 6 条件
├── batch_phaseU1ext_B.sh            # Config B: B18_ts_balanced, 6 条件 (time permitting)
├── batch_phaseU1ext_A_smoke.sh      # Config A dry probe (1 prompt, 3 run)
├── prompts/ -> (U-1 attachment から copy)
├── parse_spec_stats.py              # サーバログから `statistics ngram_mod: #gen = X, #acc = Y` を抽出 → TSV
├── analyze_phaseU1ext.py            # U-1 analyze を拡張: drift 補正 eval_tps + accept rate 集計
├── plot_phaseU1ext.py               # PNG 生成: onoff_eval / speedup / history / acceptance
└── startup_logs/                    # サーバ起動ログ + nvidia-smi csv (各条件)
```

### 補助スクリプト (プロジェクトリポ内、読み取りのみ)

- `.claude/skills/gpu-server/scripts/lock.sh` / `unlock.sh` / `lock-status.sh`
- `.claude/skills/llama-server/scripts/stop.sh`

### t120h-p100 上 (変更なし、確認のみ)

- `~/llama.cpp/build/bin/llama-server` (`6217b4958`、U-1 と同一、**再ビルド不要**)
- モデル: `/home/llm/.cache/huggingface/hub/models--unsloth--Qwen3.5-122B-A10B-GGUF/.../Qwen3.5-122B-A10B-Q4_K_M-00001-of-00003.gguf`

## Plan

### Step 0: ロック取得 + 作業ディレクトリ準備

```bash
bash .claude/skills/gpu-server/scripts/lock.sh t120h-p100
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100  # 念のため

mkdir -p /tmp/phaseU1ext/{prompts,startup_logs}
cp report/attachment/2026-04-23_132933_qwen3-122b-u1-specckpt-baseline/{start_phaseU1.sh,run_all_phaseU1.sh,measure_phaseT5.sh} /tmp/phaseU1ext/
cp report/attachment/2026-04-23_132933_qwen3-122b-u1-specckpt-baseline/prompts/*.txt /tmp/phaseU1ext/prompts/

# バイナリ同一確認 (ハッシュ化は不要、U-1 レポート注記で十分)
ssh t120h-p100 "cd ~/llama.cpp && git rev-parse HEAD"  # => 6217b4958... であること
```

### Step 1: `--cache-ram` 引数仕様の dry probe

U-1 では `--cache-ram 0` (無効化) は確認したが **具体的なサイズ指定の挙動未検証**。

```bash
ssh t120h-p100 "~/llama.cpp/build/bin/llama-server --help 2>&1 | grep -E 'cache-ram|ram'"
# Expected: --cache-ram N [MiB]  のような表記。MB 単位で整数引数を取ることを確認
```

`/metrics` エンドポイント (Prometheus) が spec stats を出力するかも合わせて確認:

```bash
ssh t120h-p100 "~/llama.cpp/build/bin/llama-server --help 2>&1 | grep -E 'metrics|slots'"
# --metrics / --slots フラグの有無と default を確認
```

### Step 2: start_phaseU1ext.sh 作成 (U-1 start を軽微改変)

変更点:
- `CTX_SIZE` を env var で受け入れ（既に U-1 で実装済、そのまま）
- リモートログ path を `/tmp/llama-server_phaseU1ext_...log` に変更（U-1 と混在しないよう）
- OOM 検知 grep パターンはそのまま継承

`run_all_phaseU1ext.sh` も同様に TAG_PREFIX 接頭辞を `U1ext_` に変更するだけ。

### Step 3: Config A smoke (prompt_1k のみ、warmup 2 + eval 2)

```bash
cd /tmp/phaseU1ext
bash batch_phaseU1ext_A_smoke.sh 2>&1 | tee smoke_A.log
```

目的:
- GPU3 残 VRAM が 1.8 GiB 以上確保できるか実機確認
- ON で eval Run 2 まで完走するか確認
- `--cache-ram 256` が想定通り動作するか確認
- サーバログに `statistics ngram_mod` が出るか確認

**完走しなければ**:
1. `--cache-ram 128` に縮小して再試行
2. それでもダメなら `--ctx-checkpoints 2` に縮小
3. さらにダメなら Config A 放棄し Config B へ移る

### Step 4: Config A full A/B 実行

```bash
cd /tmp/phaseU1ext
bash batch_phaseU1ext_A.sh 2>&1 | tee batch_A.log
```

6 条件:
- `OFF_prompt1k` / `OFF_code` / `OFF_repetitive` (B14b_ts_alt + ctx=16384 + --cache-ram 256)
- `ON_prompt1k` / `ON_code` / `ON_repetitive` (さらに `--spec-type ngram-mod --ctx-checkpoints 4 --spec-ngram-size-n 24 --draft-min 48 --draft-max 64`)

各条件: warmup 2 run (haiku) + eval 5 run (prompt切替)、条件間でサーバ再起動 (prompt / ngram cache 汚染回避)。

各条件ごとに stop.sh の **前に** サーバログをローカル `startup_logs/` に fetch (U-1 実装継承)。spec stats はサーバが出力する `statistics ngram_mod: #gen drafts = X, #acc drafts = Y` 行をこのログから解析する。

### Step 5: Config B full A/B 実行 (Config A 完走後、時間があれば)

```bash
cd /tmp/phaseU1ext
bash batch_phaseU1ext_B.sh 2>&1 | tee batch_B.log
```

B18 で 6 条件。Config A より VRAM 余裕があるため追加軽量化は不要見込み。

### Step 6: 集計・可視化

```bash
cd /tmp/phaseU1ext
python3 parse_spec_stats.py  # startup_logs/ を全スキャン → spec_stats.tsv
python3 analyze_phaseU1ext.py  # eval 5-run mean + drift 補正 + merge spec_stats
python3 plot_phaseU1ext.py     # PNG 生成
```

### Step 7: 停止 + ロック解放

```bash
bash .claude/skills/llama-server/scripts/stop.sh t120h-p100
bash .claude/skills/gpu-server/scripts/unlock.sh t120h-p100
```

### Step 8: レポート作成

- タイムスタンプ: `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`
- タイトル (50 字以内): 「Phase U-1-ext: spec ckpt A/B 完走 (緩和 VRAM 構成)」(36 字)
- ファイル名: `report/<ts>_qwen3-122b-u1ext-specckpt-relaxed.md`
- プランファイル添付必須: `report/attachment/<basename>/plan.md` (本ファイルをコピー)
- **核心発見サマリ**冒頭に PNG 3 枚埋め込み (`spec_onoff_eval_ext.png` / `spec_onoff_speedup_ext.png` / `phaseU1ext_history.png`)
- 必須比較表:
  - 歴代 Phase (D / T-5 / T-5a-ub / T-5a-ts / T-5a-ts2 / U-1 OFF / U-1-ext OFF / U-1-ext ON)
  - U-1 との直接比較 (B14b_ts_alt OFF 18.664 vs U-1-ext 緩和 OFF vs U-1-ext 緩和 ON)
  - prompt 別 OFF / ON / speedup / accept rate
- 「未検証事項」「検証完了後 TODO」セクション必須（U-1 の TODO の取捨含む）

## Metrics / 取得データ

各 eval run ごとに `.timings.*` 全フィールドを JSON 保存、特に:

- `predicted_per_second` (eval_tps, 主指標)
- `prompt_per_second` (prompt_tps, 参考)
- `predicted_n` / `prompt_n` (整合性確認)
- `draft_n` / `draft_accepted_n` (ON 時のみ、JSON に入るか未確認。Step 1 で確認)

サーバログから抽出 (ON 条件のみ):

- `statistics ngram_mod: #gen drafts = X, #acc drafts = Y` → acceptance_rate = Y / X
- `slot create_check: ... created context checkpoint N of M (size = X MiB)` → ckpt 実行回数・サイズ
- `cuMemCreate` / `out of memory` キーワード → OOM 発生有無

派生メトリクス:

- **drift 補正後 ON eval_tps** = ON_raw * (18.664 / OFF_raw) (OFF が B14b baseline の cross-session 変化を補正)
- **OFF / ON speedup 倍率**
- **prompt tps の ON/OFF 比** (spec decoding の prefill overhead 確認)

## Verification (受け入れ基準)

1. Config A または B のいずれかで **3 prompt × OFF/ON × eval 5 run が全て成立** (n=5 の CSV 行が 6 条件すべてに入る)
2. ON 条件で acceptance rate が最低 1 prompt について非 null (`spec_stats.tsv` に `#gen drafts > 0`)
3. レポートに PNG 3 枚 (eval bar / speedup / history) 埋め込み
4. 歴代比較で B14b OFF 18.664 を基準線として表示
5. drift 補正前後の ON eval_tps を両方記載
6. Config A 採用時は `--cache-ram 256` と `--ctx-size 16384` が起動ログに反映されていることを startup_logs で確認
7. ロック解放済 (`lock-status.sh` で空)

## Risks / Fallback

- **R1: Config A も OOM (ctx 16k + cache-ram 256 でも GPU3 不足)** → `--cache-ram 128`、`--ctx-checkpoints 2`、`--spec-ngram-size-n 16` の順で段階軽量化。それでも失敗なら Config B へ完全移行。
- **R2: Config B の `-ts 11,14,14,11` で eval_tps が B18 default より >3% 劣化** → `-ts 12,14,14,10` または `-ts default` にフォールバック。
- **R3: サーバログに `statistics ngram_mod` が出ない** → `/metrics` Prometheus endpoint で取得。それも無理ならレポートに「acceptance rate 取得不可」と明記し、eval_tps のみで比較。
- **R4: OFF baseline が U-1 時点から > 1% drift** → 直前 OFF 測定値で ON に drift 補正を適用し、生値と補正値を両方レポート。
- **R5: ctx=16384 により prompt が入り切らない** → U-1 の prompt_1k (1097 tok) / prompt_code (656 tok) / prompt_repetitive (504 tok) は全て 2k 以下なので ctx=16384 で十分。出力 max_tokens=256 も余裕。
- **R6: Config A 完走に時間かかりすぎ (>3h)** → Config B をスキップし Config A のみでレポート作成。
- **R7: ロック競合** → `lock-status.sh` 確認、他セッション使用中なら遅延待機。
