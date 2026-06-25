# 収集データ(生ログ要約)

## ベースライン(負荷前・idle)

```
COUNT=4
UPTIME= 12:16:42 up  3:46
PORT 00:02.0 = Width x16 Speed 8GT/s PresDet+ AER(cor=0 fatal=0 nonfatal=0)
PORT 00:03.0 = Width x16 Speed 8GT/s PresDet+ AER(cor=0 fatal=0 nonfatal=0)
PORT 80:02.0 = Width x16 Speed 8GT/s PresDet+ AER(cor=0 fatal=0 nonfatal=0)
PORT 80:03.0 = Width x16 Speed 8GT/s PresDet+ AER(cor=0 fatal=0 nonfatal=0)
GUIDS_ALIVE= 29525 33301 54068 8820
```

物理層は原 ROCm レポート([2026-06-25_094641](../../2026-06-25_094641_mi25_4card_load_gpuvm_fault.md))と同一構成。負荷投入は 12:27 (uptime ≈ 13917s)。

## スロット↔ルートポート↔BDF↔GUID↔Vulkan index↔HIP index 対応

| 物理スロット | ルートポート | GPU BDF | GUID | Vulkan index | HIP index | KFD node | 役割 |
|---|---|---|---|---|---|---|---|
| CPU1 SLOT2 | 00:02.0 | 04:00.0 | 29525 | 0 | 0 | 2 | safe |
| CPU1 SLOT4 | 00:03.0 | 07:00.0 | 33301 | 1 | 1 | 3 | safe(旧villain復帰) |
| CPU2 SLOT8 | 80:02.0 | 84:00.0 | 54068 | 2 | 2 | 4 | safe |
| **CPU2 SLOT6** | **80:03.0** | **87:00.0** | **8820** | **3** | **3** | **5** | **本件フォルト元** |

- Vulkan index は `vulkaninfo` の PCI bus 昇順で割り当てられ HIP index と一致した。
- llvmpipe(CPU)は Vulkan index 4 として末尾に列挙されるため、起動時 `GGML_VK_VISIBLE_DEVICES=0,1,2,3` で除外される(`start.sh` の `detect_radv_vk_indices()`)。
- 切り分け用デバイスマスクは HIP index と数値が一致するため、原 ROCm 切り分けと同じ index 列を使う:
  - 4枚 all: `0,1,2,3`
  - 3枚 excl 8820: `0,1,2`
  - 3枚 incl 8820 (= 33301除外): `0,2,3`

## キャンペーン構成と結果一覧

各フェーズ共通: モデル `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`、ctx=131072、`--flash-attn 1 --poll 0 -b 2048 -ub 2048 --cache-type-k q8_0 --cache-type-v q8_0`、`split-mode layer`。バイナリは `~/llama.cpp/build-vulkan/bin/llama-server`(master 追従、Vulkan/RADV)。

| 構成 | デバイスマスク | 完了試行 | 連続稼働 | 結果 | 備考 |
|---|---|---|---|---|---|
| 4枚 all (Phase 1) | `GGML_VK_VISIBLE_DEVICES=0,1,2,3` | **3/12 完走 + 9 空回り** | **2208s** (trial 4 冒頭でフォルト) | **8820 GPU reset** | trial 1 = 726s / trial 2 = 733s / trial 3 = 749s |
| 3枚 excl 8820 (Phase 2A) | `GGML_VK_VISIBLE_DEVICES=0,1,2` | 3/3 完走 | 2210s | **クリア (control)** | trial 1 = 754s / trial 2 = 734s / trial 3 = 722s |
| 3枚 incl 8820 (Phase 2B) | `GGML_VK_VISIBLE_DEVICES=0,2,3` | **3/3 完走** | **2307s** | **クリア (8820含むのに安定)** | trial 1 = 779s / trial 2 = 743s / trial 3 = 785s |

### ROCm 結果との対比(原レポート 2026-06-25_094641 より)

| 構成 | バックエンド | 連続稼働 | 結果 | フォルト signature |
|---|---|---|---|---|
| 4枚 all | ROCm | ~745s(2/2 再現) | **8820 GPUVM fault** | `Memory access fault by GPU node-5` + UTCL2 `[gfxhub0] no-retry page fault address 0x100000000` |
| 4枚 all | Vulkan | **~2208s (1/1)** | **8820 GPU reset** | `amdgpu_job_timedout` → `GPU reset begin!` → `BACO reset` → `VRAM is lost` → `vk::Device::waitForFences: ErrorDeviceLost` → `vk::DeviceLostError` |
| 3枚 incl 8820 | ROCm | ~1613s | **8820 GPUVM fault** | UTCL2(同上) |
| 3枚 incl 8820 | Vulkan | **2307s (3/3 完走)** | **クリア** | — |
| 3枚 excl 8820 | ROCm | ~2361s (3/3) | クリア | — |
| 3枚 excl 8820 | Vulkan | 2210s (3/3) | クリア | — |

