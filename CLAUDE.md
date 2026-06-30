# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリのコードを扱う際のガイダンスを提供します。

**応答言語**: Claudeは日本語で応答してください。

## 必読ドキュメント

- [REPORT.md](REPORT.md) — レポート作成ルール

---

## ソースコード

- llama.cpp の完全なソースツリーが `src/llama.cpp/` にある（コードリーディング用）。`.gitignore` で `src/` は git 追跡対象外。ビルドは GPU サーバ側の `~/llama.cpp/` で行う（`llama-server` スキル参照）ため、`src/` はローカル参照専用。

---

## GPUサーバとLLM

**重要**: GPUサーバを使用する場合は、**必ず Skill `gpu-server` を使用してください**。このスキルはサーバのロック管理を行い、複数のClaudeセッションが同時にサーバを使用することを防ぎます。

- GPUサーバ（mi25、t120h-p100、t120h-m10）の管理、リモートブラウザの管理に関する情報は `.claude/skills/gpu-server/` にあります。
- llama-serverの起動・管理、モデル選択に関する情報は `.claude/skills/llama-server/` にあります。

### ロックが必要なケース

| ケース | ロック必要 | 理由 |
|--------|-----------|------|
| GPUサーバでllama-serverを使用 | **必要** | 他セッションとの競合を防ぐ |
| GPUサーバでリモートブラウザを使用 | **必要** | 同上 |
| **ローカルでブラウザを実行**（CDPプロキシ経由） | 不要 | GPUサーバのリソースを使用しない |
| **読み取り専用の監視・確認**（ダウンロード進捗、VRAM確認、プロセス確認、ログ確認） | 不要 | リソースを専有しない |

**注**: ローカルでDockerコンテナのブラウザを起動し、LLMサーバのみGPUサーバを使用する場合は、LLM使用のためロックが必要です。

### クイックリファレンス

| サーバ | IPアドレス | OpenAI互換API | BMC |
|--------|-----------|---------------|-----|
| mi25 | 10.1.4.13 | `http://10.1.4.13:8000/v1` | 10.1.4.7（IPMI） |
| t120h-p100 | 10.1.4.14 | `http://10.1.4.14:8000/v1` | 10.1.4.8（iLO5） |

**OSハング/クラッシュ（SSH・ping 不通）を検知したら、電源リセットの前に必ず**
`bmc-screenshot.sh`（KVM スクショ）でコンソール画面を保全すること。カーネルパニックの
スタックトレース・FS 破損・OOM などの原因究明に決定的な情報が表示されている可能性が高く、
リセットすると失われるため。保全後に `bmc-power.sh`（電源リセット）で復旧する。いずれも
`gpu-server` スキルのスクリプトで、SSH 不通でも操作可。詳細は
`.claude/skills/gpu-server/bmc.md`。

```bash
# llama-server確認
ssh t120h-p100 "ps aux | grep llama-server | grep -v grep"

# リモートブラウザ確認
ssh t120h-p100 "docker ps | grep chrome-novnc-cdp"
```

### mi25 GPU 個体識別 (Unique ID 必須)

mi25 (MI25 4枚) では `rocm-smi -i` が表示する **GUID は KFD ランタイム割当値で個体不変ではない**。過去のレポート群で「GUID 8820 / 54068 / 33301 / 29525」と呼んでいたものは、その当時の 4 枚同時運用セッション内でのみ有効。物理交換・スロット入れ替え・単独可視化で値が変わる (実例: 別個体カードを単独装着すると両方とも GUID 54068 を返した)。

カード個体不変の識別子は `rocm-smi --showuniqueid` の **Unique ID** (例: `0x21501edbcec48c4`)。ASIC 内部に焼き込まれた値で、構成変更でも変わらない。

**運用ルール**:
- 認識確認では必ず `rocm-smi --showuniqueid` を併記して記録 (`boot_state.log` 等)
- レポート/メモリで「カード」を指すときは Unique ID **末尾 5 桁** で略記 (例: `card-c48c4`)。2026-06-29 の 4 枚 baseline で末尾 4 桁では `48c4` が `card-c48c4` / `card-448c4` で衝突することが判明したため。衝突した場合は 6 桁以上に拡張
- 過去レポートの「GUID xxxxx」は当時のセッション値として読み替える (新たに使わない)。本日の 4 枚 baseline で過去 fault 集中個体 (4 枚運用時 BDF 87:00.0 = GUID 8820) = **`card-c48c4` (Unique ID `0x21501edbcec48c4`)** と確定
- 物理スワップ前後で Unique ID で必ず照合 (BDF / GUID では追跡不能)

**SMBIOS スロット ↔ GPU BDF**:
- `sudo dmidecode -t 9` の `Bus Address` は MI25 内蔵 upstream bridge の bus 番号 (GPU 本体 BDF ではない)
- 正しい SLOT↔GPU BDF マッピングは `lspci -tnnv` で PCIe tree を辿る
- 例: SMBIOS CPU2 SLOT6 = `85:00.0` (upstream) → `86:00.0` (downstream) → `87:00.0` (GPU 本体) / CPU2 SLOT8 = `82:00.0` → `83:00.0` → `84:00.0`

詳細経緯は [report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md](report/2026-06-29_191721_mi25_gpu_card_id_unique_id.md) と続編 [report/2026-06-29_213624_mi25_4card_uniqueid_baseline.md](report/2026-06-29_213624_mi25_4card_uniqueid_baseline.md) (4 枚 baseline 取得 + 過去 fault 個体 = `card-c48c4` 確定) を参照。

---

## 重要な制約

| 制約 | 説明 |
|------|------|
| GPUサーバ使用 | **必ず Skill `gpu-server` を使用**（ロック管理のため） |
| スクリプト実行 | **プロジェクトルートからの相対パス**（`.claude/skills/...`）で実行すること。フルパス（`/home/ubuntu/projects/...`）は使用しない |
| レポート作成 | plan mode で計画を立てた場合は、**必ず**対になるレポートを作成すること（ユーザから明示的に不要と指示された場合を除く）。フォーマットは [REPORT.md](REPORT.md) に従う |
| sudo実行 | **原則 Claudeはsudoを直接実行しない**。sudo権限が必要な操作が発生した場合は、コマンドをユーザに提示して実行を依頼すること（sshリモート先のsudoも同様）。**例外**: mi25 では `sudo dmidecode`（GPU SMBIOS スロット番号確認等の読み出し用途）は Claude が直接実行してよい（NOPASSWD 設定済み・副作用なし） |
| OSクラッシュ時の証跡保全 | OSハング/クラッシュ（SSH・ping不通）検知時は、**電源リセットの前に必ず** `bmc-screenshot.sh` で KVM スクショを取得すること（コンソールに原因究明の情報が残るため）。詳細は「GPUサーバとLLM」節 |
