# llama.cpp 最新ビルド (HEAD=1348f67c5) でのデフォルト構成 prefill/generate 徹底ベンチ

## Context

このプロジェクトのデフォルト推論構成（t120h-p100 + Qwen3.5-122B-A10B-GGUF:Q4_K_M + fit モード, B14b_ts_alt + ctx=128k）は Phase U-6 (2026-04-24) で確定し、その時点の llama.cpp ビルドは `6217b4958`。

それから約 3 週間経過し、現在 P100 上の llama.cpp HEAD は `1348f67c5`。この間に下記の **A. 速度系 PR** と **B. ユーザ指定可能な新フラグ** が多数マージされている。ユーザ指示により**全体で 24 時間程度の予算で、可能性があるものは十分にテスト**する徹底ベンチを実施。

### A. 累積効果が期待される速度系 PR（実測対象）
| PR | マージ日 | 内容 | 期待 |
|----|---------|------|------|
| #22541 | 4/30 | CUDA: Pascal tile FA 修正 | P100 で新 FA 動作 |
| #22041 | 4/19 | meta backend: cache subgraph splits | generate +8〜16% |
| #21764 | 4/16 | ggml: add graph_reused | generate 数% |
| #22330 | 4/26 | CUDA: coalesce contiguous concat | +1〜3% |
| #22650 | 5/4  | CUDA: fastdiv for batch index split | カーネル 3〜5% |
| #21038 | – | Walsh-Hadamard rotation (KV q4_0 品質改善) | KV q4_0 で品質維持 |
| 他 #22298 / #22506 / #22651 / #21168 等 | – | 限定経路 | 累積で観測 |

### B. 試す価値のある新規/変更 CLI フラグ
| フラグ | 既定 / 用途 | 試行価値 |
|--------|-------------|----------|
| `-fa auto` | flash-attn の新既定 | 新 Tile/MMA カーネル自動選択 |
| `-ncmoe N` | 先頭 N 層の MoE expert を CPU | OT パターンの簡潔化、性能同等 or 微増 |
| `-cmoe`    | 全 MoE expert を CPU | 参考（速度大幅低下想定） |
| `-sm tensor` | tensor parallel | TG 1.3-1.7x、FA 必須・KV 量子化不可 → ctx を下げて試行 |
| `--spec-type ngram-mod` | n-gram modular spec（draft 不要） | generate +20-100% 可能性 |
| `--spec-type ngram-cache` | persistent ngram cache | 同上、長対話で hit 増 |
| `--spec-type ngram-simple` | 単純 ngram | 同上、速度 |
| `--spec-type ngram-map-k` | k-gram map | 同上 |
| `--spec-type ngram-map-k4v` | k4v 変種 | 同上 |
| `--spec-type` chain | 複数 spec を同時 | 例: `ngram-mod,ngram-cache` で accept rate 加算 |
| `--spec-type draft-mtp` | MTP（GGUF に `mtp.*` テンソル必要） | decode 1.85-2.2x（要事前確認）|
| `--cache-type-k/v q4_0` | KV 4-bit | Walsh-Hadamard ON で品質維持、VRAM 削減 |
| `--cache-type-k/v f16` | KV f16 | 速度面で最有利 (FA 経路)、ctx 縮小必要 |
| `--swa-full` / `--swa-checkpoints` | SWA 制御 | Qwen3.5 の SWA 利用有無を要確認 |
| `--main-gpu N` | CUDA0 以外を main に | memory にも未検証として記載 |

### C. 既存ロードマップの未試行項目（memory/project_t_series_roadmap.md より）
- **B12 化** (OT 14 → 12 層)、感度外挿で eval 18.91 t/s 予測
- **B16 化** (OT 14 → 16 層)、逆方向の参照
- **ub 細粒度** (200/224/288/320/384/448/640/768)
- **threads** 再 sweep
- **`--main-gpu` 切替**

## 直接比較対象（U-6, 2026-04-24, ビルド 6217b4958）

| prompt | eval t/s | prompt t/s |
|--------|----------|------------|
| 1k     | 17.692   | ~91        |
| 32k    | 14.360   | ~64        |
| **96k**| **10.029** | 53–64    |

参考: T-5a-ts2 (ctx=32k, 1k prompt) で eval 18.664 / prompt 46.082。

## ベースライン構成 (BL) = U-6 と完全同条件

