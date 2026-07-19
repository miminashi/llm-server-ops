# mi25 デフォルトバックエンドを Vulkan に反転

- **実施日時**: 2026年7月20日 06:00 〜 06:24 JST (前セッション pp 退行切り分けの帰結として default backend を hip → vulkan に反転、コード変更 + Vulkan 既定 + ROCm fallback 両経路の動作確認)
- **報告日時**: 2026年7月20日 06:24 JST
- **作成者**: Claude Opus 4.7 (1M context)

## 概要

前セッション (同日未明) で、mi25 で Qwen3.6-35B-A3B を実運用したときの prompt eval 退行はバックエンドの選び方に起因することが確定した。ROCm/hip 側だけが長い prompt で退行し、Vulkan/RADV 側は 1k から 100k まで全域で過去水準を維持しており、生成速度 (tg) でも Vulkan が ROCm を上回るという結果になった。当時のセッションでは「今後は Vulkan の性能改善に注力し、ROCm 側の原因調査は打ち切る」というユーザ判断が下されており、その帰結として `start.sh` / `update_and_build-mi25.sh` / SKILL.md の default backend を反転する作業が次セッションのタスクとして持ち越されていた。

本セッションではその反転作業を実施した。具体的には、`.claude/skills/llama-server/scripts/start.sh` の `${MI25_BACKEND:-hip}` を `${MI25_BACKEND:-vulkan}` に変更し、`.claude/skills/llama-server/server-scripts/update_and_build-mi25.sh` の usage コメントと default 値を `vulkan` 既定に反転した。また `.claude/skills/llama-server/SKILL.md` の「サーバ別最適化パラメータ」表とバックエンド切替節を、既定=Vulkan / fallback=ROCm という順序に書き換え、既定反転の背景として 2026-07-20 実測 (pp 100k で Vulkan 191 t/s vs ROCm 38.9 t/s、tg で Vulkan 39.5 t/s vs ROCm 28.8 t/s) を根拠として明示した。`CLAUDE.md` にも「mi25 デフォルトバックエンドは Vulkan」を 1 段落で明記する追記を行い、プロジェクトルート側で運用方針を追いやすくした。

編集にあたっては、SKILL.md 内に残っていた 2026-06-14 実測ベースの「Vulkan は prompt が ROCm の約 3.3 倍・eval は約 0.6 倍」という記述が今回の既定反転の根拠と矛盾するため (2026-07-20 実測では tg も Vulkan が ROCm を上回る)、この 1 行も 2026-07-20 実測値で置き換えた。SKILL.md の他の技術詳細 (KV q8_0 固定、vulkaninfo による GPU 可視性の自動検出、gfx900 での __hip_fp8_e4m3 型リグレッションによる pin など) は既定反転後もそのまま有効なため、削らずに順序だけを整えた。

反転が意図通りに動くかを確認するため、まず `MI25_BACKEND` 未指定で `start.sh mi25 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072` を実行し、起動ログで `Vulkan: RADV 物理 GPU を検出 → GGML_VK_VISIBLE_DEVICES=0,1,2,3 (4枚)` が出ることと、稼働プロセスが `~/llama.cpp/build-vulkan/bin/llama-server` (Vulkan バイナリ) であること、`/health` が `{"status":"ok"}` を返すことを確認した。次に fallback 経路として `MI25_BACKEND=hip` を明示した状態で同じコマンドを起動し、稼働プロセスが `~/llama.cpp/build/bin/llama-server` (ROCm バイナリ) に切り替わり、pinned commit (`0fac87b15`, v8533) から新規にフルビルドが走ることも確認した。fallback 側は初回ビルドで数分要するが、既存の `update_and_build-mi25.sh` の分岐 (hip 選択時に PINNED_COMMIT に checkout、vulkan 選択時に master 追従) はそのまま動作している。

動作確認後は再び `MI25_BACKEND` 未指定 (= Vulkan 既定) で llama-server を起動しなおし、mi25 のロックを解放する運用にする。これで次セッション以降は `MI25_BACKEND` を prefix しなくても Vulkan が起動し、ユーザ / 別セッションが自然に高い pp / tg を享受できる状態になる。逆に ROCm を意図的に呼びたい場合 (例えば ROCm 側の long-ctx 退行の原因調査を将来再開したい場合など) は `MI25_BACKEND=hip` を明示して切り替えられる。

