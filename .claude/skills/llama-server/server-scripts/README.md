# server-scripts/

**これらのスクリプトはGPUサーバ上で実行するためのものです。ローカルで実行しないでください。**

各スクリプトはGPUサーバの `~/llama.cpp/update_and_build.sh` として転送・配置して使用します。

## 転送方法

```bash
# 例: t120h-p100 に転送
scp .claude/skills/llama-server/server-scripts/update_and_build-t120h-p100.sh \
  t120h-p100:~/llama.cpp/update_and_build.sh
```

## ファイル一覧

| ファイル | 対象サーバ | プラットフォーム |
|---------|-----------|-----------------|
| `update_and_build-mi25.sh` | mi25 | ROCm (gfx900) |
| `update_and_build-t120h-p100.sh` | t120h-p100 | CUDA (sm_60) |
| `update_and_build-t120h-m10.sh` | t120h-m10 | CUDA (sm_52) |
