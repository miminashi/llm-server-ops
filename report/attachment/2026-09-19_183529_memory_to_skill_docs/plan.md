# メモリにしか無い注意点を CLAUDE.md / スキル文書へ移す

## Context

メモリにしか書かれていない運用上の注意点を、ユーザと合意した配置で CLAUDE.md とスキル文書へ移す。
あわせて、照合中に見つかった「古い／誤った記述」を直す。

計画中の確認で、前ターンの提案より重要な事実が 3 つ判明したので、それを反映した内容にする:

1. **`GGML_CUDA_ALLREDUCE=butterfly` は存在しない値**（2026-09-16 の 3 腕レポートで訂正済み）。
   受け付けるのは `nccl` / `internal` / `none` だけで、未知の値は警告付きで `none` に落ちる。
   **メモリの「butterfly を付ける」は誤り**。`none` を使うと decode -25%、prefill -78〜-80% になる。
   また **t120h-p100 の 4 枚では既定の NCCL で起動 3/3**（2026-09-18）＝ハングは aws-gpu01 7 枚固有。
   `start.sh` は常に `--split-mode layer` なので、**スクリプトの修正は不要**で、文書に書くだけでよい。
2. **plugin cache（`~/.claude/plugins/cache/claude-plugins-official/llama-server/1.0.0/`）は
   2026-05-13 のコピー**で、dry 行が無いだけでなく `--presence-penalty 1.0`・RPC スタック・
   mi25 Vulkan の自動検出・`ttyd-up.sh` も入っていない。問題は dry ではなく「コピー全体が古い」こと。
   更新手段は `install-global.sh` の再実行（`cp -r` で再配置）。
3. **mi25 は現在 SSH 不通**（`No route to host`）。GPU 配置は実機で確認できないので、
   2026-07-20 のレポートの記録（BDF 84:00.0 = c48c4 = HIP index 2）で書き、「日付時点」と明記する。

## 変更内容

### A. `CLAUDE.md`

- **「重要な制約」表に 1 行追加**: `pkill -f` / `pgrep -f` は Bash ツールのコマンド全文に
  マッチして自分自身を kill する（exit 144）。pidfile の PID を kill するか、
  `pgrep -af` で PID を取って個別に kill する。
- **「ソースコード」節に 1 行追加**: `llama-finetune` は壊れており、fine-tune の調査は
  `~/projects/llama.cpp-fine-tuning` へ移管済み。依頼が来たら HF Trainer + LoRA を案内する。

### B. `.claude/skills/llama-server/SKILL.md`

- **「### 既知の問題: aws-gpu01 の `--split-mode tensor` が NCCL で起動ハング」を新設**
  （既存の「既知の問題: `-ub 8192` の CUDA OOM」節の直前）。書く内容:
  - 症状: 最初の `llama_decode`（ウォームアップ）でハング。徴候は GPU 利用率 100%・memory 利用率 0%
  - 範囲: aws-gpu01（P100 ×7）で NCCL 経路は起動 1/15。t120h-p100 ×4 では NCCL で 3/3 起動し問題なし
  - 回避策: `GGML_CUDA_ALLREDUCE=none`。**`butterfly` は不正値**（警告付きで `none` に落ちる）。
    `internal` は sm_60 で待ちに入ると `__trap()` で落ちるので使わない
  - コスト: `none` は NCCL 比 decode -25% / prefill -78〜-80%。MTP 採択率低下の疑いは未解決
  - `start.sh` は `--split-mode layer` 固定なので、tensor を手動で使う場合だけの注意
  - 参照: 2026-09-14 / 2026-09-16 / 2026-09-18 の 3 レポート
- **「モデル別サンプリングパラメータ」節の直後に注記**: plugin cache 1.0.0 は 2026-05-13 のコピーで、
  以降のサンプリング変更（`--presence-penalty 1.0` など）や RPC・Vulkan 自動検出を含まない。
  plugin 経由で起動しない。更新は `install-global.sh` を再実行。

### C. `.claude/skills/gpu-server/SKILL.md`

