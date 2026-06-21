# レポートインデックス

`report/` 配下の計測・調査レポートを**ジャンル別**に整理した一覧です（各ジャンル内はファイル名昇順＝時系列順）。

- 全レポートにワンライン説明（`[x]`）を記入済み。
- Qwen3-122B の 128K 化チューニングを軸に、基盤構築 → 探索 → 構成確定 → HEAD再評価 → 軽量モデル移行 → 運用整備、という流れで並べています。

---

## 1. 基盤構築 — Qwen3-122B を 128K で起動する

- [x] [2026-04-10_161331_qwen3-122b-128k-vram-tuning.md](2026-04-10_161331_qwen3-122b-128k-vram-tuning.md) — Qwen3.5-122B-A10B の 128k コンテキスト化に向け VRAM 配置を分析し、複数プランを立案
- [x] [2026-04-16_043659_qwen3-122b-128k-execution.md](2026-04-16_043659_qwen3-122b-128k-execution.md) — 128k コンテキスト化の各プランを実測し、C-1（layer 14-19 GPU 復帰）が 12.06 t/s でベスト確認
- [x] [2026-04-16_051249_qwen3-122b-c2-cuda2-expansion.md](2026-04-16_051249_qwen3-122b-c2-cuda2-expansion.md) — CUDA2 に追加層を載せた C-2/C-2' を検証したが VRAM マージン不足で C-1 を継続採用
- [x] [2026-04-16_053225_qwen3-122b-c3-layer30-swap.md](2026-04-16_053225_qwen3-122b-c3-layer30-swap.md) — 層範囲を 25-30 にスワップした C-3 が CUDA1/2 マージン対称を保ちつつ 12.19 t/s を達成

## 2. ボトルネック解析と環境特性の把握

- [x] [2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile.md](2026-04-16_054649_qwen3-122b-c3-eval-bottleneck-profile.md) — C-3 構成のボトルネックを計測し、GPU SM 使用率 4-5% で CPU（Xeon MoE 演算）が律速と特定
- [x] [2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive.md](2026-04-16_062447_qwen3-122b-c3-bottleneck-deepdive.md) — perf stat で CPU 律速の詳細を解析し、numactl -N1 -m1 で NUMA リモートアクセス 97% 削減・+4.3% 改善
- [x] [2026-04-16_072324_qwen3-122b-c3-numa-phaseC.md](2026-04-16_072324_qwen3-122b-c3-numa-phaseC.md) — NUMA 配置3構成を比較し、interleave=all（C-C2）が 11.91 t/s でスレッド固定比 +60.7% を記録
- [x] [2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md](2026-04-16_225920_qwen3-122b-c3-phaseE-smt.md) — SMT半減・taskset・--numa isolateを試しC-D3超えは得られず、長時間後の速度低下を示唆
- [x] [2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility.md](2026-04-17_012859_qwen3-122b-c3-phaseF-reproducibility.md) — C-E5(--numa isolate)とC-D3の再現性を交互計測し、C-E5の+3%超えを確認できず採用見送りを確定
- [x] [2026-04-17_035831_qwen3-122b-c3-phaseG-longevity.md](2026-04-17_035831_qwen3-122b-c3-phaseG-longevity.md) — 60分稼働では劣化ゼロ、idle後の古プロセスで−5.6%を観測し劣化は特殊条件に限定と判明
- [x] [2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md](2026-04-17_082738_qwen3-122b-c3-phaseH-idle-poll.md) — --poll 0/50でidle 60分後の劣化を確認せず、--poll 50はベース速度−2.2%で非採用確定

## 3. コンテキスト長 × FlashAttention × KV量子化 の探索

- [x] [2026-04-16_150717_qwen3-122b-c3-phaseD.md](2026-04-16_150717_qwen3-122b-c3-phaseD.md) — 単一NUMAノード固定(−N1 −m1)とスレッド数を検証し、C-D3構成が基準比+26%の最速と判明
- [x] [2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext.md](2026-04-17_173156_qwen3-122b-c3-phaseI-longcontext.md) — 長コンテキスト(〜131k)でのeval/prompt速度プロファイルを計測し、対話上限16k・非同期上限64kを定量化
- [x] [2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab.md](2026-04-17_200519_qwen3-122b-c3-phaseJ-flashattn-ab.md) — flash-attn OFF時はq8_0 KV量子化と非互換でSegfaultとなり、fa=1が速度ではなく機能要件と確定
- [x] [2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab.md](2026-04-18_025221_qwen3-122b-c3-phaseK-f16-flashattn-ab.md) — f16 KV+fa=0はctx=16kでcompute buffer 18GB超のOOMとなり、P100ではfa=1が量子化有無に関わらず必須と確定
- [x] [2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan.md](2026-04-18_070129_qwen3-122b-c3-phaseL-fa0-ctx-scan.md) — ctx=4096でfa=0起動を実証しfa=1のVRAM削減効果(−4.8GB)とeval速度寄与(+3%)を分離定量化
- [x] [2026-04-18_220428_qwen3-122b-c3-phaseM-ctx-scan.md](2026-04-18_220428_qwen3-122b-c3-phaseM-ctx-scan.md) — fa=0でctx=1k〜4kをスキャンしcompute bufferの3係数分離(定数項・線形・べき則)に成功
- [x] [2026-04-19_024430_qwen3-122b-c3-phaseN-ctx8k-boundary.md](2026-04-19_024430_qwen3-122b-c3-phaseN-ctx8k-boundary.md) — fa=0でctx=8192がOOM境界と確定、fa=1のcompute bufferがO(n²)→O(n)に変わる機構を定量的に解明
- [x] [2026-04-19_033924_qwen3-122b-c3-phaseO-fa1-ctx16k.md](2026-04-19_033924_qwen3-122b-c3-phaseO-fa1-ctx16k.md) — fa=1でctx=16kの5点フィットを試みた結果、compute bufferがctx≥8192で飽和する区分モデルの必要性を発見

