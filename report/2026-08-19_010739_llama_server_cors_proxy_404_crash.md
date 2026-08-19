# llama-server が MCP プロキシの 404 中継でプロセスごと落ちる問題

- **実施日時**: 2026年8月18日 21:16 〜 2026年8月19日 01:07 JST (`--ui-mcp-proxy` 付き再起動 → クラッシュ再現 → 全スレッド backtrace 取得 → 原因特定 → パッチ作成・ビルド・検証)
- **報告日時**: 2026年8月19日 01:07 JST
- **作成者**: Claude Opus 5

## 概要

aws-gpu01 の llama-server を `--ui-mcp-proxy` オプション付きで起動してほしい、という依頼から始まった作業である。このオプションは llama.cpp の WebUI が MCP サーバに接続するための CORS プロキシを有効にするもので、llama.cpp 側では experimental 扱いになっている。

起動自体は完了したものの、その後およそ 2 時間ほど動かしたところでサーバがプロセスごと異常終了した。ログには C++ の例外がキャッチされずに終了したことを示すメッセージだけが残っており、原因の手掛かりに乏しかった。そこでユーザの了承を得たうえで、同じオプションを付けたまま再起動して意図的にクラッシュを再現させ、その結果をもとに原因を追う方針とした。

最初の異常終了ではバックトレースから有用な情報が得られなかったが、これは llama.cpp に内蔵されている異常終了時のバックトレース出力が、例外を投げたスレッドではなくメインスレッドの状態しか記録しない作りになっていたためである。そこで再現テストの前に、外部からデバッガを常駐させて異常終了の瞬間に全スレッドの状態を記録する仕掛けを用意した。この仕掛けにはカーネルのセキュリティ設定を一時的に緩める必要があったため、ユーザの承認を得たうえで実施した。

再現したクラッシュのバックトレースから、問題の発生箇所が HTTP レスポンスをチャンク単位で書き出す処理の中であることが判明した。さらにソースを追った結果、原因は MCP という機能そのものではなく、llama.cpp のエラー応答処理と、同梱されている HTTP ライブラリの書き出し経路の組み合わせにあることが分かった。プロキシが中継した応答が「見つかりません」を示すステータスだった場合に、llama.cpp が本来ストリーミング用に用意した応答へ余計な本文を混ぜてしまい、その結果 HTTP ライブラリが別の書き出し経路を選び、その経路では用意されていない終端処理を呼び出してしまう、という連鎖である。

この推論を確かめるため、MCP サーバを一切使わずに再現できる最小のテストを組み立てた。当初の想定どおりには落ちず、条件をもう一段絞り込む必要があったが、最終的に上流サーバの応答本文の長さが鍵であることを突き止め、狙いどおりプロセスを落とすことに成功した。これで原因の連鎖が実証された。

修正としては、エラー応答の処理がストリーミング中の応答に手を出さないようにする方針を採り、9 行のパッチを当てて再ビルドした。修正版では、以前は確実に落ちていたケースが正常な応答を返してプロセスも生き残ることを確認している。あわせて、通常のエラー応答やプロキシの正常系、推論そのものに影響が出ていないことも確認した。

なお本作業の途中で、依頼とは直接関係のない問題もいくつか見つかっている。起動スクリプトに引数の受け渡しの誤りがあってデフォルト構成では必ず起動に失敗する状態だったこと、そして推論の実行中にワークステーションからサーバへの通信が数十秒間ほとんど通らなくなる現象である。前者はその場で修正した。後者はサーバ側は正常に動作し続けており、今回は追跡していない。

現時点でサーバは修正版バイナリで稼働している。パッチは対象サーバ上のローカル変更として残っているだけなので、本家への報告と、次回のソース更新時に失われないための扱いが残課題である。

## 添付ファイル

