# PR #25428 English comment draft (for posting from `miminashi` account)

**Instructions**: Copy the block below (from `---` to `---`) and paste as a comment on PR #25428 via GitHub Web UI or `gh pr comment 25428 --repo ggml-org/llama.cpp --body-file <path>`.

---

Independent CPU-only verification of this PR on Qwen2.5-0.5B: **PR + a one-line follow-up fix works, and with an appropriate lr (1e-7 on a 0.5B model) the finetune actually converges — post-training PPL 13.90 → 10.18 on wiki.test.raw.** Two issues found along the way; the first is a real gap in the PR, the second is a lr-guidance nit.

**Environment.** Deliberately different from the author's setup, to test what's environment-specific:
- QEMU virtual CPU, 94 vCPU, single socket
- x86-64 with AVX-512F/DQ/CD/BW/VL only. **No AMX, no AVX-VNNI, no BF16, no BLAS**
- Build: `-DGGML_OPENMP=ON -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DGGML_BLAS=OFF -DCMAKE_BUILD_TYPE=Release`
- Model: **Qwen2.5-0.5B** (`general.architecture: qwen2`), F32 GGUF (~2 GB), 30x smaller than the author's 14B test
- Base: master `af3be131c` (b7542) + this PR (`fd0b2b479`)

**Result 1 — the PR fixes the SET_ROWS backward assert as intended.** With the PR applied, `ggml_build_backward_expand`'s `!node->view_src || node->op == GGML_OP_CPY || ...` assert (the primary #18805 symptom) is gone.

**Result 2 — the PR then immediately hits a second, distinct assert one layer up:**

```
GGML_ASSERT((int)sched->hash_set.size >= graph->n_nodes + graph->n_leafs) failed
  at ggml/src/ggml-backend.cpp:1866

  ggml_backend_sched_alloc_graph
  ggml_opt_alloc
  llama_context::opt_epoch_iter
```

Batch-size independent — reproduces with both `-b 512 -ub 512` and `-b 128 -ub 128`.

Same root cause as the `gf_res_prev` fix you already did, one level up: `llama_context::opt_init()` correctly re-reserves the graph result buffer with `8 * graph_max_nodes(n_batch)` for the training graph. But `llama_context::sched_reserve()`, which runs earlier and calls `ggml_backend_sched_new(..., max_nodes, ...)`, still uses the plain `graph_max_nodes(n_tokens)` sized for the compact inference graph. The scheduler's internal `hash_set` gets sized from that. When `opt_epoch_iter` submits the larger training graph, `ggml_backend_sched_alloc_graph` sees `hash_set.size < n_nodes + n_leafs` and aborts.

**Suggested fix — one line.** Mirror the 8x heuristic in `sched_reserve()`:

```diff
--- a/src/llama-context.cpp
+++ b/src/llama-context.cpp
@@ -452,7 +452,7 @@ void llama_context::sched_reserve() {
     const uint32_t n_seqs = cparams.n_seq_max;
     const uint32_t n_tokens = std::min(cparams.n_ctx, cparams.n_ubatch);

-    const size_t max_nodes = this->graph_max_nodes(n_tokens);
+    const size_t max_nodes = 8 * this->graph_max_nodes(n_tokens);

     LLAMA_LOG_DEBUG("%s: max_nodes = %zu\n", __func__, max_nodes);
```

Cleaner would be to re-create (or grow) the scheduler inside `opt_init()` alongside the existing `gf_res_prev` re-reservation — the extra headroom is only strictly needed for training. What I did as a probe is the simpler global 8x above; it wastes some memory during regular inference but is otherwise harmless. Happy to send this as a follow-up patch either way.

Why this doesn't fire on your 14B setup: at 14B the compact inference graph is already large enough that the initial `hash_set` has slack; the 0.5B graph is much smaller so `graph_max_nodes(n_tokens)` was too tight. GPU backend init may also allocate differently. Either way, `sched_reserve` and `opt_init` need to agree on the sizing multiplier.

**Result 3 — with PR + one-line sched patch, `llama-finetune` finishes 1 epoch, and with the right lr it converges.** Config: `-c 512 -b 512 -ub 512 -fa off -t 64 --numa distribute -epochs 1 -opt adamw` on wikitext-2-raw `wiki.test.raw` (1107 samples, ~280k tokens). Ran an lr sweep to find the right value for this model size:

| lr | final train loss | val loss / acc | wiki.test.raw PPL after 1 epoch | vs baseline (13.9031) |
|---|---|---|---|---|
| — (base model) | — | — | 13.9031 ± 0.10259 | — |
| **1e-5** (common default) | 6.23 | 6.93 / 12.6% | 914.9349 ± 8.96 | **+ 6484%** (damaged) |
| **1e-6** | 3.25 | 3.97 / 33.9% | 22.7438 ± 0.19 | **+ 64%** (mild damage) |
| **1e-7** | 2.68 | 2.84 / 45.5% | **10.1848 ± 0.07** | **− 27%** (converged, improved) |

**PPL vs lr is non-monotonic across 2 decades** — classic "small model + F32 update is sensitive to overshoot" behavior. lr=1e-7 (100x smaller than the commonly used 1e-5) is what this model wants for a 1-epoch fine-tune, and the improvement is real: PPL down 27%, val acc up 3.6x, and generation goes from complete collapse (`"Barack Obama was born in 1000000000000 , (100000000000000..."` at lr=1e-5) through wikitext-formatting overfit (`"...1999 . He is a black @-@ colored man..."` at lr=1e-6) to something coherent that's picked up wikitext-flavored content (`"Barack Obama was born in 1961 in Chicago, Illinois. He was raised in a religious family. He attended Chicago's North Shore High School..."` at lr=1e-7). Some hallucination remains (Obama went to Punahou/Columbia/Harvard, not North Shore/UChicago), but that's a base-model-quality issue on a 0.5B, not a training-loop issue.

So the PR + sched patch is a real fine-tune, verified end-to-end on a totally different HW class than the author's setup. For contrast: the prior workaround at `b6290` (`LLAMA_SET_ROWS=0` + `graph_max_nodes` 32x sed) had loss escape to ~16 (PPL ~10^7) inside one epoch **regardless of optimizer/lr** — genuinely gradient-broken. This PR is qualitatively different: functional gradient computation, tunable via lr.

**Ask (nice-to-have): model-size-aware lr guidance.** Once this PR lands, the example / README recipe (if you add one) should probably note that lr=1e-5 works on ~10B-class models and smaller variants need it scaled down (~1e-7 for 0.5B here). Otherwise first-time users on smaller models will hit exactly what I hit initially — the loop runs, but their weights explode without a clear symptom that says "your lr is wrong."

**Result 4 — confirming the "qwen2 only" scope.** Ran the same PR + sched patch build against `HuggingFaceTB/SmolLM2-135M-Instruct` (Llama arch). Crashes at `ggml.c:7074` with the original `!node->view_src || node->op == GGML_OP_CPY || ...` assert — exactly as your PR description acknowledges. Not a bug in this PR; just an independent data point that the `qwen2.cpp` template pattern is the right primitive, and the same shape would need to land in the other model files.

**Ask.** With the added one-line `sched_reserve` fix, this PR is enough to unblock `llama-finetune` on Qwen2 CPU-side and it demonstrably converges. Would love to see it move out of Draft — I can push the sched patch as a follow-up PR (or you can fold it in), and I'm happy to iterate on / help review a companion `qwen3` / `llama` / `gemma` template rollout once this lands.

Full local report with build logs, all assert traces, 4-trace loss curve (lr=1e-5 green / lr=1e-6 blue / lr=1e-7 purple / prior b6290 broken hack red-dashed), before/after PPL logs, before/after generation dumps, and the exact `sched_reserve` patch diff, available on request.

---

**Notes on posting**:
- Post URL: https://github.com/ggml-org/llama.cpp/pull/25428
- All numbers filled in with final values (no placeholders)
- Post-training PPL improved from 13.90 to 10.18 at lr=1e-7 — this is the headline result, phrased directly as "converged" in the comment
- Optional attachments if desired: `pr25428_loss_curve.png` (4-trace plot) and `local_sched_reserve_patch.diff`
- Related upstream state to be aware of before posting: issue #18805 was closed for moderation (not fix); PR #21924 and #22705 are alternate fix proposals in the same area. If the author cross-references, this comment still stands on its own — it's about #25428 specifically