## 4. batch / ubatch 境界の微細探索（Phase P–Sb）

- [x] [2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan.md](2026-04-19_051604_qwen3-122b-c3-phaseP-fa1-batch-scan.md) — -bではなく-ubがcompute bufferの真のドライバと確定し、ub=2048でVRAM73%削減+eval+1.5%のダブルウィンを発見
- [x] [2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md](2026-04-19_074335_qwen3-122b-c3-phaseQ-fa1-ub-lower-bound.md) — -ubをub=128まで下限探索しeval速度のピークがub=2048と確定、本番既定値を-ub=2048に決定
- [x] [2026-04-19_085127_qwen3-122b-c3-phaseR-ctx131k-ub2048.md](2026-04-19_085127_qwen3-122b-c3-phaseR-ctx131k-ub2048.md) — 本番想定ctx=131k×-ub=2048で安定起動・120kプロンプト推論を実証しstart.sh既定値変更の根拠を確立
- [x] [2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints.md](2026-04-19_105737_qwen3-122b-c3-phaseR-ctx3-midpoints.md) — ctx中間4点を追加計測しCUDA1/2/Hostの線形モデルを4点で検証、CUDA0のみ二次モデルへの置換が必要と判明
- [x] [2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md](2026-04-19_120715_qwen3-122b-c3-phaseS-ub-ctx-2d.md) — ub×ctxの2軸16点フィットでCUDA3のub純比例性を確定し、CUDA0の単変量モデル破綻(+137%)を定量化
- [x] [2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary.md](2026-04-19_151311_qwen3-122b-c3-phaseSb-ub-boundary.md) — 256トークン刻みで CUDA0 区分境界を走査し ub*∈(1536,1792] に初期絞り込み
- [x] [2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary.md](2026-04-19_161658_qwen3-122b-c3-phaseSbfine-ub-boundary.md) — 64トークン刻みで境界を再走査し ub*∈(1536,1600] に精度向上
- [x] [2026-04-19_172104_qwen3-122b-c3-phaseSbfine2-ub16tok.md](2026-04-19_172104_qwen3-122b-c3-phaseSbfine2-ub16tok.md) — 16トークン刻みで境界を絞り込み ub*∈(1584,1600] を確定
- [x] [2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md](2026-04-19_181540_qwen3-122b-c3-phaseSbfine3-ub1tok.md) — 1〜4トークン精度で ub*∈(1585,1586]（推定≈1585.18）を確定し新 eval 記録
- [x] [2026-04-19_192631_qwen3-122b-c3-phaseSbsrc-threshold-hunt.md](2026-04-19_192631_qwen3-122b-c3-phaseSbsrc-threshold-hunt.md) — llama.cpp scheduler ソースを解析し slope 由来を特定・1586 は動的計算値と判明
- [x] [2026-04-19_203607_qwen3-122b-c3-phaseSb-alloc.md](2026-04-19_203607_qwen3-122b-c3-phaseSb-alloc.md) — ggml-alloc.c を詳解し候補D（1MiB境界）を棄却、真因を候補J/I-cに絞り込み
- [x] [2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary.md](2026-04-19_210603_qwen3-122b-c3-phaseSbctx-boundary.md) — ctx ∈{16k,65k,131k} 走査で候補J棄却、slope の ctx 依存性（cross項）を発見
- [x] [2026-04-19_221314_qwen3-122b-c3-phaseSbfa0.md](2026-04-19_221314_qwen3-122b-c3-phaseSbfa0.md) — fa=0 で候補K事実上棄却、ctx≥32k が CUDA1 OOM で起動不能と判明
- [x] [2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload.md](2026-04-19_232618_qwen3-122b-c3-phaseSbfa0offload.md) — OT拡張で fa=0×ctx=32k を実現し候補L（FA tile量子化副作用）を support、slope∝ctx 確定

## 5. eval 安定性・再現性の反復計測（Seval シリーズ）

約60本の連続計測。長いため折りたたみ。

<details>
<summary>Seval 全59本を表示</summary>

