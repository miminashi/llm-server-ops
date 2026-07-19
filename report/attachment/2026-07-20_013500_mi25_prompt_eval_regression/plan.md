# mi25 Qwen3.6-35B-A3B prompt eval 性能退行の切り分け + fix 試行

**対象**: NEXT_SESSION.md 節「mi25 prompt eval 性能退行の切り分け」(2. 中優先)
**サーバ**: mi25 (10.1.4.13, MI25 x4, `HIP_VISIBLE_DEVICES=0,1,2,3` 常用可)
**モデル**: Qwen3.6-35B-A3B (unsloth GGUF `UD-Q4_K_XL`, KV `q8_0`) — ユーザ呼称「Qwen3.5 35B」の正体
**目標**: 現在 ~70 t/s と報告されている prompt eval を、過去 400+ t/s (Vulkan) / 122.8 t/s (ROCm) と同条件で再測定し、回帰要因を絞り込む。原因が特定できれば fix を試みる。

---

## Context — なぜこの切り分けを行うか

ユーザから「mi25 Qwen3.5 35B の prompt eval が今 ~70 t/s しか出ない、以前は ~400 t/s 出ていた記憶」との報告。過去レポートから、Qwen3.6-35B-A3B (unsloth Q4_K_XL) では次の実測値がある:

| 日付 | Backend | GPU 枚数 | pp @32k | tg | HEAD |
|---|---|---|---|---|---|
| 2026-06-13 | ROCm | 4 (64GB) | **122.8 t/s** | 24.5 | v8533 pin `0fac87b15` |
| 2026-06-14 | Vulkan | 4 (64GB) | **401.4-405.6 t/s** | 15.23 | master |
| 2026-06-18 | Vulkan | 3 (48GB, N=5) | **407.1** / 521.2 @1k | 16.93 | master |
| 2026-06-24 | ROCm | 3 (負荷 30 trial) | **580 t/s** median | 27.3 | v8533 pin |
| 2026-06-24 | Vulkan | 3 (負荷 23 trial) | **1115 t/s** median (成長込み) | 17.9 | master |
| 2026-06-26 | Vulkan | 4 (電力スイープ) | **787-834 t/s** | 16-16.26 | master |

現在の 70 t/s は Vulkan 400 t/s 基準で **-83%**, ROCm 122.8 t/s 基準でも **-43%** の顕著な回帰。過去 400 t/s の記憶はほぼ Vulkan 由来と確定できる。それ以降、次の環境変化があり、回帰要因の候補となる:

- **2026-06-29**: SLOT4 PCIe リンク死 → 物理再装着で 4 枚 x16 復旧 (未実測)
- **2026-07-17**: BIOS 復旧 (MMIOHBase=3TB / MMIO High=512GB / Boot Order UEFI)
- **2026-07-19**: SLOT8=c48c4 (D-2 R1) の 4 枚 64GB 常用へ物理配置移行。副次発見で pp_tps 半減 (SLOT8 化以降) を確認済 — 24h 試験は Qwen3-8B のため 35B は未実測
- **llama.cpp HEAD**: 2026-06-14 以降 master が大きく進行、Vulkan/ROCm ともに退行 PR の可能性

切り分けの主観点は次の 4 つ:
1. **PCIe Gen/Width down train** (BIOS 変更・物理再装着後の実測値未確認)
2. **llama.cpp HEAD 退行** (Vulkan は pin 無し master 追従、退行 PR が挟まった可能性)
3. **ROCm ドライバ版数変化** (最終計測時 vs 現在)
4. **GPU 個体組合せ差** (SLOT8=c48c4 の物理配置化と D-2 R1 で観測された pp_tps 半減の関連)

---

## 実施フェーズ

### Phase 0: 準備 (ロック取得 + 状態記録)

1. `gpu-server` スキル参照、`.claude/skills/gpu-server/scripts/lock-status.sh` で他セッション不在確認
2. `.claude/skills/gpu-server/scripts/lock.sh mi25` でロック取得 (llama-server 実測のため必須)
3. `ssh mi25 "ps aux | grep llama-server | grep -v grep"` で既存プロセス確認 (既存があれば運用中のためユーザ確認、勝手には停止しない)
4. 現在の HEAD / ドライバ / GPU 個体・PCIe 状態を記録 (以下 Phase A へ)

