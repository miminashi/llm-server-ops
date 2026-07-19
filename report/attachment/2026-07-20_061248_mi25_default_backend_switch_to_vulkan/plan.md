# mi25 デフォルトバックエンドを ROCm/hip → Vulkan/RADV に反転

## Context

前セッション (2026-07-20) の切り分けで、**mi25 の prompt eval 退行はバックエンドの選び方の問題**であることが確定した:

- ROCm/hip 側だけが long-ctx で退行 (1k は健全、32k で -19%、100k で -35%)
- Vulkan/RADV 側は 1k=+4% / 32k=-9% / 100k=-12% と実質全域で過去水準を維持
- tg も Vulkan (39.5 t/s) > ROCm (28.8 t/s) と逆転

結果、mi25 の実運用としては Vulkan を **既定** として使うのが最適という判断が下された ([2026-07-20 pp 退行レポート](../../projects/llm-server-ops/report/2026-07-20_013500_mi25_prompt_eval_regression.md))。

しかし現状の `start.sh` / `update_and_build-mi25.sh` の default は `MI25_BACKEND=hip`。ユーザ / 別セッションが `MI25_BACKEND=vulkan` を prefix しない限り退行した ROCm 経路で起動してしまう。本タスクではこれを **default = vulkan** に反転し、ROCm 側は `MI25_BACKEND=hip` を明示したときのみの fallback 経路にする。ROCm ビルド構成 (v8533 pin) は当面残置 (万一の fallback 用途、能動的な維持は不要)。

## 変更対象ファイルと差分

### 1. `.claude/skills/llama-server/scripts/start.sh` (L239)

現状:
```sh
if [ "${MI25_BACKEND:-hip}" = "vulkan" ]; then
```
変更後:
```sh
if [ "${MI25_BACKEND:-vulkan}" = "vulkan" ]; then
```

**注意**: L239 の分岐そのものは反転しない (else 分岐が ROCm 経路のまま維持される)。default 値だけを `hip` → `vulkan` に変える。既存の Vulkan 経路 (LLAMA_BIN の切替 / vulkaninfo 検出 / GGML_VK_VISIBLE_DEVICES 設定) はそのまま流用される。

L214 コメント「MI25 (gfx900/ROCm) x4 = 64GB」は ROCm 経路の説明として妥当なので触らない (else 側の詳細解説にあたる)。

### 2. `.claude/skills/llama-server/server-scripts/update_and_build-mi25.sh` (L12, L21)

現状:
```sh
# L12 (usage コメント)
  MI25_BACKEND  ビルドバックエンド: hip (既定) | vulkan
                hip    : ROCm/HIP (gfx900)。FP8 型リグレッション回避のためコミット pin。
                         build/ にビルド。
                vulkan : Vulkan (RADV)。pin 不要で master 追従。build-vulkan/ にビルド。

# L21
MI25_BACKEND="${MI25_BACKEND:-hip}"
```
変更後:
```sh
# L12
  MI25_BACKEND  ビルドバックエンド: vulkan (既定) | hip
                vulkan : Vulkan (RADV)。pin 不要で master 追従。build-vulkan/ にビルド。
                hip    : ROCm/HIP (gfx900) fallback。FP8 型リグレッション回避のためコミット pin。
                         build/ にビルド。

# L21
MI25_BACKEND="${MI25_BACKEND:-vulkan}"
```

### 3. `.claude/skills/llama-server/SKILL.md`

#### 3a. サーバ別最適化パラメータ表 (L289-290) の見出し反転

- L289 見出し「mi25 (ROCm/hip, 既定)」 → 「mi25 (ROCm/hip, `MI25_BACKEND=hip`)」
- L290 見出し「mi25 (Vulkan/RADV, `MI25_BACKEND=vulkan`)」 → 「mi25 (Vulkan/RADV, 既定)」

表の行の並び順は現状 (ROCm 行 → Vulkan 行) のままでもよいが、既定を上に置く方が直感的なので **Vulkan 行を先に、ROCm 行を後に** 入れ替える。

#### 3b. 「mi25 のバックエンド切替」節 (L295-308) の書き換え