今回の変更はコードとドキュメントのみで、実測データを新たに取ったものではない。既定反転の根拠となる 2026-07-20 実測は [前セッションの pp 退行レポート](2026-07-20_013500_mi25_prompt_eval_regression.md) を参照する。ROCm 側の long-ctx 退行 (kernel/DKMS 版数変化・負荷時 DPM 挙動・GPU 個体組合せ差の 3 変数に絞られていた) は方針変更により打ち切りのままとする。

## 添付ファイル

- [実装プラン](attachment/2026-07-20_061248_mi25_default_backend_switch_to_vulkan/plan.md)

## 前提・目的

- **背景**: 2026-07-20 未明のセッションで、mi25 の prompt eval 退行が ROCm 側の長 ctx 依存挙動によるものであり、Vulkan では起きないと確定 ([2026-07-20 pp 退行レポート](2026-07-20_013500_mi25_prompt_eval_regression.md))
- **目的**: `start.sh` / `update_and_build-mi25.sh` / SKILL.md / CLAUDE.md の default backend を hip → vulkan に反転し、`MI25_BACKEND` 未指定時に Vulkan が起動する運用に切り替える
- **方針**: ROCm ビルド構成 (v8533 pin) は残置。`MI25_BACKEND=hip` を明示したときのみ fallback として動く形にする

## 変更内容

### 1. `.claude/skills/llama-server/scripts/start.sh`

L239 の default 値を `hip` → `vulkan` に反転。分岐そのもの (if 側が Vulkan 経路、else 側が ROCm 経路) は変えていない。

```diff
-    if [ "${MI25_BACKEND:-hip}" = "vulkan" ]; then
+    if [ "${MI25_BACKEND:-vulkan}" = "vulkan" ]; then
```

### 2. `.claude/skills/llama-server/server-scripts/update_and_build-mi25.sh`

L12 usage コメントで hip / vulkan の順序を入れ替え、L21 の default を `vulkan` に反転。既定を hip から vulkan に反転した経緯を短いコメントで残した。

```diff
-  MI25_BACKEND  ビルドバックエンド: hip (既定) | vulkan
-                hip    : ROCm/HIP (gfx900)。FP8 型リグレッション回避のためコミット pin。
-                         build/ にビルド。
-                vulkan : Vulkan (RADV)。pin 不要で master 追従。build-vulkan/ にビルド。
+  MI25_BACKEND  ビルドバックエンド: vulkan (既定) | hip
+                vulkan : Vulkan (RADV)。pin 不要で master 追従。build-vulkan/ にビルド。
+                hip    : ROCm/HIP (gfx900) fallback。FP8 型リグレッション回避のためコミット pin。
+                         build/ にビルド。
```

```diff
-# バックエンド選択。既定は hip (ROCm/gfx900) で従来挙動を維持する。
-MI25_BACKEND="${MI25_BACKEND:-hip}"
+# バックエンド選択。既定は vulkan (RADV)。過去は hip 既定だったが、2026-07-20 実測で
+# Vulkan が pp / tg とも ROCm を上回ることが確認されたため反転
+# (report/2026-07-20_013500_mi25_prompt_eval_regression.md)。hip は fallback 用途で残置。
+MI25_BACKEND="${MI25_BACKEND:-vulkan}"
```

### 3. `.claude/skills/llama-server/SKILL.md`

「サーバ別最適化パラメータ」表の mi25 行 (L289-290) の見出しを反転 + 行順を Vulkan 先 / ROCm 後 に入れ替え、既定反転の根拠として 2026-07-20 実測値を各行の理由列に追記。

「mi25 のバックエンド切替」節の見出し・リード文・例示コード・技術説明箇条書きを、既定 = Vulkan / fallback = ROCm の順序に書き換え。リード文直下に反転の背景 1 段落を追加し、2026-07-20 pp 退行レポートへの相対リンクを張った。

**副次修正**: L306 に残っていた 2026-06-14 実測ベースの「Vulkan prompt は ROCm の約 3.3 倍・eval は約 0.6 倍」記述は 2026-07-20 実測 (Vulkan tg > ROCm tg) と矛盾するため、2026-07-20 実測値 (pp 1k=541 / 32k=372 / 100k=191 t/s、tg=39.5 t/s) で置き換えた。既存の技術詳細 (KV q8_0 固定 / vulkaninfo 自動検出 / gfx900 __hip_fp8_e4m3 pin) はそのまま残している。

