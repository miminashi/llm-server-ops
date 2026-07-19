# mi25 c48c4 SLOT8 4-card / Vulkan D-2 R1 — 集計表

## 全期間サマリ
| 項目 | 値 |
|---|---|
| Session1 完了 trial (02:07-18:52 電源断中断) | 74 |
| Session2 完了 trial (23:58-05:36 継続) | 25 |
| **累計 完了 trial** | **99** |
| HANG_CONFIRMED (jsonl) | 0 |
| dmesg GPU reset (新規、baseline+2308行以降) | 0 |
| **統合 fault 件数** | **0** |
| turn 総数 | 497 |
| eval_tps mean | 12.85 |
| eval_tps p50 | 12.90 |
| pp_tps mean | 586.08 |
| 本試験 fault 率 | 0/99 = 0.00% |

## Fisher exact one-sided (H1: D-2 R1 の fault 率 < 過去)
| 比較対象 | fault/trial | 発生率 | Fisher p (one-sided) |
|---|---|---|---|
| c48c4×SLOT6 4-card | 3/88 | 3.41% | 0.1023 |
| c48c4×SLOT6 累積 | 5/235 | 2.13% | 0.1702 |
| c48c4×SLOT6 SA | 2/147 | 1.36% | 0.3561 |
| c48c4×SLOT8 SA | 0/221 | 0.00% | 1.0000 |
| a48e4×SLOT6 SA (D-1) | 0/221 | 0.00% | 1.0000 |

## 検出力 (0 fault 観測時、真の rate を棄却できる確率)
| 仮想 真の rate | P(0 fault \| p, N) | 検出力 |
|---|---|---|
| 3.41% | 3.22% | 96.78% |
| 2.13% | 11.87% | 88.13% |
| 1.36% | 25.78% | 74.22% |

## dmesg amdgpu フォルト集計
- baseline 行数: 2308
- kern_dmesg.log 全行数: 4630
- 新規 fault 関連検出件数: **0**
- シグネチャ別: {}
- BDF 別: {}

## PCIe AER (キャンペーン中)
- samples: 6846, non-x16 entries: 0
- AER COR max: 0, FATAL max: 0, NFATAL max: 0
- GPU_COUNT min: 4

## per-GPU テレメトリ
| GPU idx | ラベル | samples | power mean [W] | power p95 [W] | power max [W] | Tj max [°C] |
|---|---|---|---|---|---|---|
| 0 | c3164 (SLOT2) | 6081 | 19.5 | 48.0 | 172.0 | 55.0 |
| 1 | 448c4 (SLOT4) | 6081 | 16.6 | 44.0 | 169.0 | 69.0 |
| 2 | c48c4 (SLOT8)★ | 6081 | 19.4 | 45.0 | 172.0 | 60.0 |
| 3 | a48e4 (SLOT6) | 6081 | 19.8 | 51.0 | 166.0 | 59.0 |

