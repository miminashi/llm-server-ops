# mi25 で Qwen3.6-35B-A3B を 128k コンテキスト実行（P100 同様の最適化探索）

## Context（背景・目的）

P100 (t120h-p100) では Qwen3.6-35B-A3B (UD-Q4_K_XL) を 131072 (128k) コンテキストで
本番運用している（opencode 実ワークロードベンチ judge=4.44 で最高得点）。
2台目の GPU サーバ **mi25** でも同じモデルを 128k で動かせるようにし、運用の冗長化・
並行利用を可能にしたい。本タスクは P100 と同様の探索を mi25 に対して行い、
最適パラメータを確定し、必要なインフラ整備（モデル配置・start.sh 分岐更新）を行う。

### 探索で判明した重大な前提（実機調査済み・2026-06-13）

- **mi25 は実機で MI25 が 3 枚しか OS に認識されていない**（総 VRAM 約 48GB）。
  ドキュメント記載の「4 枚 64GB」と相違。ユーザによれば物理的には 4 枚装着済み。
- PCIe トポロジ調査の結論:
  - GPU 用ルートポート = ソケット0 `00:02.0`/`00:03.0`(2枚) + ソケット1 `80:03.0`(1枚) = **3枚**
  - ソケット1 には対称な **Root Port 2 (`80:02.0`) が lspci に列挙されない**。
    4 枚目はこの配下にあるはずだが、ルートポート自体が OS から消えている。
  - 空きルートポートでも通常は列挙されるため、**BIOS 無効化 / PCIe リンクトレーニング
    失敗（電源・装着）の可能性が濃厚**。OS 上のソフト操作では解決しない見込み。
  - `dmesg_restrict=1` のためカーネルログは sudo が必要で、確定診断は未了。
- P100 は 4 枚 64GB 中 43.4GB（平均 ~10.9GB/枚）で 131k を動かす。総量だけ見れば mi25 の
  48GB でも 43.4GB は収まるが、問題は **per-card 分散**：3 枚だと 1 枚あたり ~14.5GB と
  16GB 上限に迫り、`--split-mode layer` の層偏りや compute buffer 増で **特定カードが
  16GB を超えて OOM するリスクが高い**。**4 枚復活で 64GB・per-card に余裕が生まれれば
  P100 同様に安定**する。

### ユーザ指示による方針
- **4 枚目 GPU が認識されない原因を調査する**（最優先の追加課題）。
- 探索の結果 **128k が収まらない場合は「報告のみ」**（妥協 ctx の確定や CPU オフロードはしない）。

---

## Phase 0 — 4枚目 GPU 認識の原因調査・復旧（ユーザ協力が必須）

OS から見える切り分けは完了済み（Root Port `80:02.0` 欠落）。残る sudo 診断は
**llm に NOPASSWD sudo を設定済み（2026-06-13 確認）のため Claude が ssh 経由で直接実行**
する。物理・BIOS 点検のみユーザ作業。

1. **カーネルログ確認**（Claude が sudo 実行）— PCIe リンクトレーニング失敗・amdgpu 初期化
   エラーの有無を確認:
   ```bash
   ssh mi25 'sudo dmesg | grep -iE "pci|amdgpu|link.*(down|train|fail)|80:02"' | tail -40
   ```
2. **PCIe 再スキャン試行**（Claude が sudo 実行・ソフト復旧の可能性は低いが試す）:
   ```bash
   ssh mi25 'echo 1 | sudo tee /sys/bus/pci/rescan' ; ssh mi25 'lspci | grep -c "Instinct MI25"'
   ```
3. 上記で復活しない場合の **物理・BIOS 点検**（ユーザ作業）:
   - 4 枚目の PCIe 補助電源ケーブル接続、スロット/ライザー装着の確認
   - BIOS で該当 PCIe スロット（ソケット1 側）が Enabled か、bifurcation 設定
   - 再起動後に `ssh mi25 'lspci | grep -c "Instinct MI25"'` で 4 になるか確認

### 分岐
- **4 枚（64GB）に復活した場合** → Phase 2 を P100 と同等の余裕で実施（131k 収容ほぼ確実）。
- **3 枚（48GB）のまま** → Phase 2 を 48GB 制約で実施。131k が収まらなければ
  ユーザ指示どおり **原因（FA 非対応 / VRAM 不足）と必要 VRAM 試算を報告して終了**。

---

## Phase 1 — インフラ整備（モデル配置・start.sh 更新）

### 1-1. モデルを P100 → mi25 へコピー
mi25 の HF キャッシュは空。`hf download` での直接 DL も可能だが、ユーザ指示どおり
**LAN 内コピー**を行う（既存スクリプト `transfer-file.sh` = Python HTTP サーバ + curl を利用）。

- P100 のキャッシュから GGUF 実体パスを特定（分割ファイルなら全パート）:
  ```bash
  ssh t120h-p100 'find ~/.cache/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-GGUF/ -name "*UD-Q4_K_XL*.gguf" -not -name "*.incomplete"'
  ```
- mi25 側に同等のキャッシュディレクトリを作成し、各 GGUF パートを転送:
  ```bash
  .claude/skills/gpu-server/scripts/transfer-file.sh t120h-p100 <src-gguf> mi25 <dst-gguf>
  ```
  - `start.sh` (263行) は `find ~/.cache/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-GGUF/ -name '*UD-Q4_K_XL*.gguf'` で
    検索するため、**この命名・パスに実体ファイルを置けば認識される**（snapshots/blobs の
    symlink 構造は厳密には不要、find がヒットすれば良い）。分割 GGUF の場合は全パートを同一
    ディレクトリに配置。