- **サーバ一覧表の mi25 のプラットフォーム**: `ROCm` → `Vulkan（既定）/ ROCm`。
- **aws-gpu の注意事項の「POST 中の爆音は消せていない」を訂正**: `bmc-power.sh` が
  `boot-quiet.sh` を自動併走させるので POST 中も 2,900rpm 台（2026-08-18 実測）。
  ただし抑制が効かない場合に備えてガードは維持する（CLAUDE.md と同じ書き方にそろえる）。
- **「mi25 の注意事項」ブロックを新設**（t120h-m10 と aws-gpu の注意事項の並び）:
  - GPU 配置（2026-07-20 時点）: BDF 04=c3164 / 07=448c4 / **84=c48c4（過去 fault 個体、SLOT8）** / 87=a48e4
  - 常用は 4 枚（`HIP_VISIBLE_DEVICES=0,1,2,3`、Vulkan は `start.sh` が自動検出）。
    fault が再発したときの fallback は c48c4 を除く `0,1,3`（物理配置を変えたら Unique ID で再確認）
  - 4 枚認識は BIOS の MMIO High Size 512GB に依存（`lspci | grep -c "Instinct MI25"` が 4 か）
  - power cap は `/etc/rc.local` が起動時に 160W に設定するが、**BACO reset 後は 220W に戻る**
    （再設定は `sudo rocm-smi --setpoweroverdrive`。sudo なのでユーザに依頼）
  - 重い I/O（ビルド＋大容量コピー）で ext4 が read-only 化した前例がある。ビルド並列度を抑える

### D. `.claude/skills/gpu-server/bmc.md`

- **「いつ使うか」節**: ext4 破損の例に「SSH が `Connection reset by peer` になるのは fail2ban
  ではなく FS 障害のことがある」を追記。
- **「ハング調査では最初に SEL を読む」節の直後に「### ハング判定: 経路障害と区別する」を新設**:
  ping / SSH / health の不通だけでは経路障害と区別できない。「BMC に届き、かつ対象と同じ拠点の
  参照先にも届く」ときだけ真のハング。mi25 の参照先は 10.1.5.1 / 10.1.1.1
  （制御ホストと同じ拠点の 10.1.6.4 は使わない）。確率的なハードウェア事象なので負荷で再現させようとしない。
- **「トラブルシュート」節に「VBAT の定期確認」を追加**:
  `ipmitool ... sensor | grep VBAT`。mi25 は 2026-07 に CMOS 電池切れでリブートループになった
  （初警告から 10 ヶ月の猶予があったが監視していなかった）。電池切れで BMC 時刻が +9h ずれ、
  BIOS 設定（MMIO High 等）も初期化される。

### E. メモリの整理（移した内容の重複と誤りを消す）

| メモリ | 対応 | 理由 |
|---|---|---|
| `feedback_pkill_self_match.md` | 削除（MEMORY.md の行も） | CLAUDE.md に移したため |
| `project_gpu01_tensor_split_nccl_hang.md` | 削除（MEMORY.md の行も） | SKILL.md に移したうえ、butterfly の記述が誤り |
| `project_dry0_unpushed.md` | 削除（MEMORY.md の行も） | push 済みで役目を終え、plugin cache の注意は SKILL.md に移したため |

以下は移さずメモリに残す: OSS への投稿ルール、memtest_vulkan、fine-tune の詳細（PR の監視先）、
mi25 系の経緯メモ。その他の古い記述（`project_mi25_vulkan` の start.sh バグなど）の整理は今回の対象外。

### F. レポート

CLAUDE.md の規則どおり `report/<日時>_memory_to_skill_docs.md` を REPORT.md の書式で作成
（概要＝何を移したか、判明した誤り 3 点、変更ファイル一覧）。実測データは無いので PNG は不要。
コミットはユーザの指示があるまで行わない。

## 検証

- 追記した各コマンド・パス・数値を出典（上記レポート、`start.sh`、`install-global.sh`）と照合する
- `grep -rn "butterfly" .claude/skills CLAUDE.md` が「不正値」という文脈でしか出ないこと
- `grep -n "POST 中の爆音" .claude/skills/gpu-server/SKILL.md` で古い記述が残っていないこと
- MEMORY.md の行と memory ディレクトリのファイルが 1 対 1 で対応していること
- 相対リンク（`../../../report/...`）の参照先が実在すること（`ls` で確認）