- [全スレッドの backtrace (gdb)](attachment/2026-08-19_010739_llama_server_cors_proxy_404_crash/gdb-backtrace-all-threads.log)
- [1 回目のクラッシュ時サーバログ](attachment/2026-08-19_010739_llama_server_cors_proxy_404_crash/llama-server-crash-1st.log)
- [2 回目のクラッシュ時サーバログ](attachment/2026-08-19_010739_llama_server_cors_proxy_404_crash/llama-server-crash-2nd.log)
- [適用したパッチ](attachment/2026-08-19_010739_llama_server_cors_proxy_404_crash/server-http.cpp.patch)
- [ネットワーク停滞中の KVM コンソール](attachment/2026-08-19_010739_llama_server_cors_proxy_404_crash/kvm-console-during-network-stall.png)

## 核心発見サマリ

**結論**: `--ui-mcp-proxy` の `/cors-proxy` が **status 404 を中継**し、かつ **上流の応答本文が llama.cpp の 404 JSON (74 bytes) より短い**とき、llama-server は `std::bad_function_call` で **プロセスごと abort** する。MCP のプロトコル処理に固有の問題ではなく、「ストリーミング応答が 404 ステータスを持つ」場合に一般に成立する欠陥である（現状の llama-server で該当するのは `/cors-proxy` 経由の中継のみ）。error_handler がストリーミング応答に body を注入しないようにする 9 行のパッチで解消し、回帰は無し。

**ただし実環境の 2 回のクラッシュについては、上流の MCP サーバが返したステータスを直接確認していない**（クラッシュ時のログにプロキシ応答のステータスが記録されないため）。修正版での検証時に `Accept` ヘッダ無しで同エンドポイントを GET したときの応答は 406 であり、406 では error_handler が body を注入しないので本連鎖では落ちない。WebUI は `Accept: text/event-stream` を付けるため上流の応答が異なると考えられるが、未確認である。実証済みなのは「404 かつ短い本文で確実に落ちる」ことと「クラッシュ地点が `sink.done()` である」ことの 2 点で、実環境の 2 回が同じ 404 経路だったかは推定に留まる。

連鎖は以下の 8 段階（行番号は llama.cpp `10bf611e5`）:

| # | 場所 | 起きること |
|---|---|---|
| 1 | `tools/server/server-models.cpp:2332` | `server_http_proxy` が上流の 404 を `status` に設定し `next` も設定 → `is_stream() == true` |
| 2 | `tools/server/server-http.cpp:547` | `process_handler_response` が `res.status = 404` + `set_chunked_content_provider()` → `content_length_ = 0` |
| 3 | `vendor/cpp-httplib/httplib.cpp:8037` | `400 <= res.status` なので error_handler を呼ぶ |
| 4 | `tools/server/server-http.cpp:145` | error_handler は **404 のときだけ** `set_content()` で body 注入。`set_content()` は `content_provider_` をクリアしない |
| 5 | `vendor/cpp-httplib/httplib.cpp:8825` | `apply_ranges()` が body 非空を見て `content_length_ = body.size()` (> 0) |
| 6 | `vendor/cpp-httplib/httplib.cpp:8113` | `content_length_ > 0` の分岐に入り `write_content()` → `write_content_with_progress()` |
| 7 | `vendor/cpp-httplib/httplib.cpp:3763` | この関数の `DataSink` は `write` と `is_writable` のみ設定し、**`done` を設定しない** |
| 8 | `tools/server/server-http.cpp:568` | provider が EOF で `sink.done()` を呼ぶ → 空 `std::function` → `std::bad_function_call` → `ggml_uncaught_exception` → `abort` |

`write_content_chunked()` (httplib.cpp:3871) と `write_content_without_length()` (同 3836) の `DataSink` には `done` が設定されているため、6 の分岐に入らない限り落ちない。

**本文長が条件に効く理由**: `write_content_with_progress()` のループは `while (offset < end_offset)` であり、`end_offset` は注入された body の長さ。上流の応答本文がそれ以上あれば 1 回目の `sink.write()` で `offset == end_offset` に達してループが終了し、`sink.done()` に到達しない。短い（空を含む）場合のみ provider が EOF を返して `sink.done()` に到達する。

