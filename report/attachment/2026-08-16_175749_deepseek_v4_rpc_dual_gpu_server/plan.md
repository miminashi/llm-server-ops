# DeepSeek-V4-Flash UD-Q4_K_XL を aws-gpu01 + aws-gpu02 の RPC 分散で起動する

## Context

`unsloth/DeepSeek-V4-Flash-0731-GGUF:UD-Q4_K_XL` は **155.1 GB（144.4 GiB）** あり、
aws-gpu01 単体の VRAM 112 GiB にも aws-gpu02 単体の 88 GiB にも収まらない。
2 台を llama.cpp の **RPC バックエンド**で束ねて合計 200 GiB の VRAM に載せ、
起動可否・VRAM 実測値・pp/tg 性能を確認するのが本タスクの目的。

両機は 100GbE（ConnectX-4）で直結されており、この構成で 13 枚の Tesla P100 を
1 プロセスから使えるかどうかが未検証。成功すれば、このリポジトリで扱える最大級の
モデルクラスが一段上がる。

### 調査で確定した事実

| 項目 | 実測値 |
|---|---|
| モデルサイズ | 5 shard 合計 155,095,241,120 B = **144.4 GiB**（unsloth 公式の 4-bit 要件 162GB と整合） |
| VRAM 空き | gpu01 = 113,932 MiB（16GB×7）/ gpu02 = 89,490 MiB（16GB×4 + **12GB×2**）→ 合計 **198.7 GiB** |
| 差引ヘッドルーム | 約 **54 GiB**（KV cache + 13 デバイス分の compute buffer） |
| 100GbE | 両機 ConnectX-4 / **Speed 100000Mb/s** / **MTU 9000** / RTT 0.20 ms |
| RDMA | `mlx5_0/1 state ACTIVE`、`libibverbs.so.1` 導入済 → **RPC の RDMA 転送が自動で有効化される見込み** |
| llama.cpp | 両機とも `~/llama.cpp` が **HEAD `10bf611e5` で一致**。`deepseek4` アーキ実装あり（`src/models/deepseek4.cpp`） |
| ビルド状況 | **gpu01 は `build/` 自体が無い**。gpu02 のバイナリは **2026-01-31** の古いもの（`GGML_RPC:BOOL=ON`） |
| 新 op の Pascal 対応 | `lightning_indexer` は `turing_mma_available(cc)` で分岐し、**非 wmma フォールバック経路がある**（sm_60 で動く見込み・性能は落ちる） |
| ディスク空き | gpu01 = **707 GB**（モデル格納可）/ gpu02 = 140 GB（RPC worker はモデル不要） |
| 電源 | **両機とも稼働中（uptime 17h）→ 爆音を伴う電源操作は一切不要** |
| ビルド環境 | 両機 nvcc 12.0 / gcc 13.3。gpu02 は 1 月にこの組み合わせでビルド成功実績あり |

### ユーザ確定事項

- **ctx-size は 32768 で開始**（起動確認を優先し、VRAM 実測後に段階的に伸ばす）
- **DSpark（speculative decoding）は今回スコープ外**（本体のみ。draft モデル 10.9 GB は後日フェーズ 2）
- **スクリプト化は最小限**（ビルドスクリプトへの RPC 追加 + rpc worker 起動/停止スクリプト。
  `start.sh` への統合は成功構成が固まってから別途判断）

### 役割分担

- **aws-gpu01 = メインホスト**（VRAM 112 GiB / RAM 157 GiB / disk 707 GB / 24C48T）。
  モデルファイルを保持し `llama-server` を実行。API は既存慣行どおり `10.8.2.1:8000`。
- **aws-gpu02 = RPC worker**（`ggml-rpc-server`）。モデルファイルは不要（メインホストが
  重みを RPC 経由で転送する）。**100GbE 側 `192.168.100.2` にのみバインド**する。

---

## 実装ステップ

### 0. ロック取得（GPU を使うので必須）

```bash
.claude/skills/gpu-server/scripts/lock.sh aws-gpu01
.claude/skills/gpu-server/scripts/lock.sh aws-gpu02
```

作業終了時は `unlock.sh` で解放。**電源 OFF はしない**（`llama-down.sh` は使わない）。

### 1. ビルドスクリプトに RPC を追加

`.claude/skills/llama-server/server-scripts/update_and_build-aws-gpu01.sh` と
`-aws-gpu02.sh` の `build_llama_cpp()` に **`-DGGML_RPC=ON`** を追加する。

あわせて **`-n/--no-pull` オプション**を両スクリプトに追加する。理由: RPC は
メインホストとワーカーの llama.cpp バージョンが一致していないとプロトコル不整合で
失敗するため、`git pull` で片方だけ HEAD が進む事故を防ぐ必要がある。現在両機とも
`10bf611e5` で揃っているので、**この commit のまま両方をビルドする**。