### Phase A: ハードウェア/ソフト環境の実測 (Fix 前に必ずスナップショット)

`report/attachment/<日付>_mi25_prompt_eval_regression/phaseA_*.log` として全て保存:

- `rocm-smi --showuniqueid --showbus --showhw --showvbios --showdriverversion` — 4 枚の Unique ID / BDF / VBIOS / ドライババージョン。過去レポートの物理配置と照合
- `rocm-smi --showcurrentclocks --showpower --showtemp` — SCLK/MCLK 上限張り付き有無、DPM state、温度
- BDF ごとに `sudo -n lspci -vvv -s <BDF> | grep -E 'LnkSta|LnkCap'` — Gen3 x16 期待 (Gen1 や x8 に落ちていれば PCIe down train 確定)。過去 `report/2026-06-14_131713_mi25_gpu4_pcie_dropout.md` L89-91 のコマンド流用。**mi25 は `sudo dmidecode` が NOPASSWD 済 (CLAUDE.md L38) だが `sudo lspci` は未確認**。`-n` (non-interactive) 付きで試行し、`sudo: a password is required` 応答が返る場合は該当コマンドをユーザに提示して実行依頼
- `sudo dmidecode -t 9` (SMBIOS slots) と `lspci -tnnv` の PCIe tree を CLAUDE.md の SLOT↔BDF ルールと突合
- `dmesg | grep -E 'amdgpu|pcieport|link.*down|link.*up|error'` — ドライバ層のリンク再ネゴやエラー
- 参考として `~/llama.cpp` の `git log -1 --format="%H %ci %s"` (ROCm ビルドの pin 確認) と `~/llama.cpp` の master (Vulkan ビルド) の HEAD、それぞれ `build/bin/llama-server --version` / `build-vulkan/bin/llama-server --version`

**判定**:
- **PCIe が Gen3 x16 でない枚数がある** → down train 確定、fix セクションで再装着依頼
- **DPM が sclk/mclk 上限に張り付いていない** → 温度・電力・fan 問題を疑う (現状 idle 中なので推移確認は Phase B/C で)
- **HEAD が 2026-06-18 (`f3e182816`) と大きく違う** → llama.cpp 退行を疑う (Phase D で bisect 候補化)

### Phase B: ROCm baseline 実測 (llama-server timings)

ROCm は `0fac87b15` (v8533) pin 済み。**start.sh は WS 側 (Claude ホスト) から実行**、内部で `ssh -f mi25` して mi25 側 `~/llama.cpp/build/bin/llama-server` を nohup で立ち上げる:

```bash
# WS 側 (llm-server-ops リポジトリのルート) で実行
.claude/skills/llama-server/scripts/start.sh mi25 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
# readiness (既存)
.claude/skills/llama-server/scripts/wait-ready.sh mi25
```

**測定 (3 水準)**:
- **1k prompt**: `curl POST http://10.1.4.13:8000/completion` で ~4000 char の長文 + JSON `n_predict: 1` → `timings.prompt_per_second` を取得。3 回実行、median 採用
- **32k prompt**: `~128k char` の長文 → 3 回実行
- **100k prompt**: `~400k char` の長文 → 1 回 (30 分オーダー、curl max-time 3300s)。過去 `2026-06-13` の「90k 25 分 ≒ 60 t/s」と同じ計測法

**注意**: start.sh は既定で `--n-predict 32768`。プロンプト eval だけ見たい時は curl body に **`n_predict: 1`** を明示 (省略すると 32k トークン生成が走って測定不能になる)。tg 用は別途 `n_predict: 128`。

長文プロンプト用意 (mi25 上で組み立ててから curl):
- 素材は mi25 の `~/llama.cpp/README.md`, `~/llama.cpp/CMakeLists.txt`, `src/llama.cpp` などを連結・repeat
- 事前に `/tokenize` エンドポイント (`curl POST http://10.1.4.13:8000/tokenize` で `{content: "..."}`) で正確なトークン数を確認して長さを調整
- 生成された長文は attachment に prompt_1k.txt / prompt_32k.txt / prompt_100k.txt として保存

