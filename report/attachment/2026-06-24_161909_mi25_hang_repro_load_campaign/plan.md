# mi25 ハング再現・条件特定 負荷試験

## Context（背景・目的）

opencode の feature-bench（run_id=m31）実行中、mi25（10.1.4.13）が **trial 2 の build フェーズ
で全体ハードハング**した（BMC電源ONだが ping/SSH不達・llama `/health=000`）。レポート:
`http://10.1.6.4:5032/opencode/report/2026-06-21_232002_feature_bench_m31p100.md/raw`。

事象の要点（レポート＋ハング記録より）:
- 構成: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` / 131072 ctx / **ROCm(hip) backend**（pin `0fac87b15`、ub=2048/FA）。
- ハング時の **context は 15.0K(11%) と小さく**、フルコンテキスト枯渇ではない。
- 起動時に「**実効 GPU 3枚/期待4枚・GPU脱落の可能性**」警告。最有力原因は **GPU脱落（SLOT4 の
  PCIe物理層障害, 既知）と整合する ROCm/GPUドライバ起因のカーネルハング**。
- 現状: mi25 は **電源OFF**。前回ハングで GPU ロックファイルが **stale 残存**（要 `unlock.sh mi25`）。

**目的**: mi25 に opencode 利用を模した連続推論負荷を繰り返しかけ、ハングの**再現性・発生条件・
カーネル signature** を統計的に特定する。試験後は mi25 をシャットダウンする。

**確定した方針（ユーザ確認済み）**:
1. バックエンド: **ROCm → Vulkan の2フェーズ比較**（「ROCm固有か」を切り分け）。
2. 1試行の負荷: **実ワークロード相当（約8〜15分/試行の連続推論）**。
3. ハング時: **KVMスクショ→BMCリセット→復帰→継続**（統計重視。発生率・条件・時間分布を採取）。

> opencode ハーネス本体はこのマシンに無いため、OpenAI互換APIへ **opencode の build フェーズを
> 模した合成負荷**（多ターンのコーディング会話）を用いる。GPU/ドライバ起因ハングに効く変数は
> 「ROCm連続推論の継続」であり、合成負荷で十分に再現条件を突けると判断（前提として明記）。

---

## 試験アーキテクチャ

**制御ホスト = このマシン**。負荷も計測も電源制御もここから行い、**全ログをローカルに保存**する
（mi25 が freeze してもフリーズ直前までのデータが残る）。作業ディレクトリは scratchpad 配下。

```
[このマシン] --HTTP(負荷)--> mi25:8000/v1   (load_driver.py)
            --SSH(計測ストリーム)--> mi25     (rocm-smi=10s毎 / dmesg=常時 をローカル追記)
            --IPMI(電源/KVM)--> 10.1.4.7      (bmc-power.sh / bmc-screenshot.sh)
