# レポート作成: aws-gpu01/02 の GPU 移設・DIMM 再構成・RPC 分散推論の再開

## Context

本セッション（2026-10-19 19:58〜21:50 JST 頃）で以下を行った。ユーザの依頼に従い、REPORT.md の書式でレポートにまとめてコミットする。

1. aws-gpu02 → aws-gpu01 へ P100 16GB 2 枚を移設 → aws-gpu01 は 9 枚 144GB（commit `8cf7f51d`、push 済み）
2. aws-gpu02 の DIMM 再構成を 4 回の起動で確認（31 GiB 故障スロット 1 枚 → 125 GiB 4 枚 → 62 GiB 2 枚 → 確定 94 GiB Micron 3 枚）。確定構成で再起動しても同じ構成で上がることを確認（commit `1981dcf2`、未 push）
3. RPC 分散推論の試行: 100GbE の NIC 移動でインタフェース名が変わり（`enp4s0np0`→`ens1np0`）netplan が外れて初回失敗 → MAC 一致の netplan に修正 → 13 GPU で起動成功、pp 55〜57 t/s / tg 10.9〜11.9 t/s
4. 副次: Bash サンドボックスからだけ 10.8.2.x へ No route（`dangerouslyDisableSandbox` で回避）、Monitor/バックグラウンド完了通知が実状態より先に届く事象

## 作業手順

### 1. タイムスタンプとディレクトリ
- `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
- レポート: `report/<ts>_aws_gpu_card_move_dimm_rebuild_rpc_restart.md`
- 添付: `report/attachment/<同名>/`

### 2. 添付ファイルの収集（読み取りのみ・サーバ状態は変えない）
- `plan.md`（本プランのコピー）
- scratchpad の KVM スクショ: `gpu01_boot1.png`（POST BA）、`gpu02_boot1.png`（`Failing DIMM: P1-DIMMA1`）、`gpu02_d_1.png`（確定構成の POST 91）
- `rpc-up.log`（初回失敗: `Failed to create server socket`）、`rpc-up2.log`（成功）
- 現時点のスナップショットを SSH で取得してテキスト保存: 両機の `nvidia-smi`（serial/BDF/VRAM 使用量）、`nvidia-smi topo -m`、aws-gpu02 の `dmidecode -t 17` 抜粋・`numactl -H`・新 netplan、`/tmp/llama-server.log` の要所（RDMA activated / buffer size / listening）
- `summary.png`: matplotlib で pp / tg を旧構成（2026-08-16 abliterated 実測: pp 70.8〜75.7 / tg 12.2〜12.8）と今回（pp 55.5/57.2 @10,410 tok、tg 10.9〜11.9）で並べた棒グラフ（条件不一致の注記付き）

### 3. レポート本文（REPORT.md 準拠）
- タイトル例: `# aws-gpu 2 台の GPU 移設とメモリ再構成 — RPC 分散推論を再開`
- メタ情報（作成者: Claude Opus 5.5 (1M context)）
- `## 概要`（平易な日本語 5〜8 段落）
- `## 添付ファイル`
- `## 核心発見サマリ`（summary.png 埋め込み → **結論**: 段落）
- `## 環境情報`: aws-gpu01 9 枚表 / aws-gpu02 4 枚表 / DIMM 3 枚表（serial と旧スロット）/ llama.cpp `465e49b9`
- `## 結果詳細`: (a) aws-gpu01 起動と構成確認 (b) aws-gpu02 DIMM 構成の 4 段階の推移表（各回の容量・スロット・POST 表示）と旧 serial 照合（`0FEDE991` = 旧 A2 で 09-10 に名指しされた個体、`<BAD INDEX>` 2 枚を除外）(c) RPC 起動失敗の原因と netplan 修正 (d) VRAM 配分と速度
- `## 副次発見`: サンドボックスの No route、通知の先行
- `## 残課題`: 速度低下の切り分け、`0FEDE991` の経過観察・memtest、Patrol Scrub を Enable に戻す機会、aws-gpu01 側 netplan も MAC 一致にするか（sudo はユーザ依頼）
- `## 参照レポート`: 2026-08-16 RPC / abliterated 比較、2026-09-05 ECC、2026-09-11 DIMMA2、2026-09-24 ECC enable

### 4. ドキュメント更新
- `.claude/skills/gpu-server/aws-gpu.md` の「100GbE 直結リンク」節: aws-gpu02 のインタフェースを `ens1np0`（2026-10-19 に `enp4s0np0` から変更）に直し、netplan を MAC 一致にした旨と手動復旧コマンドを更新
- `report/INDEX.md` の「14. aws-gpu01 / aws-gpu02 の追加」末尾に 1 行説明付きで追記

### 5. コミット
- `git add` で上記レポート・添付・aws-gpu.md・INDEX.md を追加し、1 コミット（`docs(report): ...`、Co-Authored-By 付き）。push はしない（未 push の `1981dcf2` も含めて、push は指示を待つ）
- llama-server / rpc-server と両機のロックはそのまま（停止は別途指示を待つ）

## 検証
- `git show --stat HEAD` で対象ファイルのみが含まれること
- レポート内の相対リンク（attachment / 参照レポート）が実在することを `ls` で確認
- pre-commit hook（巨大ファイル検出）が通ること