llama-up.sh のデフォルト引数。`start.sh` の Qwen3.5-122B-A10B 専用プロファイル分岐により以下が自動適用：

- model: `unsloth/Qwen3.5-122B-A10B-GGUF:Q4_K_M`
- `-ngl 999 --split-mode layer`
- OT: B14b = `blk\.([2-3]|2[0-3]|3[1-8])\.ffn_.*_exps\.weight=CPU`
- `--tensor-split 11,12,13,14`
- `--flash-attn 1 --poll 0`
- `-b 2048 -ub 512`
- `--threads 40`, `numactl -N1 -m1`
- `--ctx-size 131072`
- `--cache-type-k q8_0 --cache-type-v q8_0 --parallel 1`

## 計測共通仕様

- API: `POST http://10.1.4.14:8000/v1/completions` (`stream=false`)
- prompt 先頭に `[Request ID <epoch_ns>]\n` でキャッシュ回避
- 指標: `predicted_per_second` (eval_tps), `prompt_per_second` (prompt_tps)
- prompt 長: 1k / 32k / 96k（U-6 添付を再利用）
- warmup / eval: 1k → 2/5、32k → 1/5、96k → 1/5
- max_tokens: 1k→1024, 32k→512, 96k→256
- run 間 15s cooldown、run 後に `nvidia-smi` で `min_gpu_free`
- spec 系は accept rate / draft 統計を生 JSON から抽出

各試行で BL の全 prompt 長を測るのは高コストなので、**標準は 1k と 32k**、有望と判定したら追加で **96k**。BL のみは必ず 1k/32k/96k 全段。

### ctx フォールバック規則（重要）
**全試行共通**: 既定 `--ctx-size 131072` (128k) で起動し計測。以下のいずれかが発生したら ctx を落として **同じ試行を再実行** する。

| 検出条件 | フォールバック先 |
|---------|------------------|
| llama-server 起動時 OOM / load 失敗 | `--ctx-size 98304` (96k) で再起動 |
| 96k prompt 投入時 CUDA OOM / crash / server hang | `--ctx-size 98304` (96k) で再起動 → 1k/32k/96k 全段を再計測 |
| 96k で再度 crash | `--ctx-size 65536` (64k) に下げ、96k prompt は除外 |

ctx を変更した試行は、テーブル上で `ctx=128k` ではなく `ctx=96k` 等を明示。比較時にも ctx 軸を区別する。U-6 baseline は ctx=128k で完走しているため、ctx=96k に落とした試行は U-6 直接比較の対象外（参考扱い）。

**BL が ctx=128k で crash した場合の対応**: BL を ctx=96k で再計測した値を「BL_96k」として記録。以降の F1/N1/M1/K1/S*/U*/B*/T*/O* も同じ ctx=96k で実施し **BL_96k と比較**する。この場合の U-6 直接比較は不可となるため、レポートには「BL_128k → BL_96k で再ベースライン化、U-6 比較は ctx 軸が異なるため参考扱い」と明記。

各試行のログに使用 ctx と起動回数（128k 起動 → 96k 起動などの履歴）を記録。

## 試行マトリクス（5 フェーズ、合計 14-18 時間予算）

### Phase A: ベースライン再計測 + Quick wins（合計 ~3 時間）
| ID  | 変更点 | 計測 prompt | 想定時間 |
|-----|---------|-------------|----------|
| **BL** | （変更なし、U-6 と同条件） | 1k/32k/96k | ~50 分 |
| **F1** | `--flash-attn 1` → `-fa auto` | 1k/32k | 22 分 |
| **N1** | `-ot ...` を `-ncmoe 14` に置換 **（注意: 先頭連続 14 層 = `{0-13}` を CPU、BL の `{2,3,20-23,31-38}` とは別構成）**。**性能比較ではなく、新フラグの実装妥当性と Phase T-5a の OT 最適化が現 HEAD でも維持されているかの確認**が目的 | 1k/32k | 22 分 |
| **M1** | `--main-gpu 1` （TS は維持） | 1k/32k | 22 分 |
| **K1** | `--cache-type-k/v q4_0`（VRAM 削減効果も確認） | 1k/32k | 22 分 |
| Phase A 集計 + Aha! Best 選定 | – | – | 10 分 |

**Phase A 終了時点で BL より明確に勝ったものを `BL_A` として以降のフェーズで採用**（最低でも BL を維持）。Phase A 全試行は同セッションでロックを保持して連続実行。