現状のリード文 (L297):
> mi25 は2つのバックエンドを持つ。**既定は ROCm（hip）**。環境変数 `MI25_BACKEND=vulkan` を付けると Vulkan（RADV）に切り替わる（`start.sh` が `build-vulkan/bin` を使用）。

変更後 (反転 + 反転理由の1段落を追加):
> mi25 は2つのバックエンドを持つ。**既定は Vulkan（RADV）**。環境変数 `MI25_BACKEND=hip` を付けると ROCm（hip）に切り替わる（`start.sh` が `build/bin` を使用）。
>
> **反転の背景 (2026-07-20)**: 過去は ROCm を既定としていたが、長 ctx (32k/100k) で ROCm 側だけが退行する現象を切り分けた結果、Vulkan が prompt eval / token gen ともに ROCm を上回ることが確認された (Vulkan pp 100k=191 t/s vs ROCm 100k=38.9 t/s / Vulkan tg=39.5 t/s vs ROCm tg=28.8 t/s)。詳細は [2026-07-20 mi25 pp 退行レポート](../../../report/2026-07-20_013500_mi25_prompt_eval_regression.md)。ROCm 側の long-ctx 退行原因調査は打ち切り、`MI25_BACKEND=hip` は fallback 用途で残置する。

例示コードブロック (L299-304) も反転:
```bash
# Vulkan（既定）
.claude/skills/llama-server/scripts/start.sh mi25 "<model>" 131072
# ROCm（fallback）
MI25_BACKEND=hip .claude/skills/llama-server/scripts/start.sh mi25 "<model>" 131072
```

L306-307 の説明箇条書きは **順序入れ替え + 数値更新** (要点: 順序を Vulkan 先 → ROCm 後 にする、L306 Vulkan 節にある「prompt は ROCm の約3.3倍・eval は約0.6倍」は 2026-06-14 の Vulkan RADV 実測ベースで **既定反転の根拠と矛盾する** (最新 2026-07-20 実測では tg も Vulkan が ROCm を上回る)、以下の数値で置き換える):

- **Vulkan (既定)**: `build-vulkan/` を使用、**pin 不要（master 追従）**。ub は VRAM/速度にほぼ無影響だが ROCm と同値（ub=2048）を踏襲。**2026-07-20 実測で prompt eval / token gen とも ROCm を上回る** (pp 1k=541 t/s / 32k=372 t/s / 100k=191 t/s、tg=39.5 t/s)。KV は **q8_0 固定**（f16 は高負荷でホスト不安定、`FA=0`+q8_0 は不可）。
- **ROCm (fallback, `MI25_BACKEND=hip`)**: `update_and_build-mi25.sh` で gfx900 ビルド可能コミット (`0fac87b15`, v8533) に **pin**（master は `__hip_fp8_e4m3` を gfx900 で参照しビルド不能）。起動パラメータは上表のとおり ub=2048。**2026-07-20 実測で long ctx (32k/100k) の pp が退行** (1k は健全 254 t/s、32k -19%、100k -35%)、原因未解明のまま fallback 用途で残置。

L308 の「Vulkan の GPU 可視性（自動検出）」箇条書きと L309 の「GPU 枚数チェック」箇条書きはそのまま残す (内容として反転後も有効)。

### 4. `CLAUDE.md` (クイックリファレンス表の直下)

現状 L37-57 (クイックリファレンス表) の直後に以下の 1 段落を追加:

```markdown
**mi25 デフォルトバックエンド**: Vulkan (RADV, 4 枚 x16GB)。
`MI25_BACKEND=hip` を明示すると ROCm fallback。詳細は
[llama-server SKILL.md](.claude/skills/llama-server/SKILL.md) の「mi25 のバックエンド切替」節、
および [2026-07-20 pp 退行レポート](report/2026-07-20_013500_mi25_prompt_eval_regression.md)。
```