- [x] [2026-04-20_003250_qwen3-122b-c3-phaseSeval.md](2026-04-20_003250_qwen3-122b-c3-phaseSeval.md) — 初回5-run計測で1-run参照値が全3ub再現せず、run内σは極小だがセッション間ゆらぎが浮上
- [x] [2026-04-20_013006_qwen3-122b-c3-phaseSevalcross.md](2026-04-20_013006_qwen3-122b-c3-phaseSevalcross.md) — 別セッション追加でub依存のセッション間ゆらぎ確定、ub=1586のみsession_independent（pooled σ=0.010）
- [x] [2026-04-20_022922_qwen3-122b-c3-phaseSeval3s.md](2026-04-20_022922_qwen3-122b-c3-phaseSeval3s.md) — n=3でub=1586のsession_independent主張が破綻、ub=1664単調増加・ub=1584 trimodal確認
- [x] [2026-04-20_032317_qwen3-122b-c3-phaseSeval4s.md](2026-04-20_032317_qwen3-122b-c3-phaseSeval4s.md) — S4でub=1584が−0.728大崩壊・ub=1664単調増加仮説も棄却、S4全ub共通下振れ発生
- [x] [2026-04-20_041308_qwen3-122b-c3-phaseSeval5s.md](2026-04-20_041308_qwen3-122b-c3-phaseSeval5s.md) — ub=1584がS5で復帰（崩壊頻度1/5=20%確定）、ub=1586がsession_dominated転落・最ロバスト称号崩壊
- [x] [2026-04-20_050710_qwen3-122b-c3-phaseSeval6s.md](2026-04-20_050710_qwen3-122b-c3-phaseSeval6s.md) — ub=1586初崩壊・ub=1664過去最高15.292でpeak順序mode C（1664>1584>1586）新発見、3ub全1位経験
- [x] [2026-04-20_061007_qwen3-122b-c3-phaseSeval7s.md](2026-04-20_061007_qwen3-122b-c3-phaseSeval7s.md) — mode Cは単発でS7にmode B復帰、ub=1664崩壊57.1%で過半数、ub別独立変動モデル決定的支持
- [x] [2026-04-20_075044_qwen3-122b-c3-phaseSeval8s.md](2026-04-20_075044_qwen3-122b-c3-phaseSeval8s.md) — mode D（1664>1586>1584）初出現、ub=1664が15.380で過去最高更新、3帯分布モデルへ進化
- [x] [2026-04-20_080258_qwen3-122b-c3-phaseSeval9s.md](2026-04-20_080258_qwen3-122b-c3-phaseSeval9s.md) — ub=1586の減衰振動モデル棄却（再崩壊−0.430）、ub=1664史上最大下落−0.778、ub=1584推奨1位へ
- [x] [2026-04-20_085556_qwen3-122b-c3-phaseSeval10s.md](2026-04-20_085556_qwen3-122b-c3-phaseSeval10s.md) — ub=1586がMarkov連鎖（崩壊20%/復帰100%）を2周期目で支持、ub=1664の3帯固定モデル棄却
- [x] [2026-04-20_094934_qwen3-122b-c3-phaseSeval11s.md](2026-04-20_094934_qwen3-122b-c3-phaseSeval11s.md) — mode A 5度目で単独1位、ub=1664が初の崩壊閾値超え復帰15.038、Markov予測成立を確認
- [x] [2026-04-20_104503_qwen3-122b-c3-phaseSeval12s.md](2026-04-20_104503_qwen3-122b-c3-phaseSeval12s.md) — mode A 6度目で独走拡大、ub=1664の中帯一過性確認（1session後に再崩壊）、3ub同方向下振れ初観測
- [x] [2026-04-20_113929_qwen3-122b-c3-phaseSeval13s.md](2026-04-20_113929_qwen3-122b-c3-phaseSeval13s.md) — peak order 5種目（1586>1664>1584）初観測、ub=1584が2回目崩壊・ub=1586が13session最高15.481で3ub同時大変動
- [x] [2026-04-20_123152_qwen3-122b-c3-phaseSeval14s.md](2026-04-20_123152_qwen3-122b-c3-phaseSeval14s.md) — S13の5大異常が全て1session限定で回帰、ub=1584崩壊「翌session正常復帰」2/2確定・9session周期仮説
- [x] [2026-04-20_132400_qwen3-122b-c3-phaseSeval15s.md](2026-04-20_132400_qwen3-122b-c3-phaseSeval15s.md) — ub=1584史上最深崩壊13.964・ub=1586が2session間隔で上方離脱再発、pool差が初めて逆転しub=1586単独1位候補へ
- [x] [2026-04-20_142019_qwen3-122b-c3-phaseSeval16s.md](2026-04-20_142019_qwen3-122b-c3-phaseSeval16s.md) — ub=1586 peak 1位4連続達成・ub=1584が史上最大+1.174回復、ub=1586単独1位がpool/頻度/Welch t三軸で確定
- [x] [2026-04-20_151741_qwen3-122b-c3-phaseSeval17s.md](2026-04-20_151741_qwen3-122b-c3-phaseSeval17s.md) — mode C 11session ぶり再発でub=1586の4連続達成失敗、ub=1664が15.396でpool max更新・上帯⇔peak 1位完全連動確定
- [x] [2026-04-20_161642_qwen3-122b-c3-phaseSeval18s.md](2026-04-20_161642_qwen3-122b-c3-phaseSeval18s.md) — ub=1584が3session連続崩壊で2session周期仮説否定、ub=1664が上帯2連続初記録・3ub sig 2session連続の高エントロピーで18session体系確定
- [x] [2026-04-20_212313_qwen3-122b-c3-phaseSeval19s.md](2026-04-20_212313_qwen3-122b-c3-phaseSeval19s.md) — cool time 4時間21分（長時間帯初観測）＋ub=1664が pool 95-run min 14.298に急落、Welch 2ub sig初観測
- [x] [2026-04-20_231300_qwen3-122b-c3-phaseSeval20s.md](2026-04-20_231300_qwen3-122b-c3-phaseSeval20s.md) — cool time通常帯復帰＋ub=1664下帯2連続初観測、Welch 3ub sig回帰でS19 2ub sig類型が単発性と実証
- [x] [2026-04-20_232604_qwen3-122b-c3-phaseSeval21s.md](2026-04-20_232604_qwen3-122b-c3-phaseSeval21s.md) — ub=1664下帯2連続→上帯復帰で3連続episode不成立、mode_E 3回目・Welch 2ub sig対称subtype初観測
- [x] [2026-04-21_002703_qwen3-122b-c3-phaseSeval22s.md](2026-04-21_002703_qwen3-122b-c3-phaseSeval22s.md) — ub=1586が史上最低13.844に急落（全Δ中2位）、σ_pool 1586>1584逆転初観測・崩壊頻度1664が50%到達
- [x] [2026-04-21_012929_qwen3-122b-c3-phaseSeval23s.md](2026-04-21_012929_qwen3-122b-c3-phaseSeval23s.md) — S22の1586大崩壊が単発異常と判定（+1.289大回復）、σ_pool逆転2連続でregime change仮説強化
- [x] [2026-04-21_023213_qwen3-122b-c3-phaseSeval24s.md](2026-04-21_023213_qwen3-122b-c3-phaseSeval24s.md) — 1584崩壊/非/崩壊のalternating 2-hop新類型確立、σ_pool逆転3連続でregime change確定
- [x] [2026-04-21_032417_qwen3-122b-c3-phaseSeval25s.md](2026-04-21_032417_qwen3-122b-c3-phaseSeval25s.md) — 1584のalternating cycle 4-hopへ拡張確立、σ_pool逆転4連続・cool time zone線形モデル要精緻化
- [x] [2026-04-21_041752_qwen3-122b-c3-phaseSeval26s.md](2026-04-21_041752_qwen3-122b-c3-phaseSeval26s.md) — 1584 alternating 5-hop完全cycle確立、σ_pool逆転幅が0.009→0.012に拡大・zone線形モデル0.94x近接fit
- [x] [2026-04-21_051039_qwen3-122b-c3-phaseSeval27s.md](2026-04-21_051039_qwen3-122b-c3-phaseSeval27s.md) — 1584 alternating 6-hop cycle確立、ub=1664が「下→上→上」2-hop transition新類型確立
- [x] [2026-04-21_060329_qwen3-122b-c3-phaseSeval28s.md](2026-04-21_060329_qwen3-122b-c3-phaseSeval28s.md) — 1584 alternating 6-hopにてcycle BREAK、ub=1664が上帯3連続stay「上帯stable regime」初観測
- [x] [2026-04-21_065614_qwen3-122b-c3-phaseSeval29s.md](2026-04-21_065614_qwen3-122b-c3-phaseSeval29s.md) — 1584が非崩壊3連続・高安定phase開始、ub=1664「上帯stable regime」が3連続限定と確定
- [x] [2026-04-21_074512_qwen3-122b-c3-phaseSeval30s.md](2026-04-21_074512_qwen3-122b-c3-phaseSeval30s.md) — 3ub同時崩壊30session初観測、Welch全ub sig負方向初観測・ub=1664 pool min 14.213更新
- [x] [2026-04-21_083727_qwen3-122b-c3-phaseSeval31s.md](2026-04-21_083727_qwen3-122b-c3-phaseSeval31s.md) — triple collapse翌sessionに全ub回復（1-session限定確定）、Welch全ub sig正方向初観測でS30との鏡像確認
- [x] [2026-04-21_093107_qwen3-122b-c3-phaseSeval32s.md](2026-04-21_093107_qwen3-122b-c3-phaseSeval32s.md) — cool time境界帯18分超え初観測、|t_welch|歴代2位27.69・σ_pool regime change 11連続最長更新
- [x] [2026-04-21_102734_qwen3-122b-c3-phaseSeval33s.md](2026-04-21_102734_qwen3-122b-c3-phaseSeval33s.md) — mode_F初観測で6mode全観測達成、1586 alternatingが2連続崩壊に崩れ「崩壊継続regime」へ移行
- [x] [2026-04-21_112228_qwen3-122b-c3-phaseSeval34s.md](2026-04-21_112228_qwen3-122b-c3-phaseSeval34s.md) — mode_F 2連続観測で単発限定仮説否定・1586が3連続崩壊初観測で「崩壊継続regime」確定
- [x] [2026-04-21_121546_qwen3-122b-c3-phaseSeval35s.md](2026-04-21_121546_qwen3-122b-c3-phaseSeval35s.md) — 1586の3連続崩壊をbreak回復、1584が崩壊11例目・3cycleへ進展・mode_F 2session限定確定
- [x] [2026-04-21_130908_qwen3-122b-c3-phaseSeval36s.md](2026-04-21_130908_qwen3-122b-c3-phaseSeval36s.md) — mode_E 2連続初観測で連続化regime initial、1584が2連続崩壊初観測・1586は高値帯定着候補
- [x] [2026-04-21_140342_qwen3-122b-c3-phaseSeval37s.md](2026-04-21_140342_qwen3-122b-c3-phaseSeval37s.md) — mode_E 3連続regime確定、1584が3連続崩壊初・1664が下→中→上 3帯遷移初観測・1586が高値帯定着確定
- [x] [2026-04-21_145730_qwen3-122b-c3-phaseSeval38s.md](2026-04-21_145730_qwen3-122b-c3-phaseSeval38s.md) — ub=1664が30session ぶりpool max 15.534更新・mode_D復活でmode_E 3連続break、1584崩壊3連続が3session限定で終結
- [x] [2026-04-21_155525_qwen3-122b-c3-phaseSeval39s.md](2026-04-21_155525_qwen3-122b-c3-phaseSeval39s.md) — ub=1664が歴代最大級Δ=-1.057で下帯崩壊、pool max更新翌回の深崩壊パターン初観測
- [x] [2026-04-21_164936_qwen3-122b-c3-phaseSeval40s.md](2026-04-21_164936_qwen3-122b-c3-phaseSeval40s.md) — mode_B 2連続・ub=1586高値帯6連続いずれも初達成、ub=1664は中帯復帰
- [x] [2026-04-21_174520_qwen3-122b-c3-phaseSeval41s.md](2026-04-21_174520_qwen3-122b-c3-phaseSeval41s.md) — mode_F 7session ぶり復帰、ub=1586/1664 double collapse 2例目(32session ぶり)
- [x] [2026-04-21_184122_qwen3-122b-c3-phaseSeval42s.md](2026-04-21_184122_qwen3-122b-c3-phaseSeval42s.md) — ub=1586が14.781→15.527へΔ+0.746大幅回復、ub=1664は4連続崩壊中帯維持
- [x] [2026-04-21_194635_qwen3-122b-c3-phaseSeval43s.md](2026-04-21_194635_qwen3-122b-c3-phaseSeval43s.md) — ub=1584がΔ=-0.607で崩壊復帰、ub=1664が下帯転落し5連続崩壊初達成
- [x] [2026-04-21_214018_qwen3-122b-c3-phaseSeval44s.md](2026-04-21_214018_qwen3-122b-c3-phaseSeval44s.md) — ub=1584がΔ+0.766で崩壊1session限定fix、ub=1664は6連続崩壊・過半数超え
- [x] [2026-04-21_224532_qwen3-122b-c3-phaseSeval45s.md](2026-04-21_224532_qwen3-122b-c3-phaseSeval45s.md) — mode_A が16session ぶり復帰、ub=1664は7連続崩壊・下帯3連続を初達成
- [x] [2026-04-21_234926_qwen3-122b-c3-phaseSeval46s.md](2026-04-21_234926_qwen3-122b-c3-phaseSeval46s.md) — ub=1664が8連続崩壊・下帯4連続・単独崩壊3連続を初達成、A-B交互パターン確立
- [x] [2026-04-22_005619_qwen3-122b-c3-phaseSeval47s.md](2026-04-22_005619_qwen3-122b-c3-phaseSeval47s.md) — 日またぎ初計測でub=1586が14.403へ超大幅崩壊(Δ=-0.823)、inter-day driftの非対称性観測
- [x] [2026-04-22_010836_qwen3-122b-c3-phaseSeval48s.md](2026-04-22_010836_qwen3-122b-c3-phaseSeval48s.md) — ub=1586が14→15帯へΔ+0.702大幅回復、ub=1664 pool min 14.214新記録、mode_A 19session ぶり復帰
- [x] [2026-04-22_020513_qwen3-122b-c3-phaseSeval49s.md](2026-04-22_020513_qwen3-122b-c3-phaseSeval49s.md) — mode_A 2連続初達成、|Δ_max|=0.047の超安定記録、intra-day 3session連続初達成
- [x] [2026-04-22_025948_qwen3-122b-c3-phaseSeval50s.md](2026-04-22_025948_qwen3-122b-c3-phaseSeval50s.md) — ub=1664が11連続崩壊を破りnormal復帰(Δ+0.852)、ub=1584は崩壊転落でmode_E大転換
- [x] [2026-04-22_035441_qwen3-122b-c3-phaseSeval51s.md](2026-04-22_035441_qwen3-122b-c3-phaseSeval51s.md) — ub=1664が1session normal挟み再崩壊の"11+1+2"パターン確立、intra-day 5session連続初
- [x] [2026-04-22_044633_qwen3-122b-c3-phaseSeval52s.md](2026-04-22_044633_qwen3-122b-c3-phaseSeval52s.md) — mode_B 2連続初達成、"11+1+2"崩壊パターン拡張、全ub負方向Δの(-/-/-)初登場
- [x] [2026-04-22_054754_qwen3-122b-c3-phaseSeval53s.md](2026-04-22_054754_qwen3-122b-c3-phaseSeval53s.md) — ub=1586がΔ=-1.110で崩壊復帰(歴代3位)、|Δ|>0.5が4連続達成、Welch |t|>60帯初到達
- [x] [2026-04-22_072412_qwen3-122b-c3-phaseSeval54s.md](2026-04-22_072412_qwen3-122b-c3-phaseSeval54s.md) — ub=1586がΔ+1.224で即回復(歴代3位)、|Δ|>0.5が5連続・|Δ|>1.0が4例目すべてub=1586担当
- [x] [2026-04-22_081858_qwen3-122b-c3-phaseSeval55s.md](2026-04-22_081858_qwen3-122b-c3-phaseSeval55s.md) — ub=1586が1-normal-gap崩壊パターン2例目、|Δ|>0.5が6連続新記録、intra-day 9session連続初
- [x] [2026-04-22_091115_qwen3-122b-c3-phaseSeval56s.md](2026-04-22_091115_qwen3-122b-c3-phaseSeval56s.md) — ub=1586が2連続崩壊初達成、ub=1584が歴代最高値15.473を更新、intra-day 10session初
- [x] [2026-04-22_100502_qwen3-122b-c3-phaseSeval57s.md](2026-04-22_100502_qwen3-122b-c3-phaseSeval57s.md) — 全ub同時崩壊のtriple collapse初達成(57session目)、ub=1586は3連続崩壊初達成
- [x] [2026-04-22_110239_qwen3-122b-c3-phaseSeval58s.md](2026-04-22_110239_qwen3-122b-c3-phaseSeval58s.md) — triple collapse 1session単発fix確認、ub=1586は4連続崩壊に拡張、intra-day 12session初
- [x] [2026-04-22_140055_qwen3-122b-c3-phaseSeval59s.md](2026-04-22_140055_qwen3-122b-c3-phaseSeval59s.md) — ub=1586が5連続崩壊最長記録更新、ub=1584がΔ=-0.834で崩壊転落しdouble collapse再発

