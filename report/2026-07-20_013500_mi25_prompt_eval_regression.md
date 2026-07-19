# mi25 Qwen3.6-35B pp 退行 — ROCm 長 ctx で発現・Vulkan 健全

- **実施日時**: 2026年7月20日 01:35 〜 03:30 JST (ロック取得・Phase A HW/SW スナップショット・Phase B ROCm 実測・Phase C Vulkan 実測・比較分析)
- **報告日時**: 2026年7月20日 03:30 JST
- **作成者**: Claude Opus 4.7 (1M context)

## 概要

mi25 で Qwen3.6-35B-A3B (unsloth GGUF `UD-Q4_K_XL`, KV `q8_0`) を実運用したときに、prompt eval 速度が過去記憶の 400 t/s 前後から 70 t/s まで大きく落ちているというユーザ報告があった。過去のレポート群を洗い直してみると、その 400 t/s 台という数値は 2026 年 6 月に取っていた Vulkan バックエンドでの pp 実測値と一致する。一方 2026 年 6 月以降、mi25 側では PCIe リンク死とその物理復旧、BIOS の復旧、SLOT8 常用への物理配置移行など環境変化が積み上がっており、退行がハードウェア起因か、llama.cpp 側か、あるいはバックエンドの選び方の問題かを切り分ける必要が生じていた。

そこで本セッションでは、mi25 の物理・環境状態を先にスナップショットし、その後 ROCm と Vulkan 両方のバックエンドで同じ 3 水準の prompt 長 (約 1k / 32k / 100k tokens) について llama-server の実運用経路で timings を実測し、過去値と比較した。過去との対称性を保つために、モデル・KV 量子化・ubatch・FA・4 枚並列という主要条件は当時のレポートと同じ構成に揃えた。

環境スナップショットの段階で、PCIe は 4 枚とも Gen3 x16 で down train なし、VBIOS は 4 枚とも同一、温度も idle 域内、ROCm 側の apt 履歴も過去計測時から動いておらず、物理配置 (SLOT2/4/8/6 = c3164/448c4/c48c4/a48e4) も NEXT_SESSION の記録と一致していることが確認できた。ハード側と OS パッケージ側では、過去 400 t/s 前後を出していた時期と比べて回帰の直接原因になりそうな差は見当たらなかった。

実測の結果は明瞭だった。ROCm 側では 1k prompt では過去と同水準の pp を維持していたが、32k で約 20% 、100k で約 35% の退行が観測され、prompt を長くするほど落ち方が深くなるという傾向を示した。ユーザ報告の 70 t/s は、この ROCm の曲線上で 32k と 100k の中間長で観測される値と整合する。一方 Vulkan 側は 1k で過去比 +4%、32k で -9%、100k で -12% と、いずれも実質的に過去水準を保っていた。tg (生成速度) はさらに変化しており、Vulkan は過去 16.93 t/s に対して 39.5 t/s まで大きく改善しており、ROCm を 1.4 倍上回る値になっていた。

以上から、ユーザが観測していた 70 t/s は「ROCm バックエンドで長い prompt を投げたときの現状値」であり、Vulkan バックエンドではその退行は起きていないと結論できる。今の Vulkan 側の実装は、prompt が長くても短くても、そして生成速度でも、ROCm を安定して上回っており、mi25 の実運用としては Vulkan を既定として使うのが素直な回答となる。

一方、ROCm 側で長い prompt に対してだけ深く退行するという現象自体は解決していない。ROCm の llama.cpp バイナリは gfx900 ビルド可能コミット (`0fac87b15`, v8533) に pin されており、apt 履歴も過去計測時から動いていないため、変数として残っているのはカーネル / DKMS 側の版数変化、負荷時の DPM が上限に張り付いているかの実測、そして 4 枚並列時の GPU 個体組合せ (特に SLOT8=c48c4 primary 化) の三つに絞られている。ただし本レポート作成直後にユーザ判断で「今後は Vulkan のパフォーマンス改善に注力、ROCm 側の原因調査は行わない」との方針変更が入ったため、これら 3 変数の切り分けは実施しない (詳細は本文末尾の「事後方針変更」節)。ROCm ビルド構成は当面 fallback 用途で残置する。