### Phase B: Speculative decoding 探索（合計 ~5 時間）
事前に `--spec-type draft-mtp` 用に GGUF 内の `mtp.*` テンソル存在を確認（DL 済 GGUF に `gguf-py` でメタ確認）。なければ MTP はスキップ。

| ID  | 変更点（BL_A に対して） | 計測 | 時間 |
|-----|--------------------------|------|------|
| S1  | `--spec-type ngram-simple` （+ デフォルト n-size） | 1k/32k | 30 分 |
| S2  | `--spec-type ngram-mod` （+ デフォルト n-match=24） | 1k/32k | 30 分 |
| S3  | `--spec-type ngram-cache` | 1k/32k | 30 分 |
| S4  | `--spec-type ngram-map-k` | 1k/32k | 30 分 |
| S5  | `--spec-type ngram-map-k4v` | 1k/32k | 30 分 |
| S6  | チェイン `--spec-type ngram-mod,ngram-cache` （or 上位 2 種を chain） | 1k/32k | 30 分 |
| S7  | `--spec-type draft-mtp` （MTP テンソル有無確認後）| 1k/32k | 30 分 |
| Phase B 集計、Best spec を `BL_B` に統合 | – | – | 15 分 |

**Phase B の評価軸の注意**: spec 系は **短 prompt / 長生成** で accept rate が出やすく、**長 prompt / 短生成** では効果が薄い／逆効果になる。本フェーズは 1k (max_tokens=1024) を主指標として評価し、32k (max_tokens=512) は参考、96k は spec が不利と想定して原則計測しない。BL の同条件 1k 結果との eval_tps 比 (E2E speedup) を見る。accept rate 単独ではなく E2E で判定。

各 S* で次の指標を追加: spec accept rate、effective t/s 比、VRAM 増分。

### Phase C: パラメータ sweep（合計 ~4 時間）
ベースは `BL_B`（Phase B で最良の構成、もし spec が全て負けたら `BL_A`）。

| ID  | sweep 軸 | 値 | 計測 | 時間 |
|-----|----------|-----|------|------|
| U1  | `-ub` | 256, 384, 512(BL), 640, 768 | 各 1k/32k | 60 分 |
| B1  | `-b`  | 1024, 2048(BL), 4096 | 各 1k/32k | 36 分 |
| T1  | `--threads` | 32, 36, 40(BL), 44 | 各 1k | 24 分 |
| Phase C 集計、Best 採用 → `BL_C` | – | – | 10 分 |

### Phase D: OT パターン (B12 / B16) と Architecture（合計 ~3-4 時間）
| ID  | 変更点 | 計測 | 時間 |
|-----|--------|------|------|
| O1  | B12 (CPU 12 層に削減、Phase U-5 で記録された VRAM map に従って削る) | 1k/32k/96k | 50 分 |
| O2  | B16 (CPU 16 層、参考) | 1k/32k | 30 分 |
| G1  | `-sm tensor` + KV **f16** (KV 量子化禁止) + `-fa on`。**Qwen3.5-122B-A10B の KV f16 は ctx=32k で約 50GB と推定、P100×4=64GB に対し余裕なし**。起動を ctx=16k → 8k の順に試し、最小で起動できた ctx で計測。1k/4k/16k 等の prompt 長で測定 | 1k/4k/(可能なら 16k) | 40 分 |
| W1  | Qwen3.5 が SWA を使う場合のみ: `--swa-full` 有効 / `--swa-checkpoints 4` | 1k/96k | 40 分 |
| Phase D 集計 | – | – | 10 分 |

Qwen3.5 の SWA 使用有無は GGUF メタデータの `qwen3.attention.sliding_window` 等を `gguf-py` で確認してから判定。SWA を使わないなら W1 はスキップ。

### Phase E: 結果統合 + 最終ベスト構成の再確認（合計 ~1.5 時間）
- Phase A-D で発見した最良構成を組合せた `BL_FINAL` を構築
- `BL_FINAL` を 1k/32k/96k で 5 ラン × 2 (リペアビリティ確認) で取り直し
- U-6 と T-5a-ts2 への直接比較表を完成
- レポート（後述）作成

## 実行手順