</details>

## 6. 構成最適化（Phase T: KV量子化 / split-mode / threads / OT / ub）

- [x] [2026-04-22_141232_qwen3-122b-c3-phaseT1-kv-quant.md](2026-04-22_141232_qwen3-122b-c3-phaseT1-kv-quant.md) — KV量子化(f16/q8_0/q4_0/q4_1)×ubスイープ、q8_0が最良も歴代記録未更新
- [x] [2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode.md](2026-04-22_165843_qwen3-122b-c3-phaseT2-splitmode.md) — split-mode row vs layer 比較、row は -15〜-22% 大幅劣化で layer 確定
- [x] [2026-04-22_181614_qwen3-122b-c3-phaseT3-threads.md](2026-04-22_181614_qwen3-122b-c3-phaseT3-threads.md) — threads 24〜40スイープ、threads=32が最良14.860 t/s(+0.53%)
- [x] [2026-04-22_183234_qwen3-122b-c3-phaseT4-ot-layer-range.md](2026-04-22_183234_qwen3-122b-c3-phaseT4-ot-layer-range.md) — OT層範囲スイープ、B32×thr40で15.494 t/s達成・歴代最高Phase S更新
- [x] [2026-04-22_201929_qwen3-122b-c3-phaseT5-ot-aggressive.md](2026-04-22_201929_qwen3-122b-c3-phaseT5-ot-aggressive.md) — OT積極削減B28で16.024 t/s達成、Phase D比+6.6%の新歴代最高
- [x] [2026-04-22_230941_qwen3-122b-c3-phaseT5e-ctx-ub-apply.md](2026-04-22_230941_qwen3-122b-c3-phaseT5e-ctx-ub-apply.md) — B28×ub=512でeval 16.380 t/s達成、ub主因子・ctx=32k最良と確定
- [x] [2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep.md](2026-04-22_232010_qwen3-122b-c3-phaseT5f-ub-fine-sweep.md) — ub微細スイープでub=512最適・16.455 t/s達成、eval/promptパレート定量化
- [x] [2026-04-23_014104_qwen3-122b-c3-phaseT5a-ot-redistribution.md](2026-04-23_014104_qwen3-122b-c3-phaseT5a-ot-redistribution.md) — OT再配分B18で18.006 t/s達成、T-5f比+9.4%・OT削減が最大ブースター確定
- [x] [2026-04-23_034442_qwen3-122b-c3-phaseT5a-ub-resweep.md](2026-04-23_034442_qwen3-122b-c3-phaseT5a-ub-resweep.md) — B18×ub再スイープ、ub=256で18.103 t/s(補正後18.209)の新歴代最高
- [x] [2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr.md](2026-04-23_053125_qwen3-122b-c3-phaseT5a-thr.md) — B18×ub=256でthreads再スイープ、大drift(-2.44%)でthreads=40確定・新記録なし
- [x] [2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts.md](2026-04-23_074652_qwen3-122b-c3-phaseT5a-ts.md) — B16+tensor-splitでOOM回避、18.417 t/s達成・ts明示副作用なし確認
- [x] [2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2.md](2026-04-23_093629_qwen3-122b-c3-phaseT5a-ts2.md) — B14×ts+OT-bで歴代最高18.664 t/s、OTパターン差が配分より支配的と判明