**注**: SKILL.md へのリンクはアンカーなしにする理由 — SKILL.md 実見出しは `### mi25 のバックエンド切替（ROCm / Vulkan）` で全角丸括弧・全角スペースを含み、GFM 環境の renderer 差でアンカー解決が不安定なため。追加位置は現状の「クイックリファレンス」表 (L37-42) の直下・`**OSハング...` 段落の**前**。

## 実施手順

1. **ロック取得** (作業実施のため必須):
   - `.claude/skills/gpu-server/scripts/lock-status.sh`
   - `.claude/skills/gpu-server/scripts/lock.sh mi25`
2. **既存稼働の停止**: `.claude/skills/llama-server/scripts/stop.sh mi25` (Vulkan で稼働中の可能性あり)
3. **ファイル編集** (Edit ツールで順次):
   - `start.sh` L239 の default 値反転
   - `update_and_build-mi25.sh` L12 コメント / L21 default 値反転
   - `SKILL.md` の 3 箇所 (表見出し / リード文 / 例示コード)
   - `CLAUDE.md` の 1 段落追加
4. **動作確認** (`MI25_BACKEND` 未指定で Vulkan 起動されることを確認):
   ```bash
   .claude/skills/llama-server/scripts/start.sh mi25 \
     "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
   .claude/skills/llama-server/scripts/wait-ready.sh mi25 \
     "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
   # 起動ログで "Vulkan: RADV 物理 GPU を検出 → GGML_VK_VISIBLE_DEVICES=0,1,2,3 (4枚)" が出れば OK
   curl -sf http://10.1.4.13:8000/health && echo
   ssh mi25 "ps aux | grep 'build-vulkan/bin/llama-server' | grep -v grep"
   ```
5. **fallback 経路確認** (時間があれば):
   ```bash
   .claude/skills/llama-server/scripts/stop.sh mi25
   MI25_BACKEND=hip .claude/skills/llama-server/scripts/start.sh mi25 \
     "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
   ssh mi25 "ps aux | grep 'build/bin/llama-server' | grep -v grep"
   # 確認後、Vulkan に戻す
   .claude/skills/llama-server/scripts/stop.sh mi25
   .claude/skills/llama-server/scripts/start.sh mi25 \
     "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
   ```
6. **レポート作成** (REPORT.md ルール準拠):
   - `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で日時取得
   - 例: `report/<日付>_<時刻>_mi25_default_backend_switch_to_vulkan.md`
   - `## 概要` (通読可能な日本語 5〜8 段落) 必須
   - コード変更のみのレポートなので `## 核心発見サマリ` の PNG は不要 (省略可能)
   - `## 添付ファイル` に plan.md をコピー
   - `report/INDEX.md` に 1 行追記
7. **ロック解放** (作業完了後、または llama-server を Vulkan 稼働状態で維持したままなら `stop.sh` せず lock だけ解放)

## 検証で見るポイント

- `MI25_BACKEND` **未指定** で起動ログに `Vulkan: RADV 物理 GPU を検出 → GGML_VK_VISIBLE_DEVICES=0,1,2,3 (4枚)` が出る
- プロセスパスが `~/llama.cpp/build-vulkan/bin/llama-server` (ROCm 経路の `build/bin/llama-server` ではない)
- `/health` が `{"status":"ok"}` を返す (エンドポイント: `http://10.1.4.13:8000/v1`)
- `MI25_BACKEND=hip` 明示時は `build/bin/llama-server` が起動する (fallback 経路が壊れていない)

## 関連ファイル (触らない)

- `start.sh` の Vulkan 経路実装 (L240-255, `detect_radv_vk_indices` 関数) — そのまま流用
- `update_and_build-mi25.sh` の `build_llama_cpp_vulkan()` / `build_llama_cpp_hip()` 関数 — そのまま流用
- `PINNED_COMMIT="0fac87b15"` (L33) — ROCm fallback 用に残置
- `SKILL.md` の t120h-p100 / t120h-m10 節 — mi25 に無関係
- `report/attachment/2026-0[4-6]*/` 配下の M (5090 ファイル) — LFS 遡及マッチ検出、コミットしない (前セッション方針「将来分のみ LFS」を維持)
- `.gitignore` の M — 前セッション由来、ユーザ判断待ちのため放置
