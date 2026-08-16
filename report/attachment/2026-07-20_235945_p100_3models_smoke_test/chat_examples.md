# 3 モデル chat 応答例

すべて `POST /v1/chat/completions` (OpenAI 互換)、`stream=false`。`reasoning_content` は llama-server の拡張フィールド (thinking モード時に visible content と分離される)。

## gemma-4 short chat (ctx=32k, `2 + 3 = ?`, max_tokens=800)

```
content:          '5'
finish_reason:    stop
usage.completion: 83 tokens
reasoning excerpt:
  *   Input: "2 + 3 = ?"
      *   Constraint: "答えのみ数字1桁で。" (Answer only with a single-digit number.)
      *   2 + 3 = 5
      *   Is it a single digit? Ye...
```

## gemma-4 first attempt (ctx=32k, `こんにちは、世界`, max_tokens=100 → 消費し尽くし)

```
content:          ''
finish_reason:    length
usage.completion: 100 tokens  # thinking で 100 tokens 全消費、visible が空
```

## gemma-4 retry (max_tokens=500, 同一 prompt)

```
content:          'こんにちは、世界'
finish_reason:    stop
usage.completion: 108 tokens
reasoning excerpt:
  *   Language: Japanese.
      *   Target phrase: 「こんにちは、世界」 (Hello, World).
      *   Constraint: "一言だけ返してください" ...
```

## gemma-4 long prompt (ctx=131k, 42039 prompt tokens, max_tokens=500)

```
prompt_tokens:    42039
completion_tokens: 500
finish_reason:    length      # thinking で 500 tokens 使い切り、visible なし
content:          ''
```

長 prompt そのものは OOM せず処理完走したが、単発 chat 用途では max_tokens=500 でも不足。運用時は 1500+ 推奨。

## North-Mini-Code chat (ctx=32k, Python one-liner)

```
prompt:  Write a Python one-liner that returns the sum of 1 to 10. Only the code, no explanation.
content:          'sum(range(1, 11))'
finish_reason:    stop
usage.completion: 117 tokens
reasoning excerpt:
  The user asks: "Write a Python one-liner that returns the sum of 1 to 10.
  Only the code, no explanation."
  We need to output a Python one-liner that returns the sum of 1 to 10.
  So something like: sum(...
```

## North-Mini-Code long prompt (ctx=131k, 42133 tokens, max_tokens=800)

```
prompt: (42k tokens of 'The quick brown fox...' repeated) + "What is the color of the fox mentioned above?"
prompt_tokens:    42133
completion_tokens: 77
finish_reason:    stop
content:          '**brown**'
```

正答。SWA が主体の cohere2moe で 131k KV でも VRAM は各 GPU 11 GiB 前後に収まった。

## ornith chat (ctx=32k, `2 + 3 = ?`, max_tokens=800)

```
content:          '5'
finish_reason:    stop
usage.completion: 344 tokens   # thinking がかなり長い (Qwen3-Next 特性)
reasoning excerpt:
  Here's a thinking process:

  1.  **Analyze User Input:**
     - Question: "2 + 3 = ?"
     - Constraint: "答えのみ数字1桁で。" (Answer only, single digit number.)
     - Language: Japanese

  2.  **Calculate:**
     - 2 ...
```

## ornith long prompt (ctx=131k, 42027 tokens, max_tokens=800)

```
prompt_tokens:    42027
completion_tokens: 73
finish_reason:    stop
content:          'Brown'
```

正答。SSM+attn hybrid で 131k KV も安定。

## Qwen3.6-27B HF-ID smoke test (`1+1=?`, max_tokens=800)

```
content:          '2'
finish_reason:    stop
usage.completion: 230 tokens
```

`start.sh` のパッチが HF-ID 経路を退行させていないことを確認。