## 7. デフォルト構成の確定（Phase U）

- [x] [2026-04-23_132933_qwen3-122b-u1-specckpt-baseline.md](2026-04-23_132933_qwen3-122b-u1-specckpt-baseline.md) — spec ckpt有効化検証、B14bではVRAM不足でOOM・tight配置と両立不可を確認
- [x] [2026-04-23_171459_qwen3-122b-u1ext-specckpt-relaxed.md](2026-04-23_171459_qwen3-122b-u1ext-specckpt-relaxed.md) — B18緩和構成でspec decoding完走、ON時eval -22〜-33%遅延で不採用確定
- [x] [2026-04-23_173141_qwen3-122b-c3-phaseU2-cache-ram.md](2026-04-23_173141_qwen3-122b-c3-phaseU2-cache-ram.md) — cache-ramによるTTFT -98%短縮を確認、サイズ差なくdefault維持で問題なし
- [x] [2026-04-24_063651_qwen3-122b-u4-gateup-fused.md](2026-04-24_063651_qwen3-122b-u4-gateup-fused.md) — gate/up fused GGUFでeval -16.7%回帰、本構成では採用禁忌と確定
- [x] [2026-04-24_081326_qwen3-122b-u5-ctx128k-fit-map.md](2026-04-24_081326_qwen3-122b-u5-ctx128k-fit-map.md) — ctx=128k FITマップ作成、B14b_ts=11,12,13,14が安定fit・9構成を特定
- [x] [2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default.md](2026-04-24_085353_qwen3-122b-c3-phaseU6-ctx128k-default.md) — ctx=128kデフォルト構成確定、B14b/ub=512/ts=11,12,13,14を推奨として決定
- [x] [2026-04-24_163240_qwen3-122b-startup-script-128k-default.md](2026-04-24_163240_qwen3-122b-startup-script-128k-default.md) — U-6確定構成を起動スクリプトに実装・実機検証、shellバグ修正で1コマンド起動成立