**取得指標**:
- `timings.prompt_ms`, `timings.prompt_per_second` (pp t/s)
- `timings.predicted_ms`, `timings.predicted_per_second` (tg t/s。tg 用は別途 1k prompt + `n_predict: 128` で 1 回)
- rocm-smi 並走 (`ssh mi25 'rocm-smi --showuse --showmemuse --showcurrentclocks'` を 5s 間隔で run 中に取得、SCLK/MCLK/VRAM/GPU 使用率の推移を記録)

llama-server 停止: **既存 `stop.sh` を使う** (`pkill` はスキル外の乱暴な手段):
```bash
.claude/skills/llama-server/scripts/stop.sh mi25
```

### Phase C: Vulkan baseline 実測 (llama-server timings)

同じモデル・同じ長文プロンプトを、`MI25_BACKEND=vulkan` で:

```bash
# WS 側で実行
MI25_BACKEND=vulkan .claude/skills/llama-server/scripts/start.sh mi25 \
  "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL" 131072
.claude/skills/llama-server/scripts/wait-ready.sh mi25
```

Phase B と同じ 3 水準で計測。特に **1k prompt** で 521 t/s (2026-06-18 N=5) と近い値が出るか、**32k で 400 t/s** が再現するかが決定的。

**注意点**:
- Vulkan は KV cache q8_0 固定 (f16 は mi25 で高負荷時ダウン実績、`project_mi25_vulkan.md` 由来)
- `GGML_VK_VISIBLE_DEVICES` は start.sh が **`vulkaninfo --summary` で llvmpipe を除いた RADV index を自動検出** (3 枚時 `0,1,2` / 4 枚時 `0,1,2,3`)
- master 追従で pin 無し、現在の HEAD を Phase A で記録済

停止も同じく `stop.sh mi25`。バックエンド切替の前後で llama-server プロセスの完全終了を `ssh mi25 "ps aux | grep llama-server | grep -v grep"` で確認 (VRAM 開放待ちも兼ねる)。

### Phase D: 過去値との比較 + 回帰要因の絞り込み

比較表を作成:

| 項目 | 過去実測 (日付/HEAD) | 現在実測 (Phase B/C) | 差 |
|---|---|---|---|
| ROCm pp @1k | (推定 ~300 t/s) | | |
| ROCm pp @32k | 122.8 t/s (2026-06-13) | | |
| ROCm pp @100k | ~60 t/s (2026-06-13, 90k) | | |
| Vulkan pp @1k | 521.2 t/s (2026-06-18 N=5) | | |
| Vulkan pp @32k | 407.1 t/s (2026-06-18 N=5) | | |
| Vulkan pp @100k | 216.2 t/s (2026-06-14) | | |
| ROCm tg | 24.5 t/s (2026-06-13) | | |
| Vulkan tg | 16.93 t/s (2026-06-18) | | |

**判定ロジック**:
1. **ROCm も Vulkan も両方回帰** → PCIe down train または hardware 側 (電源/温度/クロック) が最有力。Phase A の PCIe LnkSta を再確認
2. **Vulkan だけ回帰、ROCm は 122.8 t/s と一致** → llama.cpp master 側の Vulkan 退行 PR が原因 → bisect 対象
3. **ROCm だけ回帰、Vulkan は 400 t/s と一致** → ROCm ドライバ層 (kfd/rocblas) の変化。dpkg 履歴確認
4. **1k は出るが 32k で落ちる** → メモリ帯域/FA workspace 側の変化。SLOT 個体差 (D-2 R1 副次発見の pp_tps 半減) との整合を検討

### Phase E: fix 試行 (原因別)

Phase D の結論に応じて:

**E-a: PCIe down train の場合**
- 該当 slot の物理再装着 (mi25 レポート `2026-06-14_131713_mi25_gpu4_pcie_dropout.md` 実績)
- Claude は物理作業できないため、**ユーザに物理再装着を依頼**。ロックは維持
- 再装着後、Phase A・B・C を再実行して回復確認