### 0. プリフライト
```bash
# ロック確認
.claude/skills/gpu-server/scripts/lock-status.sh t120h-p100
.claude/skills/gpu-server/scripts/lock.sh t120h-p100 bench-head-1348f67c5-marathon

# ビルド・モデル確認
ssh t120h-p100 "cd ~/llama.cpp && git rev-parse HEAD && ls -la build/bin/llama-server"
ssh t120h-p100 "find ~/.cache/huggingface/hub -name '*Q4_K_M*.gguf' 2>/dev/null | head"

# 不一致 / 不在なら再ビルド (+20 分) / DL (+25 分)

# Qwen3.5 GGUF メタ調査（MTP テンソル & SWA 有無）
ssh t120h-p100 "cd ~/llama.cpp && python3 -c \"
from gguf import GGUFReader
r = GGUFReader('<path>')
print('mtp:', [t.name for t in r.tensors if 'mtp' in t.name.lower()][:5])
print('swa:', [(k, r.fields[k].parts) for k in r.fields if 'sliding' in k.lower() or 'swa' in k.lower()])
\""
```

### 1. start.sh の安全な引数注入機構
Phase A 以降の試行ごとに `start.sh` の Qwen3.5-122B-A10B プロファイル分岐を手動編集 → 試行 → 起動 → 計測 → 停止 → revert のサイクル。

各試行前に：
```bash
cd /home/ubuntu/projects/llm-server-ops
git status --short                  # 編集前にクリーンか確認
# .claude/skills/llama-server/scripts/start.sh を一時編集 (Edit ツール)
git diff .claude/skills/llama-server/scripts/start.sh   # 編集内容確認
.claude/skills/llama-server/scripts/llama-up.sh
# 計測
.claude/skills/llama-server/scripts/llama-down.sh t120h-p100
git checkout .claude/skills/llama-server/scripts/start.sh   # revert
```

または各試行を独立スクリプトに切り出してプロジェクトルートを汚さない方法も可（後述、`/tmp/start_override_<phase><id>.sh` を生成して ssh 直叩き）。

### 2. 計測スクリプト・prompt 流用
- `report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/measure_phaseU6.sh`
- `report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/prompts/prompt_{1k,32k,96k}.txt`

### 3. 各試行の標準フロー
```bash
WORK=/tmp/bench_head_<phase><id>_$(TZ=Asia/Tokyo date +%Y%m%d_%H%M%S)
mkdir -p $WORK
# (start.sh 編集 → llama-up.sh)
ssh t120h-p100 "cat /proc/\$(pgrep -f llama-server | head -1)/cmdline | tr '\0' ' '" > $WORK/cmdline.txt
ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv" > $WORK/gpu_pre.csv

for tag in 1k 32k 96k; do
  # max_tokens / warmup / eval 設定
  CELL=<phase>_<id>_$tag COND_ID=<id> UB=512 \
    PROMPT_TAG=$tag PROMPT_FILE=$PROMPT_DIR/prompt_${tag}.txt \
    OUTDIR=$WORK/out_${tag} \
    WARMUP_RUNS=$W EVAL_RUNS=$E EVAL_MAX_TOKENS=$MT COOLDOWN=15 \
    PID=$(ssh t120h-p100 "pgrep -f llama-server | head -1") \
    CSV=$WORK/results.csv \
    bash measure_phaseU6.sh
done

ssh t120h-p100 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv" > $WORK/gpu_post.csv
.claude/skills/llama-server/scripts/llama-down.sh t120h-p100
# (start.sh revert)
```

### 4. 集計
各フェーズ終了時に `/tmp/bench_head_marathon_results.csv` に統合し、Python で mean/stdev/比較表を作成。

## レポート構成（REPORT.md ルール準拠）

24 時間スパンで多数の試行があるため、**各フェーズ A-E ごとに別レポート** + **最終総合レポート**の 6 本立て：

| ファイル | 内容 |
|---------|------|
| `report/<ts>_qwen3-122b-bench-marathon-phaseA-quickwins.md` | BL + F1/N1/M1/K1 |
| `report/<ts>_qwen3-122b-bench-marathon-phaseB-spec.md` | S1-S7 |
| `report/<ts>_qwen3-122b-bench-marathon-phaseC-sweep.md` | U1/B1/T1 |
| `report/<ts>_qwen3-122b-bench-marathon-phaseD-arch.md` | O1/O2/G1/W1 |
| `report/<ts>_qwen3-122b-bench-marathon-phaseE-final.md` | `BL_FINAL` の確認測定 |
| `report/<ts>_qwen3-122b-bench-marathon-summary.md` | 全体総合・U-6/T-5a-ts2 比較・推奨デフォルト |