## 8. Marathon ベンチ — llama.cpp HEAD 総合再評価

- [x] [2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins.md](2026-05-16_183834_qwen3-122b-bench-marathon-phaseA-quickwins.md) — Marathon PhaseA：HEAD が U-6 比 +1.3〜+4.5% 改善を確認、--main-gpu 1 が単独で有意な追加改善
- [x] [2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail.md](2026-05-16_195031_qwen3-122b-bench-marathon-phaseB-spec-fail.md) — Marathon PhaseB：ngram spec 系は全種 context checkpoint OOM で起動不能、本構成では実用不可と確定
- [x] [2026-05-16_221912_qwen3-122b-bench-marathon-phaseC-sweep.md](2026-05-16_221912_qwen3-122b-bench-marathon-phaseC-sweep.md) — Marathon PhaseC：--threads 32 で +0.66%、-ub 768 で prompt +16.2%（eval -1.6%）のトレードオフを確認
- [x] [2026-05-16_232150_qwen3-122b-bench-marathon-phaseD-arch.md](2026-05-16_232150_qwen3-122b-bench-marathon-phaseD-arch.md) — Marathon PhaseD：B12/B16/tensor-parallel/SWA を検証、B14（現行）がCPUオフロード層数の最適点と確認
- [x] [2026-05-17_045807_qwen3-122b-bench-marathon-phaseE-final.md](2026-05-17_045807_qwen3-122b-bench-marathon-phaseE-final.md) — Marathon PhaseE：M1+T1_th32 組合せはセッション間 drift で期待累積効果が打ち消し、単独フラグ追加では有意改善せず
- [x] [2026-05-17_045809_qwen3-122b-bench-marathon-summary.md](2026-05-17_045809_qwen3-122b-bench-marathon-summary.md) — Marathon 総括：HEAD の累積改善 +1.3〜+4.5% が主要成果、spec・アーキ変更は全て失敗または効果なし