決定的な backtrace（フレーム #10〜#13、抜粋）:

```
#10 std::__throw_bad_function_call() from libstdc++.so.6
#11 std::_Function_handler<bool (unsigned long, httplib::DataSink&),
      process_handler_response(...)::{lambda(unsigned long, httplib::DataSink&)#1}>::_M_invoke(...)
#12 std::_Function_handler<..., httplib::detail::ContentProviderAdapter>::_M_invoke(...)
#13 httplib::detail::write_content_with_progress<...Server::write_content_with_provider(...)>(...)
```

## 前提・目的

- **背景**: ユーザから aws-gpu01 の llama-server を `--ui-mcp-proxy` 付きで再起動する依頼を受けた。`--ui-mcp-proxy` は WebUI が MCP サーバへ接続するための CORS プロキシ (`/cors-proxy`) を有効にするフラグで、llama.cpp 側で experimental と明示されている
- **経過**: 起動から約 125 分後に `std::bad_function_call` でプロセスが異常終了。ユーザの指示により、同オプション付きで再起動してクラッシュを再現させ、結果に基づいてデバッグする方針となった
- **目的**: クラッシュの根本原因を特定し、修正して検証する

## 環境情報

- サーバ: aws-gpu01 (10.8.2.1) + aws-gpu02 (10.8.2.2) の RPC 分散構成
- llama.cpp: `10bf611e5` (2026-08-16)、ビルド識別子 `b10451`
- モデル: Huihui-DeepSeek-V4-Flash-0731-abliterated (Q4_K, 153.3 GiB) / ctx=131072
- 起動オプション: 既定構成に `--ui-mcp-proxy` を追加
- 上流 MCP サーバ: `http://10.77.0.19:80/mcp`
- OS: Ubuntu 24.04.3 LTS、gdb 15.0.50

## 再現方法

MCP サーバは不要。**空ボディの 404 を返す上流**を用意し、それを `/cors-proxy` 経由で GET するだけで確実に落ちる。

```bash
# 1) 空ボディ 404 を返すテスト用上流を立てる（対象サーバ上）
ssh aws-gpu01 'cat > /tmp/empty404.py <<PYEOF
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()
    def log_message(self, *a):
        pass
HTTPServer(("127.0.0.1", 8899), H).serve_forever()
PYEOF
setsid nohup python3 /tmp/empty404.py > /tmp/empty404.log 2>&1 < /dev/null &'

# 2) cors-proxy 経由で GET → 未修正版はここで abort する
curl -s -m 20 -o /dev/null -w 'HTTP %{http_code}\n' \
  "http://10.8.2.1:8000/cors-proxy?url=http://127.0.0.1:8899/foo"

# 3) プロセスが消えていることを確認
ssh aws-gpu01 "pgrep -f '[b]in/llama-server --model' || echo DEAD"
```

**落ちない例**（比較用）: 上流を llama-server 自身の 404 (`http://127.0.0.1:8000/definitely-not-found`) にすると、上流の本文が注入される body と同一内容・同一長になるため `sink.done()` に到達せず生存する。この差が本文長条件の裏付けになっている。

### 全スレッド backtrace の取得方法

llama.cpp 内蔵のバックトレース (`ggml/src/ggml.c:157` の `ggml_print_backtrace`) は `std::set_terminate` から fork した gdb で `bt` を実行するが、これは**カレントスレッド 1 本しか出力しない**。そのため 1 回目のクラッシュではメインスレッド (`server_queue::start_loop` の futex 待ち) しか記録されず、例外を投げた HTTP ワーカースレッドが見えなかった。

外部から gdb を常駐させて `SIGABRT` で全スレッドを取る:

```bash
# ptrace_scope=1 では非子孫プロセスへの attach が拒否されるため一時的に緩める（要 sudo）
ssh aws-gpu01 "sudo sysctl -w kernel.yama.ptrace_scope=0"

PID=$(ssh aws-gpu01 "pgrep -f '[b]in/llama-server --model' | head -1")
ssh aws-gpu01 "setsid nohup gdb -p $PID --batch -q \
  -ex 'set pagination off' -ex 'set confirm off' \
  -ex 'handle SIGABRT stop print pass' \
  -ex 'continue' \
  -ex 'thread apply all bt' \
  -ex 'detach' -ex 'quit' > /tmp/gdb-crash.log 2>&1 < /dev/null &"
```

内蔵バックトレースは `/proc/self/status` の `TracerPid` を見て、デバッガが付いている場合は自前の出力を抑止するため、二重取得にはならない。gdb は `SIGABRT` を pass するのでプロセスはそのまま異常終了し、従来どおりログも残る。

## 結果詳細

### クラッシュの再現性

| 回 | 稼働時間 | 直前の最後のログ行 | 結果 |
|---|---|---|---|
| 1 回目 | 約 125 分 | `proxying GET request to http://10.77.0.19:80/mcp` | `bad_function_call` で abort |
| 2 回目 | 約 23 分 | `proxying GET request to http://10.77.0.19:80/mcp` | 同上（gdb で全スレッド取得成功） |
| 最小再現 | 約 7 分 | `proxying GET request to http://127.0.0.1:8899/foo` | 同上（MCP 不要で再現） |

2 回とも直前の最後のログ行が MCP エンドポイントへの **GET** 中継で一致した。POST の中継は 2 回のセッションを通じて多数成功しており、GET だけが落ちている。

POST が落ちない理由は、上流が 200 を返すため error_handler が発火せず `write_content_chunked()` 経路（`done` が設定される）を通ることで説明できる。一方 **GET のときに上流が何を返していたかは記録が無く、未確認である**。前掲のとおり `Accept` ヘッダ無しでの GET は 406 を返し、406 では本連鎖は成立しない。したがって「実環境の GET も 404 経路だった」は推定であり、実証されているのは最小再現の 404 ケースのみである。

### 修正内容

`tools/server/server-http.cpp` の error_handler に 9 行を追加し、ストリーミング応答には body を注入しないようにした。

```cpp
 srv->set_error_handler([](const httplib::Request &, httplib::Response & res) {
+    // Never inject a body into a streaming response (e.g. the MCP CORS proxy relaying
+    // an upstream 404). set_content() leaves content_provider_ in place, apply_ranges()
+    // then sets content_length_ > 0, and httplib switches to the Content-Length write
+    // path, whose DataSink leaves done() unset. The provider installed by
+    // process_handler_response() calls sink.done() at EOF, which would throw
+    // std::bad_function_call and abort the whole server.
+    if (res.content_provider_) {
+        return;
+    }
     if (res.status == 404) {
```

`httplib::Response` は `struct` で、`content_provider_` は `// private members...` というコメントの下にあるものの実際には public のため、外部のラムダから参照できる。

検討した他の案:

| 案 | 内容 | 不採用の理由 |
|---|---|---|
| A | provider 側を `if (sink.done) { sink.done(); }` にする | クラッシュは止まるが、chunked 終端が書かれない不整合が残る（対症療法） |
| C | cpp-httplib 側で `write_content_with_progress()` の `DataSink` にも `done` を設定 | 本来はこちらも直すべきだが、vendored ライブラリの変更になり影響範囲が広い |

### 検証結果

「修正前」列は、未修正バイナリで実際に測ったものと、測っていないものを区別して記す。