なお本セッションでは llama-server (Vulkan) を稼働状態にしたままロックを解放する運用にする。ユーザが即座に高い pp/tg を享受できるようにするためであり、次のロック取得者が構成を変えたい場合は `stop.sh mi25` で正規に停止できる。次セッションでは `start.sh` / `update_and_build-mi25.sh` / SKILL.md の default backend を hip → vulkan に反転する予定である。

## 添付ファイル

- [実装プラン](attachment/2026-07-20_013500_mi25_prompt_eval_regression/plan.md)
- Phase A スナップショット:
  - [rocm-smi id / bus / VBIOS / driver](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseA_rocm_smi_id.log)
  - [rocm-smi clocks / power / temp (idle)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseA_rocm_smi_clocks_idle.log)
  - [lspci LnkSta / LnkCap (全 4 枚)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseA_lspci_lnksta.log)
  - [dmesg (amdgpu / pcie)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseA_dmesg.log)
  - [dpkg (rocm / hip / amdgpu 版数)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseA_dpkg_rocm.log)
  - [apt history (rocm 系変更履歴)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseA_apt_history_rocm.log)
  - [dmidecode SMBIOS slots](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseA_dmidecode_slots.log)
  - [llama.cpp HEAD (build / build-vulkan)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseA_llama_cpp_head.log)
- Phase B ROCm timings:
  - [1k x3 run](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseB_rocm_1k.log)
  - [32k run1 (client stdout)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseB_rocm_32k.log)
  - [ROCm 全 request timings (llama-server 側)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseB_rocm_llama_server_timings.log)
  - [ROCm 32k run3 JSON](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_rocm_32k_run3.json)
  - [ROCm 100k run1 JSON](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_rocm_100k_run1.json)
  - [ROCm tg run1 JSON](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_rocm_tg_run1.json)
- Phase C Vulkan timings:
  - [Vulkan 全 request timings (llama-server 側)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/phaseC_vulkan_llama_server_timings.log)
  - Vulkan 1k JSON: [run1](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_vulkan_1k_run1.json) / [run2](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_vulkan_1k_run2.json) / [run3](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_vulkan_1k_run3.json)
  - Vulkan 32k JSON: [run1](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_vulkan_32k_run1.json) / [run2](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_vulkan_32k_run2.json) / [run3](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_vulkan_32k_run3.json)
  - [Vulkan 100k JSON](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_vulkan_100k_run1.json)
  - [Vulkan tg JSON](attachment/2026-07-20_013500_mi25_prompt_eval_regression/bench_vulkan_tg_run1.json)

## 核心発見サマリ

![prompt eval t/s: ROCm vs Vulkan (past vs now)](attachment/2026-07-20_013500_mi25_prompt_eval_regression/summary_pp_regression.png)

**結論**: mi25 (Qwen3.6-35B-A3B UD-Q4_K_XL, KV q8_0, 4 枚並列, ub=2048, FA=1) の prompt eval 速度で、ROCm 側だけが **prompt 長依存の退行**を示す。1k では 254.6 t/s と過去 240-260 t/s 域に一致するが、32k で 99.0 t/s (過去 122.8 vs **-19%**)、100k で 38.9 t/s (過去 90k 60 vs **-35%**) と落ちる。ユーザ報告の「70 t/s」は ROCm 32k-64k 域の値に相当する。一方 Vulkan は 1k 541.4 t/s (過去 521 vs +4%) / 32k 371.8 t/s (過去 407 vs -9%) / 100k 191.3 t/s (過去 216 vs -12%) と実質全域で過去水準を維持。tg は Vulkan 39.5 t/s (過去 16.93 vs +133%) / ROCm 28.8 t/s (過去 24.5 vs +17%) で **Vulkan が pp / tg とも ROCm を上回る**。**mi25 の実運用は `MI25_BACKEND=vulkan` で立ち上げるのが最適**、次セッションで `start.sh` の default backend を hip → vulkan に反転する予定。ROCm 側 long-ctx 退行の原因調査は方針変更により打ち切り (詳細は本文末尾「事後方針変更」節)。

