# MI25+Vulkan パラメータ探索ベンチマーク計画

## Context（なぜこれをやるか）

参照レポート `report/2026-06-18_051739_llamacpp_3mo_changes_p100_mi25vulkan.md` は過去3ヶ月の
llama.cpp 変更をコードリーディングのみで棚卸ししたもので、性能効果は未実測（「実測は別途ベンチで行う」）。

**本計画の目的**: 過去コミットの寄与を分離測定するのではなく、**報告書で得た知見から、現状の
ベースラインをさらに改善できる起動パラメータ・設定値（env var / CLI オプション）がまだ無いかを
探す**こと。基準は `report/2026-06-14_001107_mi25_vulkan_qwen36_128k.md` で確立した構成・数値。
基準値に対し別パラメータを与えて比較し、改善が外乱でないことを複数回測定で確認する。

報告書から導かれる探索の焦点:
- **eval（トークン生成）が弱点**: Vulkan eval は ROCm の約0.6倍（15.2 vs 24.5 t/s @32k）。eval は
  **行列ベクトル積(MMV)カーネル**律速で、報告書の eval 改善候補はこの MMV の**両系統**にまたがる:
  量子化系（`19620004f` Q3_K/Q6_K block-load、`d6d0ce821` iq1）と **F16/F32 系**（`c6e408837`
  MUL_MAT_VEC 4K/iter for F16/32）、および混合精度の `b4e3dc613` dot2_f16。本計画のモデル重みは
  **Q4_K**（UD-Q4_K_XL）なので量子化 MMV 経路が主、活性化/一部テンソルが F16/F32 経路。これらを
  制御する**ランタイム・ノブ**（量子化MMV の `*_MMVQ`、整数dot、dot2_f16、融合）が改善余地の本命。
- これらノブは GGML_VK_* 群（`ggml-vulkan.cpp` の `getenv`）。サブエージェント調査由来のため、
  **セットアップ時に mi25 の `~/llama.cpp` で各 env-var の実在を `git grep getenv` で確認**してから
  A/B する。**全てリビルド不要**で、現 master を1回ビルドし env/起動引数の差替だけで A/B できる。
- 報告書の未解決問い「gfx900 で dot2_f16 が有効化されるか」も、起動ログのデバイス機能行＋
  `GGML_VK_DISABLE_DOT2` のランタイム A/B で決着できる（診断枠。無効化は速度を上げないが、
  現状寄与の定量＋機能有無の確定に意味がある）。
- prompt は既に良好（ROCm の3.3倍）。本計画は eval 改善を主目標とし、prompt/VRAM も併記する。

## 環境・基準構成（2026-06-14 レポート由来）

| 項目 | 値 |
|------|-----|
| サーバ | mi25 (10.1.4.13)、Vulkan/RADV、**実効3枚**（SLOT4 脱落、`project_mi25_gpu4_pcie_dropout`） |
| モデル | `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`（arch=`qwen35moe` hybrid） |
| 基準構成 | `--flash-attn 1 --poll 0 -b 2048 -ub 2048`、KV `q8_0`、ctx=131072、split-mode layer |
| バックエンド | `MI25_BACKEND=vulkan`、`./build-vulkan/bin/llama-server`、`GGML_VK_VISIBLE_DEVICES`（実効デバイス要確認・後述） |
| **基準値** | prompt 405 t/s・**eval 15.2 t/s**・GPU[0] 8.72GB（@32k, ub=2048, 単一試行） |

**注（実効デバイス）**: SLOT4 脱落により Vulkan が列挙する実 GPU は 3 枚で、device3 が llvmpipe(CPU)に
なる可能性がある（2026-06-14 品質レポート）。`start.sh` は `GGML_VK_VISIBLE_DEVICES=0,1,2,3` を固定
埋め込みするが、本ベンチではセットアップ時に起動ログのデバイス列挙を読み、**llvmpipe を除いた実 GPU
インデックスのみ**を `GGML_VK_VISIBLE_DEVICES` に明示設定する（誤って CPU レンダラに割り当てない）。

## 前提作業・セットアップ

1. **ロック取得（必須）**: `.claude/skills/gpu-server/scripts/lock.sh mi25`（LLM 使用）。
2. 現 master へ Vulkan ビルドのみ確定: `MI25_BACKEND=vulkan .../llama-up.sh mi25 "<model>" 131072` で
   1回ビルド（Vulkan は pin 不要、以降のベンチはリビルドしない）。**注**: `llama-up.sh`→`start.sh` は
   `GGML_VK_VISIBLE_DEVICES=0,1,2,3` を固定 ENV_PREFIX で埋め込むため、env-var A/B には使えない。