## 9. Qwen3.6-35B-A3B への移行と実用品質調整

- [x] [2026-05-19_030233_qwen36-add-and-skill-update.md](2026-05-19_030233_qwen36-add-and-skill-update.md) — Qwen3.6（27B/35B-A3B、MTP版含む計4モデル）をダウンロードし、start.sh/SKILL.md をMTP自動検出対応に拡張
- [x] [2026-05-21_043823_default_llm_qwen36_35b.md](2026-05-21_043823_default_llm_qwen36_35b.md) — デフォルトLLMを Qwen3.6-35B-A3B-UD-Q4_K_XL に切替（実ワークロードベンチで122B比 judge +0.55、速度×2.9）
- [x] [2026-05-25_115133_qwen36_loop_sampling_fix.md](2026-05-25_115133_qwen36_loop_sampling_fix.md) — Qwen3.x の thinking ループ対策として presence_penalty + DRY をデフォルト有効化
- [x] [2026-05-26_022707_qwen36_sampler_url_recall_fix.md](2026-05-26_022707_qwen36_sampler_url_recall_fix.md) — DRY の allowed-length 緩和と sequence-breaker 追加で URL/IP 数字書換副作用を解消
- [x] [2026-05-26_143817_qwen36_sampler_path_recall_fix.md](2026-05-26_143817_qwen36_sampler_path_recall_fix.md) — DRY を完全無効化（multiplier=0）し、長パスのtool-call中途切断問題を根本解消
- [x] [2026-05-26_164557_qwen36_presence_penalty_loop_refix.md](2026-05-26_164557_qwen36_presence_penalty_loop_refix.md) — presence_penalty を 0.5→1.0 へ再引き上げ、DRY=0 を維持しつつ verbatim ループ再発を抑制
- [x] [2026-05-29_133058_qwen36_max_context.md](2026-05-29_133058_qwen36_max_context.md) — Qwen3.6-35B-A3B の実用最大コンテキストは 262K（-ub 512 必須）、YaRN で 524K 拡張も可能と確認
- [x] [2026-05-29_134431_qwen36_dry08_redeploy_pathfix.md](2026-05-29_134431_qwen36_dry08_redeploy_pathfix.md) — DRY=0 修正をコミットし稼働サーバへ反映、未push放置が招いたパス破損・タイムアウト問題を解消