**E-b: llama.cpp master (Vulkan) 退行の場合**
- `~/llama.cpp` を **2026-06-18 の HEAD `f3e182816`** に一時 checkout し、`build-vulkan/` を再ビルド → Phase C を再実行
- 400 t/s @32k に戻れば master 側退行確定 → 退行を挟んだ PR 範囲を `git log --oneline f3e182816..master -- 'ggml-vulkan*' 'ggml/src/vulkan*'` で列挙、代表的な PR を数点 checkout してビルド・実測で bisect 縮小 (時間予算で 3-5 個)
- 退行 PR が特定できれば、その直前 HEAD を新たな Vulkan pin として運用に採用 (start.sh の Vulkan ビルド節に PINNED_COMMIT_VULKAN 変数追加)

**E-c: ROCm ドライバ層退行の場合**
- `dpkg -l | grep -E 'rocm|hip|amdgpu'` で現在版数を記録、`/var/log/apt/history.log*` から前回計測時 (2026-06-13) 以降の変更履歴を抽出
- ロールバック試行は影響大きいため、原因記録のみで留め、次セッションでユーザ判断

**E-d: DPM/thermal/電力の場合**
- `rocm-smi --setperflevel high` で最上位固定を試行 → Phase B/C 再実行
- fan / 温度が高ければ、`rocm-smi --setfan` で PWM 固定を試行 (前例あり)

**E-e: GPU 個体組合せの場合** (SLOT8=c48c4 常用の pp_tps 半減の一般化)
- D-2 R1 の副次発見: SLOT8=c48c4 単独可視化で pp_tps 半減、4 枚並列で SA 期を上回る回復
- 現在 4 枚使用のため、切り分け用に **`HIP_VISIBLE_DEVICES=0,1,3` (SLOT8 除外、3 枚 48GB)** で Phase B/C 再実行し、SLOT8 帰属を確認
- **制御方法の注意**: start.sh は ROCm 時 ENV_PREFIX を空固定 (L256-260)、`HIP_VISIBLE_DEVICES` を渡す口が無い。次のいずれかで対処:
  - **(a) start.sh に一時的なパッチ**: L259 の直後で `[ -n "${MI25_HIP_VISIBLE:-}" ] && ENV_PREFIX="HIP_VISIBLE_DEVICES=$MI25_HIP_VISIBLE"` を追加。実施後 revert
  - **(b) start.sh を経由せず直接起動**: mi25 上で `HIP_VISIBLE_DEVICES=0,1,3 ~/llama.cpp/build/bin/llama-server -m <path> ...` を組み立てて `ssh -f mi25` で発火 (start.sh の LAUNCH_CMD L402-409 を参考に組立)
  - Vulkan 側は `GGML_VK_VISIBLE_DEVICES=0,1,3` を start.sh の自動検出後に上書きする必要があり、こちらも同様に start.sh の L244 直後にオーバーライド分岐を追加、または直起動
- 一般化されれば、実運用は 4 枚並列で問題なし (D-2 R1 と同じ結論)

### Phase F: 回復確認 (fix 後の再実測)

Phase E で fix が入った場合、Phase B/C を再度実行。過去の 400 t/s @32k (Vulkan) と 122.8 t/s (ROCm) を回復目安に判定。

### Phase G: レポート作成

`report/<日付>_mi25_prompt_eval_regression.md` を作成。REPORT.md ルール準拠 (概要必須、タイトル 50 字以内、核心発見サマリに PNG 埋め込み):

- **概要**: 現状 ~70 t/s (ユーザ報告) を過去 400+ t/s と再測定して差分を確定、原因は X、fix は Y (未実施なら「次セッションで実施」)
- **核心発見サマリ**: pp/tg の過去 vs 現在の比較表を PNG グラフ化して埋め込み
- Phase A の状態記録 (PCIe/ドライバ/クロック)
- Phase B/C の詳細測定値 (attachment に curl JSON レスポンス生ログ)
- Phase D の回帰要因絞り込み
- Phase E の fix 試行内容と結果
- Phase F の回復確認値 (fix が入った場合)
- 副次発見 (もしあれば)
- 未完タスク (bisect 範囲、次に追試すべきこと)

添付ファイルは `report/attachment/<日付>_mi25_prompt_eval_regression/` に配置。LFS で自動管理 (前セッション導入済)。

INDEX.md に 1 行追記。

### Phase H: ロック解放

