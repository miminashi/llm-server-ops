# 収集データ(生ログ要約)

## ベースライン(負荷前・idle)

```
COUNT=4
PORT 00:02.0 = Width x16 Speed 8GT/s PresDet+ AER(cor=0 fatal=0 nonfatal=0)
PORT 00:03.0 = Width x16 Speed 8GT/s PresDet+ AER(cor=0 fatal=0 nonfatal=0)
PORT 80:02.0 = Width x16 Speed 8GT/s PresDet+ AER(cor=0 fatal=0 nonfatal=0)
PORT 80:03.0 = Width x16 Speed 8GT/s PresDet+ AER(cor=0 fatal=0 nonfatal=0)
GUIDS_ALIVE= 29525 33301 54068 8820
```

## スロット↔ルートポート↔BDF↔GUID↔HIP index↔KFD node 対応

| 物理スロット | ルートポート | GPU BDF | GUID | HIP index | KFD node |
|---|---|---|---|---|---|
| CPU1 SLOT2 | 00:02.0 | 04:00.0 | 29525 | 0 | 2 |
| CPU1 SLOT4 | 00:03.0 | 07:00.0 | 33301 | 1 | 3 |
| CPU2 SLOT8 | 80:02.0 | 84:00.0 | 54068 | 2 | 4 |
| **CPU2 SLOT6** | **80:03.0** | **87:00.0** | **8820** | **3** | **5（フォルト元）** |

- HIP index→BDF は `rocm-smi --showbus` で確認。KFD node は `/sys/class/kfd/kfd/topology/nodes/*/`(gpu_id・location_id)で確認(location_id 34560=0x8700=bus 0x87)。
- ROCm ランタイムが出す `Memory access fault by GPU node-5` の node-5 = gpu_id 8820 = SLOT6。

## 電源サイクルテスト(7/7 合格)

全7サイクル(コールド5 + ウォーム2)で `COUNT=4`、全ルートポート `Width x16 / Speed 8GT/s / PresDet+ / AER cor=fatal=nonfatal=0`、`GUIDS_ALIVE= 29525 33301 54068 8820`、dmesg dropout/reset/hang signature なし。詳細は [cycle_trend.log](cycle_trend.log)。

## 負荷テスト(GPUVM page fault)

### フォルト signature(全 run 共通・例: run1)

```
Memory access fault by GPU node-5 (Agent handle: 0x...) on address 0x100000000.
  Reason: Page not present or supervisor privilege.

amdgpu 0000:87:00.0: amdgpu: [gfxhub0] no-retry page fault (src_id:0 ring:24 vmid:8 pasid:32772)
  for process llama-server ...
  in page starting at address 0x0000000100000000 from IH client 0x1b (UTCL2)
  VM_L2_PROTECTION_FAULT_STATUS:0x00000000
  Faulty UTCL2 client ID: CB (0x0)  MORE_FAULTS:0 WALKER_ERROR:0 PERMISSION_FAULTS:0 MAPPING_ERROR:0 RW:0
```

- 毎回 **同一 GPU(0000:87:00.0 = 8820/SLOT6 = node-5)**、**同一アドレス(0x100000000)**、同一 ring(24)/vmid(8)。
- フォルトの monotonic timestamp は run ごとに別物(run1=1408s / run2=2465s / 3card+8820=4414s)で、各 run が新規プロセスの実フォルトであることを確認。
- 生ログ: [crash1_dmesg.txt](crash1_dmesg.txt)(4枚run1) / [crash2_dmesg.txt](crash2_dmesg.txt)(4枚run2) / [crash3_3card_dmesg.txt](crash3_3card_dmesg.txt)(3枚+8820)。

### 構成別 time-to-fault(実測, [load_results.json](load_results.json))

| 構成(HIP_VISIBLE_DEVICES) | 含むGUID | 連続負荷 | 結果 |
|---|---|---|---|
| 4枚 全部 run1 | 29525,33301,54068,8820 | ~745s | **8820 フォルト** |
| 4枚 全部 run2 | 同上 | ~660s | **8820 フォルト** |
| 3枚 incl8820 (0,2,3) | 29525,54068,8820 | ~1613s | **8820 フォルト** |
| 3枚 excl8820 (0,1,2) | 29525,33301,54068 | ~2361s(3/3完走) | **クリア・anomaly 0** |

- 物理層は全 run で健全: 負荷中の per-card PCIe サンプラ(telemetry_pcie)は全サンプル x16 / PresDet+ / AER cor=fatal=0、gpu_count は全サンプル 4。フォルトは PCIe 脱落ではなく compute/VRAM 層(GPUVM)。
- **熱・電力も正常(熱起因の除外)**: rocm-smi テレメトリ405サンプルで junction 温度ピーク **65℃**(idle 30〜40℃)、電力ピーク **164W**(キャップ160W近傍、瞬間超過は正常)。サーマルスロットル/過熱の兆候なし。
- **発現タイミングの規則性**: サーバログ上、フォルトは毎回「`restored context checkpoint`(prompt-cache の文脈チェックポイント復元)→ 短い新規プロンプト処理 → 直後にフォルト」の同一パターン。マルチターン蓄積後の checkpoint 復元が引き金になっている可能性。
- **枚数とtime-to-fault**: 4枚(~700s)< 3枚含8820(~1613s)。per-card compute が小さい4枚の方が早く落ちる=8820 への P2P/アドレッシング負荷集中の示唆(ただし8820除外で消失するため根本は8820個体/SLOT6)。
- **検出器の挙動(方法論)**: サーバ即死時、load_driver は health=000 / host_ping=True / ssh_ok=True を「server_error_transient」と分類(rc≠42/43)。run_campaign はハング扱いせず KVMスクショ・電源リセットを行わなかった=server-crash と host-hang を正しく弁別。なお rocm-smi/telemetry の gpu_count は HIP_VISIBLE_DEVICES マスクと無関係に物理4枚を表示する(ハード視点のため)。
- フォルト直前のスループットは健全(eval 20〜23 t/s、prompt ピーク 600 t/s)＝性能劣化ではなく突然死。
- excl8820 のスループット中央値: eval 22.9 t/s / prompt 506 t/s(48,267 完了トークン / 24ターン / 0 anomaly)。

## 4枚 offload 確認(参考)

```
load_tensors: offloaded 41/41 layers to GPU
load_tensors:        ROCm0 model buffer size =  5626.21 MiB
load_tensors:        ROCm1 model buffer size =  5017.37 MiB
load_tensors:        ROCm2 model buffer size =  5024.37 MiB
load_tensors:        ROCm3 model buffer size =  5130.85 MiB
```
4枚すべてにモデルバッファが配置され、4枚分散推論自体は成立していた(その上で 8820 が負荷中にフォルト)。
</content>