```

ロック・電源・起動はすべて **プロジェクトルートからの相対パス**でスキルスクリプトを使用
（CLAUDE.md 制約）。**ロック/アンロックは SSH 経由で mi25 上のロックファイルを操作する**ため、
mi25 が**起動済み（SSH 疎通可）でないと実行できない**点に注意（→ Phase0 の順序で担保）。
**sudo**: 本セッションは mi25 で **パスワードなし sudo 利用可（ユーザ承認済み）**。`rocm-smi`/`rocminfo`
は一般ユーザで実行可。カーネルメッセージ制限がかかっていても `ssh mi25 "sudo dmesg -w"` /
`sudo journalctl -k` でフルに採取する。なお**パニックトレースの一次採取は OOB で確実な KVM スクショ**が
担うため、kernel-log ストリームはそれを補強する二重化（ホスト凍結直前の amdgpu エラーを文字列で取得）。

---

## 実行手順

### Phase 0: 準備・プリフライト
> **順序が重要**: ロック操作は SSH 経由のため、**先に mi25 を電源ON**してからでないと unlock/lock
> できない（現状 mi25 は OFF・前回ハングの stale ロックが mi25 ディスク上に残存）。
1. **電源ON**: `bmc-power.sh mi25 on` → SSH 疎通待ち（最大5分ポーリング）。
   （電源ONはロック取得前だが、mi25 は OFF で他セッション専有なし＝ON 自体は無害。ON 直後に
   ロックを取得して以降を専有する。下げ/リセット操作はすべてロック保持下で行う。）
   `lock-status.sh` で stale ロックの保持者を確認。
2. **ロック整理**: `unlock.sh mi25`（前回 stale を掃除。mi25 の /tmp は**永続**でロックが残存するため
   必須。reset 後も同様に残存するので Phase2 step4 でも unlock→lock で取り直す）→ `lock.sh mi25` で取得。
3. **起動**: `llama-up.sh mi25 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072`（ROCm既定。電源は
   既にONなので llama-up は冪等にllama起動のみ。ROCm hip は `0fac87b15` に **pin**＝レポートのハング
   発生commitと一致するため忠実に再現できる）。
   - 起動ログの **GPU枚数警告（実効3/4）を必ず記録**。`ssh mi25 "rocminfo | grep -c gfx900"` で枚数確定。
   - **【ブート状態記録（必須）】各起動・各再起動の直後に下記を `boot_state.log` に記録**:
     - **認識GPU枚数**: `rocminfo | grep -c gfx900`（ROCm視点）＋ `rocm-smi --showid` のGPU列挙。
     - **各GPUの電力制限(power cap)**: `rocm-smi --showmaxpower`（= 各GPUの電力上限値, Max Graphics
       Package Power）を **GPU毎**に記録。ブート間で cap が変わる可能性を追跡する（現在の消費電力は
       Phase1 のテレメトリで別途連続採取）。
     - epoch・ブート連番（初回 / N回目のreset後）・warm reset か cold cycle か も併記。
4. **ベースライン保全**: `bmc-screenshot.sh mi25 <scratch>/baseline.png`、`ssh mi25 "sudo dmesg | tail"`、
   `journalctl` の永続化有無を確認（`ssh mi25 "ls /var/log/journal"`。永続なら再起動後に
   `sudo journalctl -b -1` で前ブートのカーネルトレースを採取可能）。
5. `/health`・1発の疎通推論で正常応答を確認。

### Phase 1: 計測ストリーマ起動（バックグラウンド, ローカル保存）
制御ホスト側のループから 10秒毎に SSH して**ローカルファイルに追記**（freeze 時に gap が記録される）:
- `telemetry_rocmsmi.log`: `rocm-smi`（温度・電力・VRAM・クロック・fan・利用率, GPU毎）+ epoch。
- `telemetry_gpucount.log`: `rocminfo | grep -c gfx900`（3⇄4 脱落の追跡）。
- `kern_dmesg.log`: 長寿命 `ssh mi25 "sudo dmesg -w"`（必要なら `sudo journalctl -k -f`）を1本張って
  ローカルへ（amdgpu ring timeout / VM page fault / GPU reset / PCIe AER / soft lockup を捕捉）。
- `llama_server.log`: llama-server ログの tail。

### Phase 2: 負荷試行ループ（ROCm フェーズ）
`load_driver.py`（合成 opencode 負荷）を作成。**1試行 = 多ターンのコーディング会話**:
- system prompt は AGENTS 風に大きめ、user は bench と同テーマ（Rails の search / pagination /
  disk-usage 実装）を指示、assistant 出力を会話に積んで反復。
- sampler は bench と同一: `temperature=0.6, top_p=0.95, top_k=20, min_p=0`（presence_penalty は
  サーバ既定 1.0）。各ターン `max_tokens` ~1500-2500。
- **1試行の wall-clock が ~8〜15分に達するまでターンを継続**（実ワークロード相当の連続推論）。
- 記録（JSONL）: trial#・turn#・latency・prompt/completion tokens・tok/s（pp/eval）・finish_reason・
  HTTP status・累積context・epoch。

**停止条件**: 統計重視のためハングは抑止せず採取する。`min 10 試行`を下限に、`30試行 到達` または
`フェーズ wall-clock 6h` のいずれか早い方で ROCm フェーズ終了（いずれも設定可・ユーザ中断可）。
ただし**反復 reset による FS 破損は実害リスク**のため、`ハング3回` を**安全境界**として設け、到達
時はフェーズを即終了せず**ユーザに状況報告して継続可否を確認**する（ハング自体はデータなので捨てない）。

**ハング検出**: 推論がタイムアウト/`/health=000` かつ `ping` 不達 かつ `ssh` 不達 を**三点確認**で
ホストハング判定（単なる遅延と区別）。検出時:
1. **先に `bmc-screenshot.sh mi25 <scratch>/hang_NN.png`**（コンソールのパニックトレース保全。
   CLAUDE.md: リセット前に必ずKVMスクショ）。
2. 記録: trial#/turn#・経過時間・直前テレメトリ（温度/電力/VRAM/クロックのピーク）・context量・
   直前リクエスト種別。
3. **復旧**: `bmc-power.sh mi25 reset`（warm）→ SSH復帰待ち → **Phase0-2のブート状態記録を再実行**
   （`rocminfo` gfx900枚数 ＋ 各GPUの power cap を `boot_state.log` に追記。warm/cold とブート連番も）。
   復帰失敗 or 枚数低下なら `bmc-power.sh mi25 cycle 20`（コールド, メモリ既知: cold で3枚復帰実績）に
   エスカレーション。`sudo journalctl -b -1` で前ブートのカーネルトレースを採取（永続journalの場合）。
4. stale ロック掃除（`unlock.sh`→`lock.sh`）→ llama 再起動 → 試行ループ再開（試行カウンタ継続）。

### Phase 3: Vulkan フェーズ（比較）
`llama-down.sh mi25` → `MI25_BACKEND=vulkan llama-up.sh mi25 "<model>" 131072`（RADV 物理GPUは
start.sh が自動検出）→ Phase 1-2 と**同一負荷・同一検出・同一記録**を実施。ROCm固有か切り分け。

### Phase 4: 解析・レポート
[REPORT.md](../../projects/llm-server-ops/REPORT.md) フォーマットで作成。核心発見サマリに主要図(PNG)を
冒頭埋め込み。解析軸:
- **再現性**: backend別ハング回数・試行到達数(trial-to-hang)・時間到達分布(time-to-hang)。
- **カーネル signature 分類**: dmesgストリーム＋KVMスクショから amdgpu ring gfx timeout / VM page
  fault / GPU reset failed / PCIe AER(Bus error) / soft lockup / NMI を分類。
- **相関**: ハング vs **起動時GPU枚数(3/4)** / **各GPUの電力制限(power cap)のブート間変動** /
  温度・電力ピーク / リクエスト種別・context量 / backend(ROCm vs Vulkan)。
- **ブート状態テーブル**: ブート連番ごとに 認識枚数・各GPU power cap・warm/cold・続くハング有無を一覧化。
- **スループット参考値**: backend別 pp/eval t/s。
- **復旧特性**: warm reset vs cold cycle の有効性、脱落(3枚)の再発有無。
- **結論**: ハングは「負荷誘発の再現事象」か「ランダムなPCIe物理層障害」か。ROCm固有か backend非依存か。

### Phase 5: 後片付け・シャットダウン
1. 負荷・テレメトリ停止。
2. `llama-down.sh mi25`（両backend分の後始末）。
3. **mi25 シャットダウン**: `power-ctl.sh mi25 off`（ACPI graceful, soft）→ `bmc-power.sh mi25 status`
   で **Off 確認**。ハングのまま終わった場合のみ ACPI 不可なので `bmc-power.sh mi25 off`（ハード）。
4. `unlock.sh mi25` でロック解放（ハング後の stale も掃除）。

---

## 作成・利用するファイル

| 種別 | パス | 役割 |
|------|------|------|
| 負荷ドライバ(新規) | `<scratch>/load_driver.py` | 合成 opencode 多ターン負荷・JSONL記録・ハング三点検出 |
| テレメトリ収集(新規) | `<scratch>/telemetry.sh` | 10s毎 SSH で rocm-smi/枚数/dmesg をローカル追記 |
| オーケストレータ(新規) | `<scratch>/run_campaign.sh` | Phase0-3 を駆動・ハング時の screenshot→reset→復帰→再開 |
| 既存(利用) | `.claude/skills/gpu-server/scripts/{lock,unlock,lock-status}.sh` | ロック管理 |
| 既存(利用) | `.claude/skills/gpu-server/scripts/bmc-power.sh` / `bmc-screenshot.sh` | KVMスクショ・電源/リセット |
| 既存(利用) | `.claude/skills/gpu-server/scripts/power-ctl.sh` | graceful shutdown |
| 既存(利用) | `.claude/skills/llama-server/scripts/{llama-up,llama-down}.sh` | 起動・停止（backend切替は `MI25_BACKEND`） |

> 長時間実行のため `run_campaign.sh` はバックグラウンド実行＋進捗ログ、TaskCreate で進捗追跡。
> ユーザはいつでも中断可（中断時も Phase 5 のシャットダウンを実施）。

## 検証（動作確認）
- プリフライト推論1発で `/health 200` と正常応答を確認してから本ループ開始。
- ハング検出ロジックは「正常な長遅延」を誤検出しないよう三点確認（health+ping+ssh）でガード。
- 各 reset 後に `rocminfo` 枚数と `/health` 復帰を確認してから試行再開。
- 終了時に `bmc-power.sh mi25 status` が **Off** を返すことを確認。

## 注意・リスク
- **ビルド/pin の挙動（正確に）**: `update_and_build-mi25.sh` は backend で分岐する。
  - **hip（ROCm, Phase2）**: `git fetch` + `git checkout 0fac87b15`（**pin**）。build/ が既存で HEAD 不変
    ならビルドをスキップ。**この pin はレポートのハング発生 commit と一致**＝忠実な再現。master 追従
    しないのでビルド破損リスクはない。
  - **vulkan（Phase3）**: `git checkout master` + `git pull --ff-only` で **master 追従**しビルド
    （build-vulkan/）。vulkan は hip.h を device コンパイルしないため FP8 リグレッションの影響外。
    万一 master HEAD がビルド失敗した場合は記録して **vulkan フェーズをスキップ**し、ROCm 結果のみで
    レポートする（試験全体は破綻しない）。
- 反復ハング→reset の繰り返しで FS 破損リスク（過去に ext4 ジャーナル破損実績）。各復帰時に
  `/health` とマウント健全性を軽く確認。重大破損時はユーザに報告し継続可否を判断。
- 物理層障害（SLOT4）は遠隔修復不可。3枚(48GB)構成でもモデルは収まるため試験は継続可能。