3. **env-var A/B 用のカスタム起動ラッパ**（attachment に作成）: 各条件で start.sh を介さず、
   `ssh mi25 "cd ~/llama.cpp && <COND_ENV> GGML_VK_VISIBLE_DEVICES=<実GPU> nohup ./build-vulkan/bin/llama-server <基準引数±条件引数> > /tmp/llama-server.log 2>&1 &"`
   の形で直接起動する。基準引数は `--flash-attn 1 --poll 0 -b 2048 -ub 2048 -ctk q8_0 -ctv q8_0 -c 131072`。
   条件ごとに `<COND_ENV>`（例 `GGML_VK_FORCE_MMVQ=1`）や CLI 引数（例 `-sm row`）を差し替える。
   ヘルスチェック `curl -sf http://10.1.4.13:8000/health` で起動確認。
4. **env-var の実在確認**: 使用予定の各 GGML_VK_* を `ssh mi25 "cd ~/llama.cpp && git grep -n getenv ggml/src/ggml-vulkan"`
   で実在確認（サブエージェント列挙の検証。存在しないものは実験から除外）。
5. **デバイス機能ログの取得**: 起動ログ（`/tmp/llama-server.log`、必要なら `GGML_LOG_LEVEL` を上げる）
   から各 GPU の device 行を読み、`fp16: dot2`（dot2_f16）/ `integer_dot_product` / matrix cores /
   実効デバイス（llvmpipe 除外）を確認。**どの env-var A/B が意味を持つか**をここで確定
   （存在しない機能の disable は no-op）。実 GPU インデックスを以降の `GGML_VK_VISIBLE_DEVICES` に固定。
6. **計測基盤の再利用**: `report/attachment/.../measure_phaseU6.sh`（warmup→eval を N 回、COOLDOWN、
   CSV 化、`timings.prompt_per_second`/`predicted_per_second` 抽出）と既存プロンプト
   `prompts/prompt_{1k,32k}.txt` をコピーし、model 名を Qwen3.6 に差替。VRAM は各ランで
   `ssh mi25 "rocm-smi --showmeminfo vram | grep Used"`。

## 実験マトリクス（全て現master・リビルド不要。各 N=5、warmup2、COOLDOWN15s）

主軸は **32k プロンプト**（100k は1試行が長く外乱混入大）。有望ノブは **1k** でも追試（短文 eval は
ボトルネックが異なる）。各条件は基準（E0）に対する A/B。

**改善探索枠（基準より速くなりうる軸）**

| ID | ノブ（種別） | 値 | 仮説（eval への効き） | 優先 |
|----|------------|-----|----------------------|------|
| **E0** | 基準アンカー（drift bracket 起点） | 基準構成 | 15.2 t/s を N=5 で再確認・統計化 | 必須 |
| **E1** | MMVQ モード（量子化重み Q4_K の MMV 経路） | auto(基準) / `GGML_VK_FORCE_MMVQ=1` / `GGML_VK_DISABLE_MMVQ=1` | auto 選択が最適か、強制 ON/OFF どちらが速いか（量子化 eval 本命） | **高** |
| **E5** | `-ub`（物理バッチ） | 512,1024,2048,4096 | eval スイートスポット探索（P100 は ub≈512 で eval peak、Vulkan は ub非依存説の再検証） | 中 |
| **E6** | `--split-mode`（GPU分割） | layer(基準) vs row | row が3枚で MMV を並列化し eval 改善するか（ROCm/P100 では -15〜22%、かつ Vulkan は row 実装が限定的で layer に fallback する可能性あり→ 実測で確認） | 中 |
| **E7** | `GGML_VK_ASYNC_USE_TRANSFER_QUEUE`（転送キュー分離） | unset vs `1` | weight 転送と compute の overlap で eval 改善 | 中 |
| **E8** | `-t`/`-tb`（CPUスレッド） | 数点掃引 | hybrid MoE の expert/サンプリング CPU 側影響（mi25 では未測定） | 低-中 |
| **E9** | `--tensor-split`/`--main-gpu` | 均等 vs 偏り、mg 0/1 | 3枚配分・KV 起点の最適化 | 低-中 |
| **E10** | `GGML_VK_SUBALLOCATION_BLOCK_SIZE` 等メモリ系 | 512M/1G/2G | 断片化削減（eval 影響は小と予想、余力あれば） | 低 |

**診断枠（速度は上げないが、現状の最適性確認＋報告書の未解決問いに回答）**