### 4. `CLAUDE.md`

「クイックリファレンス」表の直下 (「OSハング/クラッシュ検知時の bmc-screenshot.sh 保全」段落の前) に、mi25 default backend が Vulkan であることを 1 段落で明記。詳細は SKILL.md 節と 2026-07-20 pp 退行レポートへリンク。

```markdown
**mi25 デフォルトバックエンド**: Vulkan (RADV, 4 枚 x16GB)。
`MI25_BACKEND=hip` を明示すると ROCm fallback。詳細は
[llama-server SKILL.md](.claude/skills/llama-server/SKILL.md) の「mi25 のバックエンド切替」節、
および [2026-07-20 pp 退行レポート](report/2026-07-20_013500_mi25_prompt_eval_regression.md)。
```

## 動作確認

### Vulkan 既定 (`MI25_BACKEND` 未指定)

- `start.sh mi25 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072` を prefix なしで実行
- 起動ログに `Vulkan: RADV 物理 GPU を検出 → GGML_VK_VISIBLE_DEVICES=0,1,2,3 (4枚)` を確認
- `update_and_build-mi25.sh` は `更新はありません (backend: vulkan)` で通過 (既に build-vulkan/ が master 追従で存在)
- `wait-ready.sh` は 1 回目の poll で `llama-server が正常に起動しました (attempt 1/60)` を返す
- `curl -sf http://10.1.4.13:8000/health` → `{"status":"ok"}`
- `ssh mi25 "ps -ef | grep 'build-vulkan/bin/llama-server' | grep -v grep"` で Vulkan バイナリのプロセスが確認できる

### ROCm fallback (`MI25_BACKEND=hip`)

- `stop.sh mi25` で Vulkan プロセスを停止したうえで `MI25_BACKEND=hip start.sh mi25 "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072` を実行
- `update_and_build-mi25.sh` が `hip` 分岐に入り、`git checkout 0fac87b15` (PINNED_COMMIT, v8533) → `build/` が未生成のため cmake + フルビルド (`-DGGML_HIP=ON -DAMDGPU_TARGETS=gfx900`) が走行 (実測 ~2 分、mi25 側 CPU 全コアで並列 make)
- `find ~/llama.cpp/build/bin/llama-server` が実在するようになり `BUILT`
- `ps -ef | grep 'build/bin/llama-server'` で ROCm バイナリのプロセス (PID 3768367) が確認できた
- `until curl -sf http://10.1.4.13:8000/health; do sleep 5; done` で `{"status":"ok"}` を返し fallback 経路のヘルスチェックも成功
- 動作確認後、`stop.sh mi25` で HIP プロセスを停止し、`MI25_BACKEND` 未指定 = Vulkan 既定で再起動しなおして最終稼働状態にした

## 参照レポート

- [2026-07-20 mi25 pp 退行レポート](2026-07-20_013500_mi25_prompt_eval_regression.md) — 既定反転の根拠となった実測 (ROCm 側 long ctx 退行、Vulkan 全域健全、tg 逆転)
- [2026-06-14 mi25 Vulkan Qwen3.6 128k 探索](2026-06-14_001107_mi25_vulkan_qwen36_128k.md) — Vulkan バックエンド導入時の性能特性 (KV q8_0 固定 / vulkaninfo 検出 / ub 非依存)
- [2026-06-13 mi25 Qwen3.6 128k 実行](2026-06-13_112006_mi25_qwen36_128k.md) — ROCm pin (`0fac87b15`, v8533) の背景

## 結論・対応

mi25 の default backend を `hip` → `vulkan` に反転する編集を完了し、`MI25_BACKEND` 未指定で Vulkan 起動されること、`MI25_BACKEND=hip` 明示で ROCm fallback に切り替わることを確認した。ROCm ビルド構成 (v8533 pin) は fallback 用途で残置し、能動的な維持は行わない。今後 mi25 での llama-server 起動はコード変更前の `MI25_BACKEND=vulkan` prefix なしで、自然に Vulkan バックエンドを使う運用に移行する。