## Vulkan device 可視性指定の再番号付けに関する注意

`GGML_VK_VISIBLE_DEVICES=0,2,3`(非連続な index 列)で起動すると、llama-server の `device_info` ログでは可視デバイスが **連番 `Vulkan0 / Vulkan1 / Vulkan2`** に再番号付けされる(元の Vulkan index 0,2,3 はログに残らない)。Phase 2B(3枚 incl 8820 = 33301除外)の起動ログ実例:

```
0.00.111.959 I   - Vulkan0 : Radeon Instinct MI25 (RADV VEGA10) (16368 MiB, 16360 MiB free)   ← 元 idx 0 = 04:00.0 = 29525
0.00.112.346 I   - Vulkan1 : Radeon Instinct MI25 (RADV VEGA10) (16368 MiB, 16360 MiB free)   ← 元 idx 2 = 84:00.0 = 54068
0.00.112.728 I   - Vulkan2 : Radeon Instinct MI25 (RADV VEGA10) (16368 MiB, 16360 MiB free)   ← 元 idx 3 = 87:00.0 = 8820
```

ログだけでは「どの BDF/GUID を選んだか」が逆引きできないため、起動コマンドの `GGML_VK_VISIBLE_DEVICES` 値を別途保全する必要がある(ROCm の `HIP_VISIBLE_DEVICES` + `ROCm0/1/2` 表示と同じ挙動)。本タスクでは起動コマンド全文を campaign ログに残してある。

## Phase 1 フォルト signature (詳細)

### kernel (amdgpu) ログ

```
[16465.453556] [drm:amdgpu_job_timedout [amdgpu]] *ERROR* Process information: process llama-server pid 374059 thread llama-server pid 374059
[16465.455568] amdgpu 0000:87:00.0: amdgpu: GPU reset begin!
[16465.469399] amdgpu 0000:87:00.0: amdgpu: psp gfx command UNLOAD_TA(0x2) failed and response status is (0x117)
[16465.497753] amdgpu 0000:87:00.0: amdgpu: Dumping IP State
[16465.499371] amdgpu 0000:87:00.0: amdgpu: BACO reset
[16467.066465] amdgpu 0000:87:00.0: amdgpu: GPU reset succeeded, trying to resume
[16467.066963] [drm] VRAM is lost due to GPU reset!
[16467.428367] amdgpu 0000:87:00.0: amdgpu: GPU reset(1) succeeded!
```

- **GPU 8820 (87:00.0)** のみで発火。他 3 枚に GPU reset は無い。
- 原 ROCm の `Memory access fault by GPU node-5` / `[gfxhub0] no-retry page fault ... address 0x100000000` (UTCL2) **は出現せず**(Vulkan ではユーザランド HSA を経由しないため `Memory access fault` メッセージそのものが出ない)。
- 代わりに **kernel TDR (Timeout Detection & Recovery) パス**: `amdgpu_job_timedout` → `BACO reset` で GPU を再初期化。**VRAM is lost** で確保メモリは消失。

### llama-server (Vulkan) ログ

```
40.14.785.921 E srv  update_slots: decode() failed: vk::Device::waitForFences: ErrorDeviceLost
40.14.785.938 E srv    send_error: task id = 71022, error: decode() failed: vk::Device::waitForFences: ErrorDeviceLost
...
terminate called after throwing an instance of 'vk::DeviceLostError'
  what():  vk::Queue::submit: ErrorDeviceLost
```

スタックトレース末端: `ggml_vk_synchronize` → `ggml_backend_sched_synchronize` → `llama_context::synchronize` → `server_slot::prompt_save` → `server_context_impl::get_available_slot`(セッションの prompt cache をディスクに保存しようとした時)。プロセスは `std::terminate` で異常終了。

### 発現タイミング(プラン予想と一致)

trial 3 までは正常な multi-turn 推論を完走(eval ≈ 34〜38 t/s)。trial 3 の最後の `restored context checkpoint (pos_min = 17222, ..., size = 62.813 MiB)` 直後に `decode() failed: ErrorDeviceLost`。原 ROCm と **同じ「restored context checkpoint → 短いプロンプト → フォルト」パターン** で発火し、フォルト発火条件は **バックエンド非依存** であることを示す。