| ID | ノブ（種別） | 値 | 目的 | 優先 |
|----|------------|-----|------|------|
| **D1** | `GGML_VK_DISABLE_DOT2`（dot2_f16, `b4e3dc613`） | unset(基準) vs `1` | gfx900 で dot2_f16 が有効化され効いているか決着（報告書の未解決問い）。デバイス機能行が `dot2` の時のみ意味 | 中 |
| **D2** | `GGML_VK_DISABLE_INTEGER_DOT_PRODUCT`（整数dot） | unset(基準) vs `1` | 整数dot無効化で劣化幅＝現状の寄与を定量。Q4_K eval の整数dot依存度を把握 | 中 |
| **D3** | `GGML_VK_DISABLE_FUSION`（演算融合） | unset(基準) vs `1` | 融合の eval 寄与を定量 | 低 |

- **prompt t/s・VRAM も全条件で併記**（同一リクエストから無料で取れる）。VRAM 比較は FA mask F16
  化（`031ddb2e0`）の効果確認も兼ねる（前回 GPU[0] 8.72GB との対比）。
- **有望ノブの組合せ**: 単体で有意改善したものを最後に2〜3個組合せて測定。ただし marathon の教訓
  どおり**効果は線形加算でない**ため、組合せは必ず実測する。

## 計測方法・外乱対策（過去 marathon の運用を踏襲）

- 各条件: warmup 2 回 → eval 5 回、COOLDOWN 15s。**mean ± std と CV%(=std/mean)** を算出。
- **2点ブラケットで drift 補正**: セッション起点と終点で E0（基準）を測り、線形ドリフトを補正。
  セッションは ≤80 分目安（thermal drift < 0.2 t/s）。長くなる場合は分割。
- **有意性判定**: 基準 vs 各条件を Welch の t 検定（t≈2〜2.5, p<0.05 を「軽微だが有意」と判定）。
  **改善が外乱でないこと**を CV と t 検定の両方で確認（ユーザ要求）。
- CV が大きい/有意性が微妙な条件は N を増やして再測定。
- 既知の地雷を回避: **f16 KV は使わない**（Vulkan で過去にホスト down、本番 q8_0 限定）、
  ub>4096 は VRAM リスク、`--defrag-thold` は deprecated 警告のみ（無害）。

## 実行フロー

1. ロック取得 → 現 master を Vulkan ビルド → env-var 実在確認 → カスタム起動 → デバイス機能ログ
   確認（実効デバイス・dot2/integer_dot の有無を確定）。
2. 計測スクリプト/プロンプトをコピー・model 名差替・カスタム起動ラッパ作成。
3. **E0（起点 bracket）→ 改善探索枠（E1 → E5 → E6 → E7 → E8 → E9 → E10）→ 診断枠（D1 → D2 → D3）
   → E0（終点 bracket）**。各条件はカスタムラッパで env/引数を差し替えてサーバ再起動。CSV を逐次保存。
   デバイス機能行に `dot2`/`integer_dot` が無ければ D1/D2 は no-op として省略。
4. 単体で有意な改善ノブを 2〜3 個組合せて追試（効果は非線形なので実測必須）。1k でも有望条件を追試。
5. サーバ停止（`stop.sh mi25`）→ **ロック解放**（`unlock.sh mi25`）。

## 成果物（レポート）

- `report/yyyy-mm-dd_hhmmss_mi25_vulkan_param_sweep.md`（タイトル50字以内・日本語、`TZ=Asia/Tokyo date`）。
- **核心発見サマリ冒頭に PNG 埋め込み必須**（各ノブの eval t/s 改善幅を基準比で示す棒グラフ、
  ub スイープの折れ線等。matplotlib 生成、`report/attachment/<報告名>/` に配置）。
- 必須セクション: 前提・目的 / 環境情報 / 再現方法 / 核心発見サマリ / 実験マトリクスと結果
  （各条件 mean±std, CV, N, Welch t, p, 採用可否）/ 推奨構成の更新提案 / 参照リンク。
- **plan.md を attachment にコピーし「添付ファイル」節からリンク**（REPORT.md ルール）。
- 結論として「基準を改善する設定があったか・採用すべき新構成」を明示。無改善でも「効かなかった軸」
  として記録（次回の探索効率化）。

## 検証（このベンチ自体の妥当性）

- 全数値に N・mean±std・CV を付し、改善が外乱でないことを CV と Welch t の両方で確認。
- drift 2点ブラケットで補正済みであることを明記。
- 採用候補は最終的に基準と同一セッション内で再確認（再現性）。