既存の `-DLLAMA_OPENSSL=ON -DGGML_NATIVE=ON -DGGML_CUDA=ON -DGGML_CUDA_FA_ALL_QUANTS=ON
-DCMAKE_CUDA_COMPILER=/usr/bin/nvcc -DCMAKE_CUDA_ARCHITECTURES=60` はそのまま維持。

### 2. ビルド実行（両機並列・バックグラウンド）

```bash
scp .claude/skills/llama-server/server-scripts/update_and_build-aws-gpu01.sh \
  aws-gpu01:~/llama.cpp/update_and_build.sh
ssh aws-gpu01 "cd ~/llama.cpp && ./update_and_build.sh --no-pull --force"
# gpu02 も同様（-aws-gpu02.sh を転送）
```

- `run_in_background: true` で 2 台同時に走らせる。`FA_ALL_QUANTS=ON` があるため
  **30〜60 分**を見込む（gpu02 は ninja 未導入なので make、20C40T で遅い側）
- ビルド後に **両機の `llama-server --version` / `ggml-rpc-server` の commit が一致すること**を確認
- **RDMA が有効化されたか**を cmake ログで確認（`libibverbs` 検出の有無）
- 失敗時のフォールバック: `-DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-12` を追加
  （nvcc 12.0 は gcc-13 を公式サポートしないため。ただし gpu02 に成功実績あり）
- バイナリ名は新しい llama.cpp では **`ggml-rpc-server`**、古い版は `rpc-server`。
  ビルド後に `ls build/bin/ | grep rpc` で実名を確定させてからスクリプトに反映する

### 3. モデルダウンロード（ビルドと並行、gpu01 のみ）

aws-gpu01 は HF 直ダウンロードが原則（CLAUDE.md「モデルダウンロード」節）。

```bash
source ~/.config/gpu-server/.env
ssh aws-gpu01 "~/.local/bin/hf download unsloth/DeepSeek-V4-Flash-0731-GGUF \
  --include 'UD-Q4_K_XL/*' \
  --local-dir ~/models/DeepSeek-V4-Flash-0731-GGUF \
  --token $HF_TOKEN"
```

- 155 GB / 実測 27 MB/s → **約 95 分**。`run_in_background: true` で流す
- 完了後、5 ファイルすべてのサイズを HF API の期待値と `stat -c %s` で照合する
  （期待値: 5257408 / 48935523072 / 48980787136 / 49999168416 / 7174505088）
- gpu02 にはモデルを置かない（140 GB しか空きが無く、RPC worker には不要）

### 4. RPC worker 起動スクリプトを新設

新規 `.claude/skills/llama-server/scripts/rpc-up.sh` / `rpc-down.sh`:

- 引数: サーバ名（既定 `aws-gpu02`）、バインドアドレス（既定 `192.168.100.2`）、ポート（既定 `50052`）
- `rpc-up.sh`: 既存プロセスを検出したら警告して終了（冪等性は `stop.sh` の作法に合わせる）→
  `nohup ./build/bin/ggml-rpc-server -H <ip> -p <port> > /tmp/rpc-server.log 2>&1 &` →
  **LISTEN 検証**（`ss -ltn`）→ 起動ログに列挙された Devices を表示
- `rpc-down.sh`: `pgrep` → `kill` → 最大 10 秒待機（`stop.sh` と同じ構造を踏襲）
- **セキュリティ**: llama.cpp 公式が「RPC サーバは認証が無く安全でない」と明記しているため、
  `0.0.0.0` ではなく **100GbE 直結セグメントの `192.168.100.2` に限定してバインドする**

### 5. llama-server 起動（gpu01、手動コマンド）

```bash
ssh aws-gpu01 'cd ~/llama.cpp && nohup ./build/bin/llama-server \
  --model ~/models/DeepSeek-V4-Flash-0731-GGUF/UD-Q4_K_XL/DeepSeek-V4-Flash-0731-UD-Q4_K_XL-00001-of-00005.gguf \
  --rpc 192.168.100.2:50052 \
  --n-gpu-layers 999 \
  --ctx-size 32768 \
  --flash-attn 1 --poll 0 -b 2048 -ub 512 \
  --jinja \
  --temp 1.0 --top-p 1.0 --min-p 0.01 \
  --host 0.0.0.0 --port 8000 \
  > /tmp/llama-server.log 2>&1 &'
```

- 第 1 shard を指定すれば残り 4 shard は自動で読まれる
- **サンプリングは unsloth 公式値**（`--temp 1.0 --top-p 1.0 --min-p 0.01`）。
  リポジトリの Qwen3.x 共通プロファイルは適用しない
- **`-ub 512 -b 2048` から始める**。13 デバイス分の compute buffer が VRAM を圧迫するため、
  既存 aws-gpu01 プロファイルの `-ub 4096` は初回では使わない（Qwen3.5-122B の
  fit プロファイルと同じ保守的な値から入り、VRAM 実測後に引き上げる）