## per-card PCIe + AER(全 phase で異常 0)

`telemetry_pcie_*.log` の全サンプルで `Width x16 / Speed 8GT/s / PresDet+ / AER cor=fat=nonfat=0 / GPU_COUNT=4` を維持。**物理層は全期間健全**、Phase 1 の GPU reset 後も 4 枚認識・x16 で復活(VRAM は失われたが PCIe リンクは健全)。

## なぜ Vulkan は 3 枚 incl 8820 でも安定なのか(機構の推定)

- **ROCm**: HIP/HSA が `address 0x100000000` への不正参照を **即座に UTCL2 page fault** で検出 → llama-server は ROCm runtime から `Memory access fault` を受け取り即死。「8820 がアクセスする論理アドレス」が破綻するため、**枚数や負荷分担量に関係なく 8820 を含めば常に発火**。
- **Vulkan**: Vulkan ドライバは別のメモリ確保パス(VMA / driver-internal allocator)を使うため UTCL2 page fault 経路をそもそも踏まない。代わりに **長時間負荷で 8820 上の特定キューが進まなくなり**(クロック/演算ユニット異常か個体の信号品質か)、`amdgpu_job_timedout` (1.5〜2 秒の TDR 閾値)に到達して **kernel が GPU を BACO reset**。**TDR トリガに必要な負荷量は 4 枚分散時に集中して 8820 が踏む** が、3 枚分散時はカードあたりの負荷が増えて他経路を取り、TDR に達しない様子。**「枚数依存」がある(=4 枚負荷でのみ発火)** ことが Vulkan の特徴。
- ただし 3 枚 incl 8820 で 2307s 完走したのは 1 ラン(3 trial)のみで、長時間負荷で発火しない保証は無い。本番 4 枚運用には注意が必要。

## 試行スループット(参考)

Phase 2A excl 8820 中央値: eval ≈ 35.0 t/s / prompt ≈ 400 t/s(完了トークン総計 約45k / 47 ターン)。Phase 2B incl 8820 とほぼ同等。
Phase 1 4枚負荷では trial 1〜3 で eval 34〜38 t/s / prompt 280〜435 t/s。

### eval は Vulkan 優位、prompt は ROCm 優位(用途依存)

比較は **同一構成(4 枚 / Qwen3.6 / ctx=131072 / FA1 / KV q8_0)** で行う。原 ROCm レポートからの抜粋は **4 枚 run(フォルトまでの稼働中)の値** で揃える(3 枚 excl 8820 中央値 22.9 t/s 等とは混同しない)。

| 指標 | ROCm (原 4枚 run、フォルト直前の健全期) | Vulkan (本 4枚 run、trial 1〜3) | 比率 (Vulkan/ROCm) |
|---|---|---|---|
| eval (生成) | 20〜23 t/s | **34〜38 t/s** | **約 1.5×〜1.7×** ← 逆転して Vulkan 優位 |
| prompt (前処理、ピーク値) | 600 t/s | 435 t/s | 約 0.7× ← 依然 ROCm 優位 |
| prompt (前処理、中央値) | (原レポートに 4 枚 run の中央値は記載なし。3 枚 excl 8820 中央値 506 t/s が参考) | ≈ 400 t/s | — |

→ **トレードオフ構造**: 過去メモリの「Vulkan eval ≈ 0.6× ROCm」は eval だけが古かった(master 改善群を取り込んだ現バージョンでは逆転)。一方 prompt の比率は方向性は変わらず ROCm 優位のまま。**長文プロンプト処理が支配的なワークロード(チャット冒頭・新規セッション・RAG)では ROCm、生成トークン数が支配的なワークロード(長文回答・推論モード・対話継続)では Vulkan** を選ぶのが理にかなう。Qwen3.6(MoE 35B-A3B)の thinking モードは長文生成が支配的なため Vulkan が有利な側に寄りやすい。

なお、本タスクで観測した Vulkan の生スループット値(代表点):
- Phase 1 4枚負荷: trial 1 prompt 434.31 t/s + eval 37.10 t/s / trial 2 prompt 404.26 t/s + eval 36.61 t/s / trial 3 末尾 prompt 280.75 t/s + eval 34.42 t/s(フォルト直前)。
- Phase 2A/2B 3枚負荷: eval ≈ 35.0 t/s(中央値、両構成ほぼ同等)。