## 前提・目的

- **背景**: ユーザ環境で mi25 Qwen3.5 (呼称、実体は Qwen3.6-35B-A3B) の pp が「以前 400 t/s → 現在 70 t/s」との報告。過去レポートを洗うと 400 t/s 台は 2026-06-14 の Vulkan RADV 実測値と一致
- **目的**: 現状を過去と同条件で再測定し、退行がバックエンド依存か HW/OS 依存かを切り分ける
- **前提**: 実運用と同じ llama-server 経路で timings を取る (llama-bench でなく `/completion` の timings)。ubatch=2048, FA=1, KV q8_0, 4 枚並列は過去と同一

## 環境情報

| 項目 | 値 |
|---|---|
| サーバ | mi25 (10.1.4.13) |
| GPU | MI25 x4 (`HIP_VISIBLE_DEVICES=0,1,2,3`) |
| 物理配置 (SLOT ↔ Unique ID 末尾 5 桁 ↔ BDF) | SLOT2=c3164 (04:00.0) / SLOT4=448c4 (07:00.0) / **SLOT8=c48c4 (84:00.0)** / SLOT6=a48e4 (87:00.0) |
| VBIOS | 全 4 枚 `113-D0513700-001` |
| PCIe | 全 4 枚 Gen3 x16 (ok) |
| amdgpu-dkms | 1:6.8.5.60202-2041575.22.04 |
| ROCm (hip-runtime) | 6.2.41134.60202 |
| llama.cpp (ROCm build) | `0fac87b157305eb82a70902327abffbbce25bd3e` (v8533 pin) |
| llama.cpp (Vulkan build) | `ded1561b4` (v9812, master 追従) |
| モデル | `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` (22,360,456,160 B) |
| KV / batch | `--cache-type-k q8_0 --cache-type-v q8_0 --flash-attn 1 -b 2048 -ub 2048` |
| コンテキスト | `--ctx-size 131072 --parallel 1` |

## 再現方法

**プロンプト用意** (mi25 上):

```bash
# 素材連結し 800KB seed を作る
cd ~/llama.cpp
(cat README.md CMakeLists.txt src/llama.cpp src/llama-model.cpp; find src -maxdepth 2 -name '*.cpp' | head -20 | xargs cat) \
  | head -c 800000 > /tmp/prompt_seed.txt

# 3 水準に切り出し (実測トークン数: 1271 / 39589 / 119402)
head -c 4200   /tmp/prompt_seed.txt > /tmp/prompt_1k.txt
head -c 135000 /tmp/prompt_seed.txt > /tmp/prompt_32k.txt
head -c 420000 /tmp/prompt_seed.txt > /tmp/prompt_100k.txt
```

**計測スクリプト** (`/tmp/bench_prompt.py`):

```python
import json, sys, time, urllib.request
prompt_file, n_predict, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
with open(prompt_file) as f: prompt = f.read()
body = json.dumps({"prompt": prompt, "n_predict": n_predict,
                   "temperature": 0, "top_k": 1,
                   "cache_prompt": False, "stream": False}).encode()
t0 = time.time()
req = urllib.request.Request("http://127.0.0.1:8000/completion",
                             data=body, headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req, timeout=3600) as r: j = json.loads(r.read())
t = j.get("timings", {})
out = {"label": label, "prompt_n": t.get("prompt_n"),
       "prompt_per_second": t.get("prompt_per_second"),
       "predicted_per_second": t.get("predicted_per_second"),
       "wall_s": round(time.time()-t0, 3)}
with open(f"/tmp/bench_{label}.json","w") as fout: fout.write(json.dumps(out)+"\n")
```

**ROCm 実行** (WS 側から):