- 転送後にサイズ整合を確認（transfer-file.sh が自動チェック）。

### 1-2. start.sh の mi25 分岐
現状 `start.sh:175-177` の mi25 分岐は `SERVER_OPTS="-b 4096 -ub 4096"`（Flash Attention なし）。
Phase 2 の探索結果に基づき、最適値（FA 有無・ub 値）へ更新する。
- 参考: P100 分岐 `start.sh:178-188` は `--flash-attn 1 --poll 0 -b 4096 -ub 4096`。
- KV 量子化 (`--cache-type-k/v q8_0`)・サンプリング (Qwen3.6 プロファイル `start.sh:224-227`,
  `--dry-multiplier 0 --presence-penalty 1.0`) は全サーバ共通で既に適用されるため変更不要。

---

## Phase 2 — パラメータ探索（128k 起動 + 速度最適化）

`gpu-server` Skill でロック取得後に実施（GPU 占有のためロック必須）:
```bash
.claude/skills/gpu-server/scripts/lock.sh mi25
```

### 探索軸（P100 の知見を起点に mi25/ROCm 固有差分を詰める）
1. **Flash Attention (ROCm gfx900) の有効性** ← 最重要。
   - `EXTRA_LLAMA_OPTS="--flash-attn 1"` 有無で起動可否・compute buffer・速度を比較。
   - gfx900 は llama.cpp の専用 FA カーネル対象外の可能性があり、FA が効かない/遅い場合は
     OFF が最適となる。P100 では FA なしだと ctx≥8k で compute buffer OOM だった点に注意
     （mi25 は VMM:no で挙動が異なるため実測で判断）。
2. **ub 値**（4096 / 2048 / 512）: ロード時 VRAM と prompt 処理速度のトレードオフ。
   48GB なら ub を下げて VRAM を確保、64GB なら ub=4096 で prompt 速度優先。
3. **131072 (128k) 収容**: `--cache-type-k/v q8_0` 維持、`-ngl 99 --split-mode layer` で
   3〜4 枚に分散。ロード時 VRAM と 2 回目の大リクエストでの OOM を確認（P100 の OOM 教訓）。
4. **速度実測**: 1k / 32k / 128k 付近で eval(token-gen) と prompt 処理 t/s を計測。

### 探索手順（EXTRA_LLAMA_OPTS で非破壊的に試行 → 確定値を start.sh へ反映）
```bash
# 例: FA 有効 + ub=2048 で 131k 起動テスト
EXTRA_LLAMA_OPTS="--flash-attn 1 -ub 2048" \
  .claude/skills/llama-server/scripts/start.sh mi25 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
# VRAM: ssh mi25 'rocm-smi --showmeminfo vram'
# health: curl -sf http://10.1.4.13:8000/health
# 速度: /v1/chat/completions で長文プロンプト投入し timings を確認
```
各試行ごとに `stop.sh` で停止 → 次パラメータ。OOM/未起動はログ `/tmp/llama-server.log` で診断。

### 収まらない場合（ユーザ指示）
48GB で 131k が安定しない場合は、**原因（FA 非対応 / KV+compute が VRAM 超過）と必要 VRAM
試算を報告して終了**（妥協 ctx の確定・CPU オフロードは行わない）。4 枚復活が前提条件である
旨を明記する。

---

## Phase 3 — 反映とレポート

- 確定した最適構成を `start.sh` の mi25 分岐に反映（Phase 1-2）。
- `llama-down.sh mi25`（または stop.sh + unlock.sh）で後片付け。
- **REPORT.md 準拠でレポート作成**（plan mode で計画を立てたため必須）:
  - タイトル 50 字以内、「核心発見サマリ」に主要結論
  - 4 枚目 GPU 認識問題の原因切り分け結果（PCIe Root Port `80:02.0` 欠落）
  - mi25 での 128k 最適パラメータ（FA 有無・ub・VRAM 収支・eval/prompt 速度）と P100 比較
  - VRAM 収支表・速度実測値。必要なら VRAM/速度の PNG を「核心発見サマリ」冒頭に埋め込み
- 必要に応じ Discord 通知（`discord-notify` Skill）。

---

## 検証方法（エンドツーエンド）

1. `ssh mi25 'lspci | grep -c "Instinct MI25"'` → Phase 0 後に 4 になるか（復旧した場合）。
2. `curl -sf http://10.1.4.13:8000/health` が 200 を返す。
3. 推論テスト:
   ```bash
   curl http://10.1.4.13:8000/v1/chat/completions -H "Content-Type: application/json" \
     -d '{"model":"unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL","messages":[{"role":"user","content":"hello"}],"max_tokens":32}'
   ```
4. 128k 近傍の長文プロンプトで OOM せず応答し、`timings` の eval/prompt t/s を記録。
5. `rocm-smi --showmeminfo vram` でロード時 VRAM がカード容量内に収まることを確認。

## リスク・未確定事項

- **sudo 診断は Claude 実行可（NOPASSWD 設定済）。ただし物理装着・電源・BIOS 対応は
  ユーザ作業**。ソフト（rescan）で復活しなければ 4 枚化はユーザの物理/BIOS 対応待ちとなり、
  3 枚 48GB のまま 131k が per-card OOM で収まらなければ報告のみで終了（ユーザ指示）。
- **ROCm gfx900 の Flash Attention 実効性は実測待ち**。P100 と最適 ub が異なる見込み。
- GGUF が分割ファイルの場合は全パート転送が必要（実行時に確認）。
