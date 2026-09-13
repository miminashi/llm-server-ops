# GLM-5.3-Flash: #27773 の最新版ビルド動作確認と #27754 との深さ比較

## 背景

前回セッション [2026-09-05_204557_glm53flash_pr27773_sparse_fa_multistream.md] は
aws-gpu02 の連続ハングで後片付けが中断した。その原因は後続セッションで
`P2_DIMME1` の uncorrectable ECC と特定され、BIOS の `Patrol Scrub` を Disable に
することで回避済み（2026-09-05_221831_aws_gpu02_uncorrectable_ecc.md）。
aws-gpu02 は 23 時間以上ハングなしで連続稼働している。

ユーザ依頼は「ワークアラウンドが見つかったので、最新版のビルドと動作確認」。

作業開始時点の上流状況（2026-09-06 22:00 JST 調査）:

| 項目 | 値 |
|---|---|
| #27773 HEAD | `8134115f88ed8018474e7db69afcfe97fb097fc4`（**前回検証時から変化なし**） |
| #27773 新規コメント | LifesLight (09-06 07:44 UTC): `--image-max-tokens` が効かず mmproj 側の上限が使われる |
| #27754 HEAD | `629b505528`（前回検証 09-02 時点は `949f7efb09`。**進んでいる**） |
| 本家 master | `73a43d1f69`（前回 `6a1a922d2`） |
| aws-gpu01 | 電源 OFF、llama.cpp は master `6a1a922d2` |
| aws-gpu02 | 稼働中（23h20m）、llama.cpp は master `6a1a922d2`、ロック空き |

PR HEAD が動いていないため、単なる再検証では価値が薄い。ユーザ選択により
**「動作確認 + #27754 との深さ比較」**を実施する。これは前回レポートの残課題
「#27754 との深さ比較（同一環境で両者を測れば強いデータ点になる）」に対応する。

## 目的

1. **動作確認**: #27773 HEAD `8134115f88` を両機にビルドし、ハング復旧後のハードで
   前回と同じ結果が再現することを確認する（ロード・短答のバイト一致・11k needle）。
2. **#27754 との深さ比較**: 同一環境・同一プロンプト・同一パラメータで
   #27773 と #27754 の tg vs 深さを直接比較する。nicholasshirley が 1x4090 +
   CPU offload で報告した「#27773 は深さに強く #27754 は落ちる」を、
   **GPU only の 13x P100 RPC 分散で追認できるか**を確定させる。

## 測定設計

- 共通パラメータ: `-fa on --poll 0 -b 512 -ub 4096 --ctx-size 32768 --jinja`、
  測定は `temperature 0 / top_p 1.0`
- プロンプトは**前回セッションの添付をそのまま再利用**（バイト同一）:
  `short.json`(16 tok) / `needle_7k.json`(7,349) / `needle_11k.json`(11,338) /
  `needle_29k.json`(28,390)
- モデル:
  - #27773 → `~/models/GLM-5.3-Flash-GGUF/UD-IQ4_XS-nopatch/`（shard1 未パッチ + 2-5 シンボリックリンク）
  - #27754 → `~/models/GLM-5.3-Flash-GGUF/UD-IQ4_XS/`（オリジナル）
  - 両者は内容としては同一ファイル
- MTP は使わない（#27754 のみの機能なので apples-to-apples にならない）

## 手順

### Phase 0: 電源投入とロック
1. `ALLOW_FAN_NOISE=1 bmc-power.sh aws-gpu01 on`（実行済み）
2. SSH 到達を待つ
3. `lock.sh aws-gpu01` / `lock.sh aws-gpu02`
4. 100GbE リンク（`192.168.100.x`）の確認
5. aws-gpu02 の SEL に Uncorrectable ECC が増えていないことを確認（ベースライン 11 件）

### Phase 1: #27773 のビルド
6. aws-gpu01 のローカル修正（`server-http.cpp` の `--ui-mcp-proxy` 404 修正）を stash
7. 両機で `git fetch origin pull/27773/head:pr27773 -f && git checkout pr27773`
8. `update_and_build.sh --no-pull --force` を両機で並行実行（gpu02 は `-j` を落とす）
9. `llama-server --version` で両機のビルド識別子一致を確認

### Phase 2: #27773 の測定（E 系列）
10. `rpc-up.sh aws-gpu02` → `run_cfg.sh E1 <nopatch> 32768 4096`
11. E1-1 短答 → 前回 `r_D1_short.json` とバイト比較
12. E1-2/3/4: 7k / 11k / 29k needle → pp・tg・合言葉正答
13. VRAM 記録、ログ退避

### Phase 3: #27754 のビルド
14. `stop.sh aws-gpu01` → `rpc-down.sh aws-gpu02`
15. 両機で `git fetch origin pull/27754/head:pr27754 -f && git checkout pr27754`
16. `update_and_build.sh --no-pull --force` を両機で

### Phase 4: #27754 の測定（F 系列）
17. `rpc-up.sh aws-gpu02` → `run_cfg.sh F1 <UD-IQ4_XS> 32768 4096`
18. F1-1〜4: 同じ 4 プロンプト
19. VRAM 記録、ログ退避

### Phase 5: 図とレポート
20. tg vs 深さの比較図（#27773 / #27754 / nicholasshirley の 4090 データ）を matplotlib で生成
21. レポート作成（REPORT.md 準拠）、INDEX.md 更新

### Phase 6: 後始末
22. llama-server / RPC 停止
23. 両機 master に戻して再ビルド、aws-gpu01 の stash pop
24. ロック解放
25. 電源の扱いはユーザに確認

## リスク・注意

- **aws-gpu02 のハング再発**: 監視のため SEL 件数を各フェーズで確認する。
  再発したら KVM スクショ + SEL を保全してからユーザに報告。
- **ビルド並列度**: 前回 `-j40` のビルド中にハングした。ECC が原因と判明したので
  因果はないはずだが、念のため gpu02 は `-j20` 相当に落とす。
- **cold ロードが 11 分**かかる。構成切替のたびに発生する見込み（146 GiB は
  gpu02 の RAM 94 GiB に収まらないので page cache は部分的にしか効かない）。
- **#27754 が現 HEAD でも起動するとは限らない**。09-02 以降にコミットが入っている。
  起動しない場合は `949f7efb09`（09-02 検証済みコミット）にフォールバックする。
- 所要見込み: 4〜5 時間。

## 成果物

- `report/2026-09-06_<hhmmss>_glm53flash_pr27773_vs_27754_depth.md`
- 添付: plan.md / llama-server ログ / 応答 JSON / 比較図 PNG / スクリプト
- `report/INDEX.md` 更新