`.claude/skills/gpu-server/scripts/unlock.sh mi25`

---

## クリティカルファイル (触れるもの)

- **書き換えなし**: `~/llama.cpp/` は mi25 上のもので、Phase E-b で bisect が発生する場合のみ一時的に checkout。原則現状復帰
- **書き換えあり (成果物)**:
  - `report/<日付>_mi25_prompt_eval_regression.md` (新規)
  - `report/attachment/<日付>_mi25_prompt_eval_regression/` (新規、Phase A/B/C/E ログ、prompt_*.txt、比較 PNG)
  - `report/INDEX.md` (1 行追加)
  - `NEXT_SESSION.md` (このタスクを完了項目に移動、bisect 未完なら残タスクとして追記)

## 参照ユーティリティ (既存、再利用)

- `.claude/skills/gpu-server/scripts/lock.sh mi25` / `unlock.sh mi25` / `lock-status.sh`
- `.claude/skills/llama-server/scripts/start.sh` (`MI25_BACKEND=vulkan` で Vulkan 切替、モデル DL 自動)
- `.claude/skills/gpu-server/scripts/bmc-screenshot.sh` / `bmc-power.sh` (万一のハング時のみ)
- llama-server `/completion` (timings), `/tokenize` (プロンプト長確認), `/health`

## 時間予算の見積り

- Phase 0: 5 分 (ロック取得)
- Phase A: 15 分 (状態記録)
- Phase B (ROCm): 起動 3 分 + 1k×3 (1 分) + 32k×3 (15 分) + 100k×1 (25-30 分) + tg 3 分 = 約 50 分
- Phase C (Vulkan): 同上 = 約 50 分
- Phase D: 15 分 (比較表作成)
- Phase E: 原因により 15 分 (E-d) - 4-6 時間 (E-b bisect)。最短の場合を除き、時間切れ時は次セッションに繰越
- Phase F (fix 入った場合): 30-90 分
- Phase G (レポート): 45 分
- Phase H: 2 分

**最短**: 約 3.5 時間 (原因が Phase A で明白かつ E-a 物理再装着依頼で終わる場合)
**bisect 発生時**: 6-8 時間 (E-b bisect + F 再測定)

## Verification (end-to-end 動作確認)

1. ロック取得後、`lock-status.sh` で自セッションのロックが記録されていること
2. Phase B/C の各 curl 応答 JSON に `timings.prompt_per_second` が含まれ、attachment に保存されていること
3. Phase D の比較表で過去値 vs 現在値の差が数値化されていること
4. fix 前後 (Phase B/C vs F) の差が定量化され、回復が確認できること
5. レポート内で `curl` コマンドと得られた JSON レスポンス (プロンプト文本文除く) が再現可能な形で残っていること
6. INDEX.md に 1 行追記されていること
7. ロック解放後 `lock-status.sh` で mi25 のロックが消えていること

## リスク・中断方針

- **100k prompt 実測は 25-30 分/回** (70 t/s 想定)、Vulkan 回復時は ~8 分/回。合計ロック占有は最短 3.5h・bisect 発生時 6-8h と長い。他セッションの mi25 利用予定があれば時間帯を要調整
- **物理再装着 (E-a)** が必要な場合、ユーザ物理作業依頼となりロック維持で待機。長時間なら一旦 unlock してユーザ完了後に再取得する運用を選択肢に
- **bisect (E-b)** は master の Vulkan 側変更が多い場合に時間予算超過。3-5 個の候補で打ち切り、残りは NEXT_SESSION.md に繰越 (Phase E 中断時も Phase G のレポートは Phase A-D の内容で作成、fix 未完なら「次セッション追加」節を明記)
- **既存 llama-server が運用中の場合**、Phase B/C のために停止が必要。着手前に `ssh mi25 "ps aux | grep llama-server | grep -v grep"` と `curl -sf http://10.1.4.13:8000/health` で状態確認、非空ならユーザに停止許可依頼
- **異常停止時のロック解放**: Claude セッションが途中で終わっても `.claude/skills/gpu-server/scripts/unlock.sh mi25` を必ず実行 (Phase 全体を try/finally 感覚で、最終ロック解放を Phase H として独立させている理由)