| # | テスト | 修正前 | 修正後 |
|---|---|---|---|
| 1 | 空ボディ 404 を `/cors-proxy` GET で中継 | **abort（実測）** | HTTP 404 を正常中継、プロセス生存 |
| 2 | 同上を 5 連続 | 未測定（1 回で落ちるため） | 5 回とも HTTP 404、生存 |
| 3 | 通常の 404（プロキシ非経由） | 未測定（error_handler は素通り前でも同じ JSON を返すコード） | `File Not Found` JSON |
| 4 | `/cors-proxy` で 200 を中継 | 実環境で POST の中継が多数成功（ログ） | 正常 |
| 5 | 実 MCP エンドポイントへ GET | 未測定（クラッシュ元と推定されるが未確認） | HTTP 406 を中継、生存 |
| 6 | 実 MCP エンドポイントへ GET (`Accept: text/event-stream` 転送) | 未測定 | curl は 20s でタイムアウト（SSE 接続が継続）。プロセスは生存 |
| 7 | 推論 (`/v1/chat/completions`) | 正常 | 正常（サーバログで 32 tokens 生成・12.34 t/s を確認。後述のネットワーク停滞のため curl 側は応答を受け取れず） |

## 副次発見

### `rpc-stack-up.sh` の引数受け渡しの誤り（修正済み）

`.claude/skills/llama-server/scripts/rpc-stack-up.sh` の Step 4 で `rpc-llama-up.sh` に渡す `$MODEL` がクォートされておらず、**モデルパス未指定（= aws-gpu01/02 のデフォルト構成での起動）では必ず失敗する**状態だった。空展開で引数が 1 つずれ、ctx の `131072` がモデルパスとして渡り `failed to load model from 131072` になる。

`${MODEL:+"$MODEL"}` のように引数ごと省く形も同じ結果になる（`"$CTX"` が第 1 引数に繰り上がるため）。`rpc-llama-up.sh` は `MODEL="${1:-$DEFAULT_MODEL}"` なので、**空文字をそのまま第 1 引数として渡す**のが正しい。`"$MODEL"` とクォートするだけで解決する。未コミットの新規スクリプトであり、`llama-up.sh aws-gpu01` 経由の起動は今回が初回だったと思われる。

### 内蔵バックトレースがメインスレッドしか出さない

前述のとおり `ggml_print_backtrace()` は gdb に `bt` を渡すため、マルチスレッドのサーバでは例外を投げたスレッドが記録されない。`thread apply all bt` にすれば大幅に有用性が上がる。upstream への改善提案の候補。

### 推論中にワークステーションからの通信が停滞する（未調査）

検証中、推論リクエストの実行中に限って WS から aws-gpu01 への通信が数十秒ほとんど通らなくなる現象が 2 回発生した（ping 75% ロス・RTT 2048ms、SSH は `No route to host`）。いずれも自然回復している。

このときサーバ側は正常だった。BMC の KVM コンソールは通常のログインプロンプトを表示しており（[スクリーンショット](attachment/2026-08-19_010739_llama_server_cors_proxy_404_crash/kvm-console-during-network-stall.png)）、カーネルパニックも OOM も無い。復帰後に確認した `load average` は 0.27〜0.40、確立済み TCP は 4 本のみで、**推論自体はサーバログ上で正常完了していた**（応答が WS へ届かなかっただけ）。RPC 分散で aws-gpu01 ↔ aws-gpu02 が同一 NIC を使うことによる輻輳が疑われるが、今回は追跡していない。

なお、gdb で全スレッドを停止して backtrace を取得している間にも同様の停滞が起きたが、こちらは gdb がプロセスを停止させていた影響であり、別の事象である。

## 残課題

- **パッチが aws-gpu01 のローカル変更のままである**。`~/llama.cpp` で `git pull` すると失われる。upstream に取り込まれるまでは、パッチをリポジトリ側で保全するか、ビルド手順に組み込む必要がある
- **upstream (ggml-org/llama.cpp) への報告**が未実施。最小再現手順とパッチは本レポートに揃っている
- cpp-httplib 側の `write_content_with_progress()` に `done` を設定する修正（案 C）は未着手。他の利用者にも影響する本質的な欠陥である
- 推論中のネットワーク停滞は未調査
- `kernel.yama.ptrace_scope` は検証終了後に 1 へ戻してある（作業中のみ 0 に緩めた）