各レポート構造（共通）：
- 添付ファイル一覧
- 前提・目的（ビルド `1348f67c5` 明記）
- 再現方法
- 結果テーブル（5 ラン mean ± stdev）
- 仮説と解釈
- 効きそうな PR / 効いた PR 推定
- 次フェーズへの反映点
- **核心発見サマリは冒頭に配置**、ハイライト画像があれば同セクション冒頭に埋め込み

最終総合レポートには：
- 全試行のクロス比較表（BL vs 全試行）
- U-6 / T-5a-ts2 への対比
- デフォルト構成更新の推奨（あれば）
- 24h バジェットで未到達 / 諦めた項目
- `plan.md` のコピー添付（必須）

## リスクと対応

| リスク | 対応 |
|--------|------|
| ロック競合 | プリフライトで取得、長時間専有のためユーザに事前共有 |
| 24h 中に他作業が割り込む | フェーズ単位で commit / レポート化、中断しても継続可能に |
| HEAD 不一致 / ビルド破損 | プリフライトで再ビルド |
| モデル未 DL | プリフライトで確認、未 DL なら DL |
| `--spec-type` ごとに crash / hang | run 単位 timeout 300s、crash は accept rate 0 で記録、即次へ |
| MTP テンソル不在 | S7 スキップ、未試行として記録 |
| `-sm tensor` で fit 崩壊 | ctx=32k で試行、それでも OOM なら `-fa on -ctk f16 -ctv f16` に変更 |
| 128k で起動時 OOM / 96k prompt で crash | **ctx を 96k → 64k の順に落として再試行**（上記「ctx フォールバック規則」に従う）|
| SWA 非対応モデル | W1 スキップ |
| ub/threads sweep で局所最適に hit するも全体改善せず | OK、結果として記録 |
| `start.sh` 編集忘れ / revert 忘れ | 各試行 begin / end で `git diff` 確認、最終フェーズで完全 clean を保証 |
| 連続実行で drift / thermal | フェーズ間に 5 分 idle、各試行内 5 ラン stdev で安定性確認 |
| 試行中 OOM 連発 | min_gpu_free モニタ、即停止 |

## タイムライン

| フェーズ | 想定 |
|---------|------|
| Phase 0 プリフライト | 30 分 |
| Phase A ベースライン + Quick wins | ~3 時間 |
| Phase B Spec exploration | ~5 時間 |
| Phase C Sweep | ~4 時間 |
| Phase D Arch | ~4 時間 |
| Phase E 最終確認 | ~1.5 時間 |
| レポート 6 本 | ~3 時間（フェーズ完了時に逐次作成）|
| バッファ | ~2 時間 |
| **合計** | **~23 時間** |

途中で OOM 多発 / crash 多発の場合は早期打ち切り → 達成済みのフェーズで総合レポートを出す。

## 検証 (Verification)

1. 各フェーズの単体レポート + 総合レポートの計 6 本が `report/` 配下に作成済み
2. 各レポートに `plan.md` の copy が添付済み
3. `results.csv` 統合版に全試行（BL/F1/N1/M1/K1/S1-7/U1/B1/T1/O1/O2/G1/W1/BL_FINAL）の eval 5 ラン記録
4. 総合レポートに U-6 / T-5a-ts2 比較、BL_FINAL の新ベスト数値、`start.sh` 推奨パラメータ案
5. llama-server 停止 & ロック解放 (`lock-status.sh`)
6. `start.sh` が完全に revert されている (`git diff` 空)
7. 「効きそうな PR」リストの各 PR について、観測された効果の有無を明記
8. 24h スパンで未到達の試行があれば「未試行候補」として記録

## Critical Files

- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/llama-up.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/llama-down.sh`
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/llama-server/scripts/start.sh`（プロファイル 175-194 行を試行ごとに編集 / revert）
- `/home/ubuntu/projects/llm-server-ops/.claude/skills/gpu-server/scripts/lock.sh`, `lock-status.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/measure_phaseU6.sh`
- `/home/ubuntu/projects/llm-server-ops/report/attachment/2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default/prompts/prompt_{1k,32k,96k}.txt`
- `/home/ubuntu/projects/llm-server-ops/REPORT.md`