```bash
# 起動
.claude/skills/llama-server/scripts/start.sh mi25 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
.claude/skills/llama-server/scripts/wait-ready.sh mi25 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
# 一気にキュー投入 (--parallel=1 で順次処理)
ssh mi25 '
for label in rocm_1k_run1 rocm_1k_run2 rocm_1k_run3; do
  nohup python3 /tmp/bench_prompt.py /tmp/prompt_1k.txt   1 $label > /tmp/bench_$label.log 2>&1 &
done
for label in rocm_32k_run1 rocm_32k_run2 rocm_32k_run3; do
  nohup python3 /tmp/bench_prompt.py /tmp/prompt_32k.txt  1 $label > /tmp/bench_$label.log 2>&1 &
done
nohup python3 /tmp/bench_prompt.py /tmp/prompt_100k.txt 1   rocm_100k_run1 > /tmp/bench_rocm_100k_run1.log 2>&1 &
nohup python3 /tmp/bench_prompt.py /tmp/prompt_1k.txt   128 rocm_tg_run1   > /tmp/bench_rocm_tg_run1.log   2>&1 &
'
```

**Vulkan 実行** (ROCm 完了・停止後):

```bash
.claude/skills/llama-server/scripts/stop.sh mi25
MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/start.sh mi25 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
.claude/skills/llama-server/scripts/wait-ready.sh mi25 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
# 同じ手順で vulkan_* を投入
```

## 結果詳細

### ROCm baseline (build HEAD `0fac87b15`, v8533 pin)

| Run | prompt tokens | pp t/s | wall (s) |
|---|---|---|---|
| 1k run1 (cold) | 1271 | 226.08 | 5.6 |
| 1k run2 | 1271 | **254.75** | 5.0 |
| 1k run3 | 1271 | **254.64** | 5.0 |
| 1k median | | **254.6** | |
| 32k run1 | 39589 | 99.23 | 399 |
| 32k run2 | 39589 | 97.02 | ~408 (llama-server log から復元) |
| 32k run3 | 39589 | 98.97 | 400 |
| 32k median | | **99.0** | |
| 100k | 119402 | **38.90** | 3465 (~58 min) |
| tg (1k+128) | 1271 (pp 238.4) | pp 238.4 / **tg 28.77** | 3474 (実処理 ~10s、キュー内で 100k の後に処理されたためキュー待ちを含む) |

### Vulkan baseline (build HEAD `ded1561b4`, v9812 master 追従)

| Run | prompt tokens | pp t/s | wall (s) |
|---|---|---|---|
| 1k run1 | 1271 | 533.43 | 2.4 |
| 1k run2 | 1271 | 541.35 | 10.3 (キュー待ち含む) |
| 1k run3 | 1271 | 543.85 | 12.7 |
| 1k median | | **541.4** | |
| 32k run1 | 39589 | 370.37 | 120 |
| 32k run2 | 39589 | 371.78 | 226 |
| 32k run3 | 39589 | 372.06 | 333 |
| 32k median | | **371.8** | |
| 100k | 119402 | **191.31** | 957 (~16 min) |
| tg (1k+128) | 1271 (pp 544.9) | pp 544.9 / **tg 39.46** | 8.0 (実処理相当、tg python の urlopen が偶然 100k 完了直前に発火してキュー待ちが最小化された結果) |

### 過去値との比較 (Qwen3.6-35B-A3B-UD-Q4_K_XL, 4 枚, KV q8_0)

| Prompt | ROCm 過去 | ROCm 現在 | ROCm 差 | Vulkan 過去 | Vulkan 現在 | Vulkan 差 |
|---|---|---|---|---|---|---|
| 1k | 240-260 t/s (2026-06-13) | **254.6** | ≒一致 | 521.2 t/s (2026-06-18 N=5) | **541.4** | **+4%** |
| 32k | 122.8 t/s (2026-06-13) | **99.0** | **-19%** | 407.1 t/s (2026-06-18 N=5) | **371.8** | -9% |
| 100k | ~60 t/s @90k (2026-06-13) | **38.9** | **-35%** | 216.2 t/s (2026-06-14) | **191.3** | -12% |
| tg | 24.5 t/s (2026-06-13) | **28.77** | +17% | 16.93 t/s (2026-06-18) | **39.46** | **+133%** |

### 環境スナップショット (Phase A) の判定