- `--tensor-split` は**まず指定しない**（llama.cpp が空きメモリ比で自動配分する）。
  gpu02 の 12GB×2 が原因で偏りが出た場合のみ手動指定に切り替える
- 監視 UI は `.claude/skills/llama-server/scripts/ttyd-up.sh aws-gpu01` で別途立てる

### 6. 検証

```bash
# ヘルスチェック（ロード完了まで数分〜十数分かかる想定）
curl -s http://10.8.2.1:8000/health
# 実 VRAM
ssh aws-gpu01 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv"
ssh aws-gpu02 "nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv"
# 推論
curl -s http://10.8.2.1:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v4","messages":[{"role":"user","content":"日本語で自己紹介して"}],"max_tokens":256}'
```

確認する項目:

1. **13 デバイスすべてが認識されているか**（起動ログのデバイス一覧に `RPC[192.168.100.2:50052]` 系が 6 個出るか）
2. **CPU にフォールバックしたテンソル/op が無いか**（ログの buffer 割当と graph split 数）。
   `lightning_indexer` が sm_60 で CPU に落ちていれば tg が壊滅的に遅くなるので、ここが最重要
3. **VRAM 実測**と 12GB カードの偏り
4. **pp / tg（t/s）**をログの timing 行から採取（100GbE 越しの分散推論のコスト測定）
5. RDMA が効いているか（`GGML_RPC_DEBUG=1` を worker 側で有効化して確認、または
   モデル転送の所要時間から推定）

### 7. ctx を伸ばす（VRAM に余裕があれば）

32k で起動成功かつ VRAM に余裕があれば、`-ub` の引き上げ（512→1024→2048）と
ctx-size の引き上げ（32768→65536→131072）を段階的に試し、OOM する手前の値を記録する。

### 8. ドキュメント・レポート

- `.claude/skills/gpu-server/aws-gpu.md`: 「未検証事項」から llama-server 起動実績を消し、
  **100GbE / RDMA の実測値**と RPC 構成手順を追記
- `.claude/skills/llama-server/SKILL.md`: 「サーバ別最適化パラメータ」表の aws-gpu01/02 を
  実測値に更新し、**RPC 分散構成の節**（rpc-up.sh の使い方、バージョン一致の必須要件、
  バインドアドレスの制約）を追加。モデル一覧に DeepSeek-V4-Flash を追加
- `report/yyyy-mm-dd_hhmmss_deepseek_v4_rpc_dual_gpu_server.md` を REPORT.md の規約に従って作成
  （タイトル 50 字以内 / メタ情報 3 行 / `## 概要` を最上位に / 核心発見サマリ）。
  タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
  - `## 添付ファイル` に本プランファイルを `attachment/<レポート名>/plan.md` としてコピー・リンク（REPORT.md 必須要件）
  - **`## 残課題` に「DSpark（speculative decoding）を試す」を必ず書く** —
    draft モデル `dspark-DeepSeek-V4-Flash-0731-Q8_0.gguf`（10.9 GB、リポジトリルート）を
    `-md <draft> --spec-type draft-dspark --spec-draft-n-max 3 -ngl 99 -ngld 99` で使う。
    VRAM は +約 10 GB。今回計測した tg をベースラインとして改善幅を比較する
- `report/INDEX.md` に 1 行追加
- ロック解放（`unlock.sh` を両機）

---

## 主なリスクと対処

| リスク | 兆候 | 対処 |
|---|---|---|
| RPC プロトコル不整合 | worker 接続直後にエラー切断 | 両機を **同一 commit `10bf611e5`** でビルド（`--no-pull` を使う理由） |
| Pascal で新 op が CPU 落ち | tg が 1 t/s 未満、graph split 数が異常に多い | ログで確認し、**性能が出ない事実をレポートに記録**（llama.cpp 側の対応待ち。回避策は無い） |
| VRAM 不足 / OOM | ロード中に CUDA OOM | `-ub` を 512→256、ctx を 32768→16384、`--tensor-split` を手動で 12GB カードに合わせる |
| ビルド失敗（nvcc 12.0 × gcc 13） | nvcc の unsupported compiler エラー | `-DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-12` |
| ダウンロード中断 | `hf download` の停止 | `hf download` は再実行でレジュームする。gpu01 は HF 直結が速いので P100 の Xet 迂回策は不要 |
| gpu01 の RAM 逼迫 | 157 GiB RAM に対しモデル 144.4 GiB | mmap のまま使う（`--no-mmap` は付けない）。page cache は必要に応じて追い出される |

## やらないこと

- **電源操作**（両機とも稼働中。`llama-up.sh` / `llama-down.sh` は使わない）
- `/home/myzk` `/home/sizumita` への一切の変更
- gpu02 へのモデルファイル配置
- DSpark speculative decoding（今回スコープ外。**レポートの `## 残課題` に次回やることとして明記する**）
- `start.sh` / `llama-up.sh` への RPC 統合（成功構成確定後に別途判断）