## 10. 運用ツール・インフラ整備／保守

- [x] [2026-04-04_224541_fix_hf_token_validation.md](2026-04-04_224541_fix_hf_token_validation.md) — HF_TOKEN ペースト時にCR文字が混入して401エラーになる問題を特定し、トリミング処理で修正
- [x] [2026-05-12_051827_llama_up_down_scripts.md](2026-05-12_051827_llama_up_down_scripts.md) — llama-up.sh / llama-down.sh 統合スクリプトを新規追加し、電源ON〜llama-server起動〜停止を1コマンド化
- [x] [2026-05-12_105909_llama_down_unlock_order_fix.md](2026-05-12_105909_llama_down_unlock_order_fix.md) — llama-down.sh のStep3/4（power off → unlock）順序を入れ替え、電源断後のSSH切断でunlockが失敗するバグを修正
- [x] [2026-05-13_030350_wrapper_hang_fix.md](2026-05-13_030350_wrapper_hang_fix.md) — start.sh の ssh -f に fd リダイレクト追加、パイプ経由で llama-up.sh がハングし続ける問題を解消
- [x] [2026-05-13_050211_readme_global_install_doc.md](2026-05-13_050211_readme_global_install_doc.md) — README にグローバルインストール手順を追記し、既存スクリプトのドキュメントを整備
- [x] [2026-05-13_071824_llama_up_down_global_install.md](2026-05-13_071824_llama_up_down_global_install.md) — llama-up.sh / llama-down.sh をグローバルインストール対応化し、gpu-server への相対パス参照を絶対パス固定に変換
- [x] [2026-06-03_063647_llama_cpp_oom_regression_fix.md](2026-06-03_063647_llama_cpp_oom_regression_fix.md) — llama.cpp HEAD更新後のCUDA OOM 回帰を -ub 8192→4096 変更で解消（VRAM空き 0.6→5.4GB）
- [x] [2026-06-10_213920_ttyd_startup_reliability.md](2026-06-10_213920_ttyd_startup_reliability.md) — ttyd 起動ロジックを単一冪等スクリプトに集約し、どの起動経路でも ttyd が確実に立ち上がる構造に改善
- [x] [2026-06-20_052841_start_sh_gpu_visibility_autodetect.md](2026-06-20_052841_start_sh_gpu_visibility_autodetect.md) — start.sh の `GGML_VK_VISIBLE_DEVICES=0,1,2,3` ハードコードを撤廃し、起動前に vulkaninfo で RADV 物理 GPU を自動検出（llvmpipe 除外、3枚→`0,1,2`/4枚→`0,1,2,3`）。mi25/p100 に期待枚数チェック（警告のみ・非中断）を追加、ROCm/CUDA は可視性不介入

## 11. mi25 への横展開（2台目 GPU サーバ）

- [x] [2026-06-13_112006_mi25_qwen36_128k.md](2026-06-13_112006_mi25_qwen36_128k.md) — mi25 (MI25×4/gfx900) で Qwen3.6-35B-A3B を 128k 実行。BIOS MMIO High 256→512GB で4枚64GB復旧、master が gfx900 でビルド不能(`__hip_fp8_e4m3`)のため commit `0fac87b15` に pin、ub=2048 が速度(prompt 122.8/eval 24.5 t/s)・VRAM 両面で最適と確定
- [x] [2026-06-14_001107_mi25_vulkan_qwen36_128k.md](2026-06-14_001107_mi25_vulkan_qwen36_128k.md) — mi25 を Vulkan(RADV) でビルドし ROCm 版と同条件で探索。Vulkan は master(v9620) を pin 不要でビルド成功、prompt が ROCm の約3.3倍(32k 405 t/s)・eval は約0.6倍、ub 非依存で VRAM 8.72GB 一定(ub=4096 でも OOM せず)。FA=0+q8_0 は不可。f16 KV 試行中にホストダウン→本番は q8_0 構成限定