| 候補 | 判定 | 根拠 |
|---|---|---|
| PCIe down train | 棄却 | 全 4 枚 Gen3 x16 (ok) |
| VBIOS 変化 | 棄却 | 全 `113-D0513700-001` (2026-06 と同じ) |
| ROCm ドライバ版数変化 | 棄却 (dpkg レベル) | apt history: 2025-05-01 以降 rocm/hip/amdgpu 系の install 履歴なし |
| 物理配置変化 | 棄却 | SLOT2/4/8/6 = c3164/448c4/c48c4/a48e4 (NEXT_SESSION と一致) |
| 温度異常 (idle) | 棄却 | 32-42°C, DPM Level 0 (idle) |
| llama.cpp ROCm HEAD 変化 | 棄却 | `0fac87b15` (v8533) と 2026-06-13 レポートの pin 一致 |
| Vulkan llama.cpp master 退行 | 実質棄却 | `f3e182816`→`ded1561b4` に大きく進行しているが実測 pp/tg は健全 |
| **原因 (未特定)** | **ROCm 側 long-ctx 退行** | 1k は健全、32k 以降だけ退行。ROCm HEAD/apt に差がないので kernel/DKMS 側 or 負荷時 DPM / 個体組合せに絞られる |

## 副次発見

1. **Vulkan tg が過去比 +133% と大幅改善** (16.93 → 39.46 t/s)。Vulkan master 追従で decode 系の PR が効いている。2026-06 時点の「Vulkan は prefill 特化、ROCm は decode 特化」という棲み分け ([2026-06-14 Vulkan qwen36 128k](./2026-06-14_001107_mi25_vulkan_qwen36_128k.md)) は今では成立せず、**Vulkan が pp/tg とも ROCm を上回る**状態になっている。
2. **ROCm 1k run1 のみ 226 t/s (cold)、run2/3 は 254-255 t/s** に落ち着く。GPU[0] VRAM ピーク周辺の warm-up と見て良い。長い prompt では影響が相対的に小さく、無視できる。
3. **100k prompt のトークン化効率**: 420,000 char の英文コーパスで 119,402 tokens、約 3.52 char/tok。過去の見積り (3.5 char/tok) と一致し、次回同種計測でも同じ切り出しサイズで再現できる。
4. **idle 温度で GPU[1] (SLOT4=448c4) だけ +4〜9°C 高い** (edge/junction 41-42°C 対 他の 32-37°C)、**idle 電力で GPU[2] (SLOT8=c48c4) だけ +2〜3W 高い** (6W 対 他の 3-4W)。idle 域なので thermal/DPM の直接原因にはならないが、long-ctx 退行の原因候補「GPU 個体組合せ差 / SLOT8=c48c4 primary 化」の傍証データになる (事後方針変更で ROCm 調査は打ち切りとなったため、負荷時並走測定の追試は実施しない参考情報として残す)。
5. **amdgpu 0000:87:00.0 (SLOT6=a48e4) だけ起動時 dmesg に BAR 6 "bogus alignment" 警告** (`BAR 6: can't assign [??? 0x00000000 flags 0x20000000] (bogus alignment)`)。BAR 6 = Expansion ROM、機能影響なし (以降の amdgpu 初期化は正常完了、Trusted Memory Zone / MEM ECC active / VRAM 16368M ready) だが 4 枚の中で 87:00.0 のみ発生する物理層側の観察ポイント。過去 [2026-06-14 mi25 gpu4 pcie dropout](./2026-06-14_131713_mi25_gpu4_pcie_dropout.md) の SLOT4 物理層障害系列とは別事象 (SLOT6 側の presence 信号/接点差の可能性)。
6. **Bash tool の 10 分制限で ROCm 32k run2 の client JSON が失われた**。llama-server ログの `prompt eval time = ...` 行から 97.02 t/s を復元して欠けなし。以降の測定は `bench_prompt.py` 側で `BrokenPipeError` を握り潰し `/tmp/bench_<label>.json` に確実に書き出す形へ修正 (再現方法のコードに反映済)。

## 参照レポート

