# 調査レポート 目次

`report/` に約130本のレポートが時系列で蓄積。中心テーマは **Qwen3-122B を P100 サーバで 128K コンテキスト稼働させる性能チューニング**。後半は軽量モデル移行・運用整備へ。

詳細な全レポート一覧は [report/INDEX.md](report/INDEX.md) を参照。

## ジャンル一覧

1. **基盤構築** — Qwen3-122B を 128K で起動する VRAM 配置チューニング（C-1/C-2/C-3 構成）
2. **ボトルネック解析と環境特性** — CPU(MoE)律速の特定、NUMA 最適化、長時間稼働・idle 劣化の検証
3. **コンテキスト長 × FlashAttention × KV量子化** — fa=1 必須性、compute buffer のスケーリング解明
4. **batch / ubatch 境界の微細探索（Phase P–Sb）** — `-ub` が真のドライバ、OOM 境界 ub*≈1585 を 1 トークン精度で確定
5. **eval 安定性・再現性（Seval シリーズ 約60本）** — ub=1584/1586/1664 の 59 セッション統計追跡
6. **最終構成確定（Phase T / U シリーズ）** — KV量子化・split-mode・threads・OT・tensor-split・spec デコード等を評価し ctx=128k 本番既定化
7. **運用整備・モデル移行** — Marathon ベンチ、Qwen3.6-35B デフォルト化、サンプラ修正、OOM 回帰修正、スクリプト/ttyd 整備
