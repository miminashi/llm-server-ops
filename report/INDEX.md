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
- [x] [2026-06-24_161909_mi25_hang_repro_load_campaign.md](2026-06-24_161909_mi25_hang_repro_load_campaign.md) — opencode 起因の mi25 ハングを合成連続推論負荷で再現試行。ROCm(pin `0fac87b15`)30完走＋Vulkan 23完走の計53試行・約11.5時間で確定ホストハング0・カーネル危険signature 0。唯一の「ハング様」事象(run1 trial7)はBMCも不達＝拠点経路喪失で元ハング(BMC生存)とsignature相違。結論「負荷誘発の決定論的事象ではなく確率的PCIe物理層(SLOT4)障害」、ROCm固有でもない。eval ROCm 27.3/Vulkan 17.9・prompt ROCm 580/Vulkan 1115 t/s を再確認
- [x] [2026-06-25_063238_mi25_4card_recovery.md](2026-06-25_063238_mi25_4card_recovery.md) — シャットダウン後に2→3→4枚を段階装着し各構成を網羅調査。**4枚すべてGen3 x16・AER訂正エラー0・dmesg脱落痕跡なしで認識、64GB VRAM復旧**。前回脱落常連の GUID 33301 は同一SLOT4で、8820 は SLOT8→SLOT6 へ挿し替えて健全化（要因は再装着＋挿し替え両方で切り分け未完）。MMIOは全構成で非問題(BAR size=16G正常割当)。ただし3枚・4枚とも**認識まで数回の抜き差しを要した**＝接触マージン低く再発しうるため「暫定復旧・要監視」。dropout レポートの物理層障害結論を実証
- [x] [2026-06-25_094641_mi25_4card_load_gpuvm_fault.md](2026-06-25_094641_mi25_4card_load_gpuvm_fault.md) — 4枚復旧の負荷検証。**電源サイクル7/7合格**(コールド5+ウォーム2で4枚 x16・AER0 再列挙=再起動耐性獲得)も、**実負荷では GPU 8820(SLOT6/87:00.0/node-5)が再現性をもって GPUVM page fault**(`address 0x100000000`/UTCL2)で llama-server 即死。8820含む全構成でフォルト(4枚~700s 2/2・3枚~1613s)、**8820除外3枚{29525,33301,54068}は~2361s完走でクリア**=犯人は8820個体/SLOT6。物理層は全期間健全(別系統)。旧villain 33301は負荷安定を確認。当面は8820除外の3枚48GB運用(`HIP_VISIBLE_DEVICES=0,1,2`)、4枚64GBには8820の物理対応(SLOT8系へ戻す/交換)が必要
- [x] [2026-06-25_145006_mi25_4card_load_vulkan.md](2026-06-25_145006_mi25_4card_load_vulkan.md) — 上記負荷テストの Vulkan(RADV) 追試で3構成完全対称比較。**4枚負荷で 8820 が ~2208s でフォルト**(ROCmの~745sより3倍長い、signatureは`amdgpu_job_timedout`→`BACO reset`→`vk::DeviceLost`でROCmのUTCL2 page faultとは別機序、ただし発火カード/タイミングは同一=バックエンド非依存)。**しかし3枚 incl 8820は 2307s/3試行完走**(ROCmは~1613sでフォルト)=Vulkanは「4枚分散負荷時のみ」発火する枚数依存性。新オプション「Vulkan+3枚 incl 8820」で48GB運用+eval ≈ 35 t/s(ROCm 22.9を上回る)が見えた。4枚64GBは Vulkan でも不可で物理対応必須は変わらず
- [x] [2026-06-26_081718_mi25_4card_load_vulkan_pwr_sweep.md](2026-06-26_081718_mi25_4card_load_vulkan_pwr_sweep.md) — mi25 4枚 Vulkan で電力スイープ 190→140W 11 点。電力 cap に対し eval は ~16 t/s で水平、per-card 実消費 36-39W で cap 140-190W は compute を絞らない構造を確認。FAULT は 175W/155W/150W の 3 点で発火 (8820, t2f=183s/941s/1515s) も電力非単調=電力点固有か確率的かは弁別保留。物理層 (AER/Link/GPU_COUNT) は全期間健全
- [x] [2026-06-26_210732_mi25_4card_load_vulkan_pwr_sweep_v2.md](2026-06-26_210732_mi25_4card_load_vulkan_pwr_sweep_v2.md) — 上記電力スイープと **完全同一条件で追試**。**11/11 全 PASS / 44 trial 連続 fault 0** → 原 3 件の FAULT 点 (175/155/150W) は同点では再発火せず、「電力点固有説」を完全否定し「確率的揺らぎ説」を確定。Fisher 検定で原 3/44 vs 再 0/44 の有意差なし (両側 p≈0.241) → 同一確率分布。8820 発火率は 6.8% から合算 3/88 = 3.4% へ下方修正。物理計測量 (power/温度/eval/AER) は完全再現
- [x] [2026-06-27_071959_mi25_8820_vram_memtest.md](2026-06-27_071959_mi25_8820_vram_memtest.md) — 8820 確率発火 (3.4%) の真因仮説 (a) 個体 VRAM bad page を `memtest_vulkan v0.5.0` で直接検査。mi25 4 枚に対し計 9 Run / 88,006 iter / **累積 1.29 PB checked**、うち 8820 単独で **1.14 PB / ~72,650 周相当の全 VRAM read**。**全 Run error 0 件、dmesg 新規 amdgpu fault 0 件、PCIe AER (COR/FATAL/NFATAL) = 0**。bad page 仮説を強く否定 → 真因は (b) コアロジック VM/MMU 層 or (c) multi-GPU 同期経路 に絞り込み。本リポジトリ初導入の memtest_vulkan は pre-built バイナリで gfx900/RADV 完動、`./memtest_vulkan N` で非対話モード即時開始 (PCI Bus 降順メニュー)、運用ノウハウを確立
- [x] [2026-06-29_041700_mi25_8820_stand_alone_24h.md](2026-06-29_041700_mi25_8820_stand_alone_24h.md) — 8820 単独 (`GGML_VK_VISIBLE_DEVICES=3`) + Vulkan/RADV + Qwen3-8B Q6_K で 24h 負荷を 2 ラウンド (累計 31.8h)。**累計 147 trial / 2 fault (1.36%)、両 fault とも過去 4 枚 88 trial と完全同一シグネチャ** (`[gfxhub0] no-retry page fault src_id:0 ring:88 pasid:32772 @ BDF 87:00.0` + `amdgpu_job_timedout ring comp_1.1.0` + `BACO reset` + `vk::DeviceLostError`、vmid のみ動的差)。**(c) multi-GPU 経路起因否定、(b) 個体ロジック起因確定** → 物理交換相当の判定材料。発火率 1.36% vs 3.41% は Fisher p=0.27 で有意差なしだが若干低下、(c) が微小寄与の可能性は残る。Round 1 では `server_error_transient` 連続 165 件 (llama-server クラッシュ時の load_driver 挙動) で MAX_TRIALS=200 偽終了するバグ判明、Round 2 用に **trial 前 `/health` pre-check + auto-restart** を追加し、trial 24 fault 後の自動復旧 → 88 trial 連続 0 fault で 24h 完走を実証。PCIe 物理層は 10504 サンプル全期間健全
- [x] [2026-06-29_191721_mi25_gpu_card_id_unique_id.md](2026-06-29_191721_mi25_gpu_card_id_unique_id.md) — 上記 stand-alone 24h 完了後の物理スワップ追跡 (約 12 回シャットダウン+装着+確認/約 9.5h) で、**`rocm-smi -i` の GUID 値は KFD ランタイム割当値で個体不変ではない** ことが判明 (SLOT6/SLOT8 単独で 2 枚の別個体カードが両方 `BDF=84:00.0` / `GUID=54068` を返したが Unique ID は別: `0x21501edbcec48c4` / `0x2150040969a48e4`)。過去レポート群の「GUID 8820/54068/33301/29525」は当時のセッション値、**今後は `rocm-smi --showuniqueid` の Unique ID で識別**。SMBIOS Type 9 の Bus Address は MI25 内蔵 upstream bridge bus 番号で GPU 本体 BDF と異なる副次知見も併記 (例: SMBIOS CPU2 SLOT6=82:00.0 → upstream → 83:00.0 → GPU 84:00.0)、BDF も装着構成依存。stand-alone 24h の結論 (BDF 87:00.0 集中 = (b) 個体ロジック起因) は不変、ただし物理カード個体特定は 4 枚運用復帰時の Unique ID baseline 取得まで保留。CLAUDE.md に運用ルール (Unique ID 必須・末尾 4 桁略記・物理スワップ前後で照合) を明文化
- [x] [2026-06-29_213624_mi25_4card_uniqueid_baseline.md](2026-06-29_213624_mi25_4card_uniqueid_baseline.md) — 上記 Unique ID 続編の 4 枚 baseline 取得 (4 枚装着 + SLOT6 単独 4 回スワップで全 Unique ID 確定)。**過去 fault 集中個体 = `card-c48c4` (`0x21501edbcec48c4`) 確定** (4 枚運用時 BDF 87:00.0 = GUID 8820 = この Unique ID、本日 05:25 と 21:14 JST の 2 回観測で全 BDF の GUID 配置完全一致から KFD allocation の BDF 決定論性も確証)。全 4 個体 = `card-c3164` / `card-a48e4` / `card-448c4` / `card-c48c4`。カード略称は末尾 4 桁では衝突 (`48c4` が `card-c48c4`/`card-448c4` で 2 重) するため **末尾 5 桁基本** に運用変更し CLAUDE.md 反映。物理交換対象が一意に確定 → 4 枚 64GB 復帰には `card-c48c4` の**物理交換**が必要 (stand_alone 24h で (b) 個体ロジック起因確定済のため SLOT 移動では救えない)。当面の `HIP_VISIBLE_DEVICES=0,1,2` (= `card-c48c4` 除外 3 枚 48GB) 運用継続は不変。次セッション課題 = 4 枚装着実負荷で `card-c48c4` (BDF 87:00.0) の fault シグネチャ再現確認 (※ 本レポートの「SLOT8」記述は後続 c48c4 slot move 試験で SLOT6 = BDF 87:00.0 と訂正)
- [x] [2026-06-30_012759_mi25_c48c4_slot_move_load.md](2026-06-30_012759_mi25_c48c4_slot_move_load.md) — c48c4 を SLOT6 (= BDF 87:00.0) から **SLOT8 (= BDF 84:00.0)** へ物理移動して Vulkan/RADV 8h 単独可視化負荷 (GGML_VK_VISIBLE_DEVICES=2)。**37 trial / 0 fault** (期待 0.5 件、P(0)≒60% → (D) 判定保留、Fisher vs 4 枚 3/88 p=0.345 / vs SA 2/147 p=0.637、有意差なし) — (b) Unique ID 単位 fault 追従性は本試験では否定も確定もできず、24h+ 追試が必要。**副次の決定的発見: SMBIOS dmidecode + lspci tree 再照合で過去 baseline の SLOT 番号認識が逆と判明、正しくは `CPU2 SLOT6 = BDF 87:00.0` / `CPU2 SLOT8 = BDF 84:00.0`** → stand_alone_24h L50 の「SLOT6」元記述が正しく、uniqueid_baseline と CLAUDE.md L60-63 が誤り。試験中 PCIe AER=0 / GPU_COUNT=4 維持 / eval p50 23.9 t/s で stand_alone_24h と整合。AB swap は 4-5 サイクルかかり、448c4 + SLOT6 の特定組み合わせ micro-fit 不認識を発見 (H1/H2 棄却・H3 残存)。試験後物理配置: SLOT2=c3164 / SLOT4=448c4 / SLOT6=a48e4 / **SLOT8=c48c4**、運用継続なら HIP_VISIBLE_DEVICES を 0,1,2 → **0,1,3** に変更必要
- [x] [2026-07-04_012209_mi25_c48c4_slot8_24h_x2.md](2026-07-04_012209_mi25_c48c4_slot8_24h_x2.md) — c48c4 = SLOT8 (BDF 84:00.0 = GPU[2]) 構成で **24h × 2 ラウンド** (実測 48.2h) の Vulkan/RADV stand-alone 負荷 (GGML_VK_VISIBLE_DEVICES=2、Qwen3-8B Q6_K)。**累積 221 trial / 0 fault** (期待 3.01 件、**P(0)≒4.85%**)、**Fisher exact vs 過去 4 枚運用 3/88 = p=0.0225 で 5% 水準で有意に低い**、vs SA SLOT6 2/147 = p=0.1589 で非有意 (SA 水準 1.36% は棄却できず) → **(b) Unique ID 単位 fault 追従性は本 SLOT8 構成では否定される方向**、c48c4 個体の ASIC 欠陥は残っても SLOT8 では実運用に耐える確率で fault が抑制される新選択肢。物理層 (AER 全 0 / GPU_COUNT=4 / power p95 161W / Tj max 95°C) は SA と完全整合、48h 通じて BACO recovery 発生 0 件。**副次発見 (残課題#5 完全解明): power cap 永続化 = `/etc/rc.local` が boot 時に sysfs power1_cap を 160W 書き込み** (default = 220W = HW)、stand_alone_24h の「BACO 後 220W リセット」観測と整合 (BACO は sysfs を default にリセット、rc.local 再実行なし = `recover_from_hang` の `sudo rocm-smi --setpoweroverdrive` が runtime 再設定として機能)。**副次観測**: SLOT8 化以降 pp_tps mean が SA 508.9 の 40-45% (206-230 t/s) に低下継続、eval_tps は完全整合、原因未追究
- [x] [2026-07-05_181639_mi25_fault_tracking_fable_review.md](2026-07-05_181639_mi25_fault_tracking_fable_review.md) — **Claude Fable 5 による fault 追跡 (06-14〜07-04、14 レポート) の後方視的レビュー**。最重要発見: **単独 24h 試験はカードを fault 多発時と同じ SLOT6 に置いたまま実施されており、カード個体とスロットが交絡した状態で「(b) 個体ロジック起因確定・物理交換相当」を宣言していた** (仮説枠組みに (d) スロット/環境要因が欠落)。fault 実績は c48c4×SLOT6 = 5/235、c48c4×SLOT8 = 0/258、**他カード×SLOT6 = データなし** (2×2 の空セル)。07-04 の p=0.0225 はスロットと GPU 枚数を同時に跨ぐ交絡比較で、同条件比較 (0/221 vs 2/147) は p=0.159 非有意 + 0/221 の 95% CI 上限 ≈1.36% = SLOT6 単独実測率と一致 → **スロット効果は統計的に未実証**。他: pp_tps 半減等の未解明異常が結論と同居、fault シグネチャ台帳の 3 件目 (uptime 43173) の由来に未監査の曖昧さ、fault アドレス (0x100000000 = 4GiB 境界) 未解析、sclk スイープ等の落とし糸 5 件、テレメトリデーモンが試験終了後も稼働継続し commit 済み添付ログ 6 ファイルを書き換え中 (git M の原因)。**推奨最優先: 健全カード×SLOT6 単独 24h 負荷** (最安の決定実験、どのレポートでも未提案)。CLAUDE.md/メモリの「物理交換必須」断定は要更新
- [x] [2026-07-10_105706_mi25_a48e4_slot6_24h_x2.md](2026-07-10_105706_mi25_a48e4_slot6_24h_x2.md) — Fable レビュー D-1 決定実験。健全カード `a48e4` を SLOT6 (BDF 87:00.0 = GPU[3]、Vulkan idx 3) に単独可視化して SA と同一構成 (Qwen3-8B Q6_K / Vulkan / FA / q8_0 KV / MAX=200・TRIAL=720s・HANG_SAFETY=10) で **24h × 2 ラウンド (実測 48.12h、累積 221 trial / 0 fault)**。**Fisher exact vs c48c4×SLOT6 累積 5/235 = p=0.0356 で 5% 有意に低い**、vs 4-card 3/88 = p=0.0225 有意、vs SA 2/147 = p=0.159 非有意、vs SLOT8_x2 0/221 = p=1.0 完全対称。**P(0 fault \| p=2.13% [c48c4×SLOT6 累積], n=221) = 0.86%** で「a48e4 も 2.13% で fault」の帰無仮説はほぼ棄却 → **(d) SLOT6 単独環境起因説を統計的に棄却**、fault は c48c4 個体または c48c4×SLOT6 相互作用に絞られる。2×2 マトリクス完成: c48c4×SLOT6 = 5/235 (2.13%) ★fault 集中、c48c4×SLOT8 = 0/221、**a48e4×SLOT6 = 0/221**。**副次発見**: VBIOS 全 4 枚共通 `113-D0513700-001` = 版数差では個体差説明不能。pp_tps mean 180-183 t/s は SLOT8 c48c4 (206-230) より更に低い → 「pp_tps 半減 = PCIe root port 経路差」仮説を棄却、SA 期以降の共通要因 (llama.cpp/ROCm/RADV 回帰か)。**Fable レビュー B-1 恒久修正**: `run_campaign_a48e4.sh` に `trap 'stop_telemetry' EXIT INT TERM` と mi25 側 `pkill -f 'dmesg -w'` / `pkill -f 'tail -F'` を追加、R1/R2 完走後にテレメトリデーモン残存 0 件を確認、commit 済み添付ログ書き換え問題は再発せず。R2 完走後 07-09 07:15 / 13:43 に mi25 意図しない再起動 2 回 = Unattended Upgrades 起因と推定、amdgpu fault / GPU reset / kernel panic すべて 0 件で fault 由来ではないと確認、本試験結論に影響なし (**※ 07-09 リブートの Unattended Upgrades 起因推定は後続 [2026-07-12_045926_mi25_cmos_battery_reboot_loop](2026-07-12_045926_mi25_cmos_battery_reboot_loop.md) で VBAT 起因へ再解釈**)
- [x] [2026-07-12_045926_mi25_cmos_battery_reboot_loop.md](2026-07-12_045926_mi25_cmos_battery_reboot_loop.md) — mi25 の連続リブート (07-11 32回・07-12 39+回) の根本原因調査。BMC センサ **VBAT = 1.624V** (Lower Non-recoverable 閾値 2.326V 未満)、他センサ全正常 = **CMOS/RTC コイン電池 (CR2032) 切れ単独障害**。SEL 464 件中 VBAT イベント 289 件 (62%)、うち Non-recoverable 140 件。**電圧低下の時系列**: 2025-08-28 (2.43V, Lower Critical 初) → **2025-10-28 (2.33V, Non-recoverable 初)** → 2025-11 (2.27V) → 2026-01 (2.09V) → 2026-07 (1.55-1.62V) の 9 ヶ月以上の緩やかな単調減少。BMC 時刻オフセット +9h 先行 (RTC 破綻の副作用)。**07-09 07:15 / 13:43 / 07-10 09:01 の 3 回リブートを Unattended Upgrades 起因から VBAT 起因へ再解釈** (VBAT が Non-recoverable 域に落ちて 8 ヶ月後、以降 07-10 → 07-11 → 07-12 の単調増加系列の初期期)、[a48e4_slot6_24h_x2 副次観測 4](2026-07-10_105706_mi25_a48e4_slot6_24h_x2.md) の推定を訂正。BMC 経由 ACPI soft shutdown で 05:01:43 JST に電源停止、ロック `aws-mmns-generic-2796720-20260712_050051` 保持で物理修理待機。**GPU 4 枚 (c3164/448c4/a48e4/c48c4) 個体特性・fault シグネチャ解析には無関係な独立事象** (現 boot 0 の amdgpu 初期化は完全正常、amdgpu fault / GPU reset / kernel panic 0 件)。物理修理はユーザ介入必須 (CR2032 交換 + BIOS 再設定 = MMIO High 512GB 等 + BMC NTP 再有効化)
- [x] [2026-07-17_135433_mi25_bios_restore_after_cmos.md](2026-07-17_135433_mi25_bios_restore_after_cmos.md) — CMOS/RTC バッテリー物理交換後の BIOS 再設定を BMC KVM 経由で実施。**実質変更 3 点**: MMIOHBase 56TB → **3TB**、MMIO High Size 256GB → **512GB**、Boot Order #1 Legacy [Hard Disk] → **[UEFI Hard Disk:ubuntu]** (default の Legacy Hard Disk は UEFI/GPT な NVMe を検出できず PXE fail に落ちた副次発見あり、初回 Save & Exit 後の再起動失敗で判明)。Above 4G Decoding / IIO SLOT Gen3 / Non-Posted Prefetch Disable / Boot Mode DUAL / Secure Boot Disabled / CSM Enabled は default で既に期待値と一致し変更不要。Ubuntu 22.04.5 LTS 起動 + SSH 到達確認。**GPU 4 枚は電池交換時に取り外し中、未装着** (ユーザ手元)、4 枚認識確認は次セッションで実施予定。**副次発見**: (a) BMC 時刻が **2015-01-02 で完全リセット** (前セッション観測の +9h ずれとは異なる、CR2032 電池と BMC RTC は独立ではなく依存関係あり)、`ipmitool sel time set "07/17/2026 ..."` は "Specified time could not be parsed" エラーで失敗 (BMC FW 3.94 の年範囲/date 形式制約か、参考として BIOS Aptio 3.2 が Build 2019-11-22 の同世代)、BMC Web UI 経由の恒久同期を推奨、(b) **Ubuntu 側 RTC も CR2032 電池切れの影響で起動直後に約 10 時間ずれ** (`ssh mi25 date` = `Fri Jul 17 03:22 JST 2026` 実時刻 13:22、cloud-init も同時刻で起動、`systemd-timesyncd` の NTP 同期で数分後に補正) → **電池は BMC RTC だけでなく OS 側 `/dev/rtc0` にも影響**、電池交換後の初回起動では時刻依存ジョブは `System clock synchronized: yes` 確認後に開始すべき、(c) **GPU 未装着状態で CPU1 SLOT4 の Root Port `00:03.0` だけ lspci に列挙** (他 SLOT2/6/8/11 は BIOS で disable) → SLOT4 は過去に PCIe 物理層障害の実績あり、**presence 信号 (PRSNT#1/#2 pin) 残留の可能性** を示唆、次セッションで GPU 装着時に SLOT4 の接点清掃と装着後 `02:00.0` 正常認識を要確認、(d) VBAT = **2.794V** (`ok` 域だが新品 CR2032 3.0V より 6.87% 低い、BMC ADC 精度誤差か電池個体品質、監視継続推奨)、(e) `ipmitool chassis bootdev bios` で確実に BIOS 進入可 (Delete 連打より安定)、(f) mi25 BIOS の実質デフォルトは過去実績と大半一致し、復旧要は 3 点集中で速度化可能、(g) `bmc-kvm.py sendkeys` は "Right" ではなく **`ArrowRight`** を使う (Playwright fallback で Unknown key エラー)、(h) Chassis Intru センサ = `0x0` のまま (電池交換でケース開けたが trigger されず、シャーシ侵入検知は監査用途に信頼不可)
- [x] [2026-07-19_053651_mi25_c48c4_slot8_4card_24h_r1.md](2026-07-19_053651_mi25_c48c4_slot8_4card_24h_r1.md) — Fable レビュー D-2 決定実験 R1。c48c4 = SLOT8 (BDF 84:00.0 = GPU[2]) を含む **4 枚同時装着** で `HIP_VISIBLE_DEVICES=0,1,2,3` の multi-GPU 負荷を 24h+ 走行 (Session1 = 02:07-18:52 + 電源断中断 + Session2 = 23:58-05:36、実走 22.3h)。**累計 99 trial_done / 0 fault** (Session1: 74 + Session2: 25)、**Fisher exact one-sided vs c48c4×SLOT6 4-card 3/88 = p=0.1023 (10% 有意、5% には届かず)** で 検出力 96.78% (SLOT6 4-card 3.41% を実質棄却)、vs c48c4×SLOT6 累積 5/235 = p=0.1702 (検出力 88.13%)、vs c48c4×SLOT6 SA 2/147 = p=0.3561 (棄却不能、R2 で N≥200 到達待ち)、vs c48c4×SLOT8 SA 0/221 = p=1.0 完全整合、vs a48e4×SLOT6 SA 0/221 = p=1.0。dmesg amdgpu fault / GPU reset / PCIe AER (COR/FATAL/NFATAL) / GPU_COUNT 低下 は 22.3h 通じて **全 0 件**、telemetry 6846 サンプル全体で GPU_COUNT min=4 維持。**運用方針の更新**: `HIP_VISIBLE_DEVICES=0,1,2,3` (4 枚 64GB) を常用可とする暫定判定、従来の `0,1,3` (c48c4 除外 3 枚 48GB) は fallback に降格。**副次発見**: (a) 制御ホスト側でブレーカー電源断発生 (2026-07-18 18:52-23:58 JST の 5h)、mi25 側は完全健全で llama-server は孤児 request (task 758927) を推論継続、5h 単独負荷で GPU fault 0 = D-2 結論を強化する safety margin、(b) per-GPU power 4 枚とも同水準 (mean 16.6-19.8W / p95 44-51W / max 172W)、**c48c4 (SLOT8) の p95 45W = 他 3 枚 44-51W と完全同水準**で SLOT6 系の pwr_sweep で観測した「c48c4 だけ p95 105W 跳ね」パターンは SLOT8 では再現せず、(c) c48c4 Tj max = 60°C (SLOT6 系 95°C と大差)、SLOT8 の冷却/電源経路が c48c4 熱ストレスを抑制している可能性、(d) eval_tps mean 12.85 t/s / p50 12.90 t/s は SLOT8 SA 16.9 t/s の -24%、multi-GPU 4 枚 split-mode layer の cross-GPU 同期コストの妥当範囲 (pp_tps mean=586.08 t/s)、(e) 制御ホスト電源断は run_campaign の resilience 設計外 (BMC 経由 GPU 側 recovery は自動化、制御ホスト側 crash は対応不可) → systemd Restart=on-failure 等の改善余地、(f) `trials_vulkan.jsonl` は session ごとに trial 番号を 1 から再開するため epoch フィールドで session1/2 分離集計、trial 75 (電源断で trial_done event 出ず) は統計から除外、(g) VBAT = 2.794V 継続 (22.3h 走行中変動なし、CR2032 の負荷ストレス下でも劣化痕跡なし)、(h) dmesg diff +8 行の内訳は ubuntu_pro esm-cache が rocm ライブラリ scan で apparmor DENIED (4 行) + kernel perf subsystem の負荷保護 (4 行) のみで GPU 系は完全静寂