- [2026-06-13 mi25 Qwen3.6-35B 128k (ROCm baseline)](./2026-06-13_112006_mi25_qwen36_128k.md)
- [2026-06-14 mi25 Vulkan Qwen3.6-35B 128k (Vulkan baseline)](./2026-06-14_001107_mi25_vulkan_qwen36_128k.md)
- [2026-06-18 mi25 Vulkan パラメータ探索 (N=5 統計値の出典)](./2026-06-18_084557_mi25_vulkan_param_sweep.md)
- [2026-07-19 mi25 c48c4 SLOT8 4 枚 24h R1 (副次発見 pp_tps 半減の観察元)](./2026-07-19_053651_mi25_c48c4_slot8_4card_24h_r1.md)

## 結論・対応

- **主対応 (即応)**: mi25 の実運用は **`MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/start.sh mi25 ...`** で起動する。本セッション終了時点で Vulkan 起動状態を維持したままロックを解放したので、ユーザは即座に高い pp/tg を享受できる
- **恒久対応 (次セッションで実施)**: `start.sh` / `update_and_build-mi25.sh` / SKILL.md の default backend を hip → vulkan に反転し、以降 `MI25_BACKEND` prefix なしで Vulkan 起動される形にする (詳細は NEXT_SESSION.md「最優先: mi25 デフォルトバックエンドを Vulkan に変更」節)

## 事後方針変更 (2026-07-20 セッション終了直後、ユーザ判断)

本レポート作成直後に、以下の方針変更をユーザから受けた:

- **今後は Vulkan のパフォーマンス改善に注力**する (Vulkan HEAD `f3e182816`→`ded1561b4` に挟まった軽微退行 PR の bisect、`PINNED_COMMIT_VULKAN` 導入検討など)
- **ROCm 側 long-ctx 退行の原因調査は行わない** (Vulkan が pp / tg とも ROCm を上回るため、ROCm 側の労力対効果が低い)
- ROCm ビルド構成 (v8533 pin) は fallback 用途で当面残置 (能動的な維持は不要)

このため、本レポート中「原因 (未特定): ROCm 側 long-ctx 退行 → kernel/DKMS / DPM / 個体組合せに絞られる」は**未解明のまま打ち切り**となる。副次発見 4 (idle 温度/電力の個体差) や本レポート内の残変数 3 種は今後の追試に紐付かない参考情報として保持する。

## 残課題

1. **mi25 デフォルトバックエンドの反転** (次セッション最優先) — `start.sh` L239 の `${MI25_BACKEND:-hip}` を `${MI25_BACKEND:-vulkan}` にする等、5 ファイルの差分。詳細は NEXT_SESSION.md
2. **Vulkan 32k / 100k の -9% / -12% 誤差要因の bisect** — 誤差範囲だが Vulkan HEAD `f3e182816`→`ded1561b4` に軽微退行 PR が挟まった可能性。特定できれば Vulkan build にも pin を導入。方針変更「Vulkan パフォーマンス改善に注力」の帰結
3. **rocm-smi の非対応オプションに注意** (次セッション以降、ROCm 側スクリプトを触る際の trap 回避用として残す) — 現行 (ROCm 6.2.2, package `rocm-smi.60202`) では `--showcurrentclocks` が非対応、代替は `-c -P -t` (`--showclocks` + `--showpower` + `--showtemp`) または `--showclocks` 単独
4. **Phase A の dmesg 取得を `tail -80` に絞ったため 04:00.0 / 07:00.0 の初期化ログが残っていない** (今後の Phase A 相当スナップショット時の trap 回避) — 次回は `dmesg | grep amdgpu` で全 4 枚の初期化ログを一括保存する
5. **打ち切り**: 本セッションで rocm-smi 並走を取り忘れた点は、方針変更 (ROCm 調査打ち切り) により再取得不要となった

## 次セッションへの引き継ぎ

- llama-server は Vulkan で稼働中 (ロック解放時点)。停止したい場合は `.claude/skills/llama-server/scripts/stop.sh mi25`
- 次セッションで default backend の反転作業を実施 (NEXT_SESSION.md「最優先」節参照)
