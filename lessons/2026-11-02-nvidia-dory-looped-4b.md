---
date: 2026-11-02
track: new-models
topic: NVIDIA Dory 1.0 4B, a looped model that thinks by re-running its own layers
slug: nvidia-dory-looped-4b
tags: [llm, open-weights, nvidia, small-models, reasoning, inference-compute, openmdw]
read_time: 15 min
---

# 🆕 NVIDIA Dory 1.0 4B: a small model with a "loops" dial

> **TL;DR**
> - Dory is a 4B-parameter open-weights model that re-runs one shared block of layers 1, 2 or 4 times for each token. You choose the number of loops at serving time, from the same checkpoint.
> - This is a third way to buy accuracy with compute. The first two are more parameters and longer visible chains of thought. Looping adds neither parameters nor output tokens.
> - NVIDIA's own table says 2 loops beats Qwen3.5-4B on several benchmarks. Those numbers are vendor-reported, so test it on your own tasks before you believe them.

## What it is

NVIDIA released **Nemotron Labs Dory 1.0 4B** on **2026-10-16**. The model card describes a <em>looped</em> (also called latent-recurrent) language model. It has about 4B parameters, a context length of up to 256K tokens, and English-only support. Its architecture is a normalized GPT that interleaves sliding-window attention layers with full-attention layers. The licence is the **OpenMDW License Agreement v1.1**. The card says it was pre-trained on 6T tokens.

A note on timing: that date is 17 days ago, just outside the usual two-week window. I picked it anyway because it introduces a genuinely new idea and you can run it today on a single consumer GPU. Kimi K3.1 Pro, whose weights are due by 2026-11-04, is a better fit for a later "this week in AI" lesson.

The new part is the **loop**. A normal transformer runs your tokens through a stack of *different* layers once. Dory has a shared block of layers that the model can apply repeatedly, so the same weights get several passes before it emits each token. Per the model card, repeating the shared block lets Dory "spend more compute per token". Secondary write-ups that quote the card say the same checkpoint supports **1, 2 or 4 loops**, with 2 as the recommended default.

The weights come in several formats. According to a secondary model-hub page, they range from a 7.95 GB full-precision file to a 3.20 GB NVFP4 file, and there is a GGUF export for llama.cpp. I did not confirm those sizes on the primary page, so check the repo.

## Why it matters

- **On-device and edge assistants.** A 4B model fits on one consumer GPU, and the loop count lets one deployment serve both quick and hard requests.
- **Cost tiers without model sprawl.** A support tool could run 1 loop for FAQ-style questions and 4 loops for hard ones, without hosting two different models.
- **Private or air-gapped code and ops helpers.** Open weights you host yourself mean prompts never leave your machine. NVIDIA reports 59.5 on SWE-bench Verified at 2 loops (vendor-reported), which is why a model this small is being discussed for agent work.

## How it works

You already know two ways to get more accuracy from a model:

1. **More parameters.** Use a bigger model. It costs more memory and more money per token.
2. **More output tokens.** Use a reasoning model with higher effort. It writes a long chain of thought first, and you pay for those tokens as output (see the GPT-6.1 Sol lessons).

Looping is a third way: **more passes through the same weights, inside the model, before each token comes out.**

```
Standard transformer:   tokens → [L1][L2][L3]...[L24] → next token

Looped (simplified):    tokens → [ shared block ] ─┐
                                      ▲            │  repeat n times
                                      └────────────┘
                                         → next token
```

The diagram is a simplification. The model card says the shared block is applied several times, but I haven't confirmed exactly which layers sit inside the loop and which sit outside it.

Three consequences follow, and the first two are my own reasoning rather than NVIDIA's claims:

- **Memory barely changes.** The weights are stored once, however many times you reuse them. The 4B model stays a 4B model on disk.
- **Compute per token goes up.** More loops means more work per generated token, so expect higher latency and lower throughput at 4 loops than at 1. Measure it, because the exact slowdown depends on your hardware and server.
- **The extra thinking is hidden.** The repeated passes happen in the model's internal state, not as visible text. You won't see them as reasoning tokens on a bill, but you will see them as extra seconds per request.

One more serving detail. A secondary article shows a vLLM command that sets `n_recurrent_loops` and `recurrent_kv_cache_mode` through `--hf-overrides`. I couldn't verify those key names against the model card, so use the card's serving instructions if they differ. The KV cache is the memory the server keeps for tokens it has already processed, and loops affect how it is handled. The model card is the place to learn what each mode means.

## Try it

This script scores a tiny known-answer test set against a locally served Dory. Run it once for each loop count, restarting the server in between. It then reports accuracy, latency and tokens per question.

```python
# pip install openai   (and vllm, on a machine with a GPU)
# 1) Serve once per loop count (override key names: confirm on the model card):
#    vllm serve nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16 --max-model-len 32768 \
#      --hf-overrides '{"n_recurrent_loops": 2}'
# 2) python dory_bench.py 2
import os, re, sys, time
from openai import OpenAI

loops = sys.argv[1] if len(sys.argv) > 1 else "?"
client = OpenAI(base_url=os.environ.get("DORY_BASE_URL", "http://localhost:8000/v1"),
                api_key=os.environ.get("OPENAI_API_KEY", "none"))
MODEL = "nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16"
CASES = [
    ("A train travels 180 km in 2.5 hours. What is its average speed in km/h?", 72),
    ("What is 17 * 24?", 408),
    ("What is the sum of the integers from 1 to 40?", 820),
    ("A shirt costs $80 after a 20% discount. What was the original price?", 100),
    ("How many distinct arrangements are there of the letters in LEVEL?", 30),
    ("If 3x + 7 = 40, what is x?", 11),
    ("What is the smallest prime greater than 90?", 97),
    ("What is the remainder when 2^10 is divided by 7?", 2),
    ("A rectangle has perimeter 36 and length twice its width. What is its area?", 72),
    ("How many days from March 1 to May 1 in a non-leap year?", 61),
]
correct = tokens = 0
start = time.time()
for question, answer in CASES:
    r = client.chat.completions.create(
        model=MODEL, temperature=0, max_tokens=2048,
        messages=[{"role": "user",
                   "content": question + " End with a line 'ANSWER: <number>'."}])
    found = re.findall(r"ANSWER:\s*\$?(-?\d+(?:\.\d+)?)", r.choices[0].message.content or "")
    correct += bool(found) and float(found[-1]) == answer
    tokens += r.usage.completion_tokens
n = len(CASES)
print(f"loops={loops} correct={correct}/{n} avg_s={(time.time()-start)/n:.1f} avg_tokens={tokens/n:.0f}")
```

You should get one line per run, such as `loops=2 correct=… avg_s=… avg_tokens=…`. Run it for 1, 2 and 4 loops and compare the three lines. With only ten questions the accuracy numbers are noisy. The `avg_s` column is the more reliable signal of what extra loops cost you. If a run gives odd output, check that the model's chat template is loaded.

## Where it fits

| | Dory 4B (looped) | A bigger model (for example Qwen3.5-9B) | A small reasoning model with thinking on |
|---|---|---|---|
| Best for | One small checkpoint, with compute chosen per deployment | Higher raw quality where memory allows | Tasks that benefit from visible step-by-step work |
| Cost / licence | Open weights, OpenMDW v1.1 (read it). You pay in GPU time, and cost grows with loops | Depends on the model's licence. More memory than 4B | Thinking tokens are billed as output on APIs, and they cost seconds when self-hosted |
| Watch out for | Vendor-reported benchmarks. English only. Loop support depends on your serving stack | Bigger GPU needed, and no per-request compute dial | Long outputs and unpredictable token counts |

For scale, here is what NVIDIA's own comparison table reportedly shows, as quoted by a secondary site. At 2 loops, Dory scores 59.5 on SWE-bench Verified, against 54.7 for Qwen3.5-4B and 61 for Qwen3.5-9B. The same source says Dory scores *lower* than Qwen3.5-4B on GPQA Diamond (72.41 vs 77.71). So the picture is mixed, and it depends on your task.

## Flashcards
- **Q:** What is a looped (latent-recurrent) language model, and what does NVIDIA's Dory 1.0 4B let you choose at serving time?
  **A:** A model that re-applies a shared block of layers several times per token. Dory is released as one checkpoint, and per secondary reports of the model card you pick 1, 2 or 4 loops (2 is the recommended default).
- **Q:** How does looping differ from using a bigger model or a higher reasoning effort?
  **A:** A bigger model adds parameters (more memory). Higher effort adds visible reasoning tokens (billed as output). Looping re-runs the same weights inside the model, so memory stays about the same and compute per token goes up, with no extra visible tokens.
- **Q:** What are Dory 1.0 4B's release date, context length and licence?
  **A:** Released 2026-10-16. It supports up to 256K tokens of context, and the licence is OpenMDW License Agreement v1.1. It is English only per the model card.
- **Q:** What do more loops cost you, and what do they not cost?
  **A:** They cost compute per token, so expect more latency and less throughput (measure it). They don't add parameters, so memory for the weights stays about the same. This is my inference, so benchmark it.
- **Q:** Why shouldn't you adopt Dory just because it beats Qwen3.5-4B in NVIDIA's table?
  **A:** The table is vendor-reported, on chosen benchmarks. It also shows Dory behind on some rows (for example GPQA Diamond). Run your own eval and compare accuracy, latency and cost per correct answer at 1, 2 and 4 loops.

## Quiz
1. What does increasing the loop count in Dory change?
   - a) The number of parameters stored on disk
   - b) How many times the shared block of layers is applied per token
   - c) The licence terms
   <details><summary>Answer</summary>b. The weights are shared and stored once, so the size on disk stays the same. Only the amount of compute per token changes.</details>
2. You serve Dory at 4 loops and your latency doubles versus 1 loop, but accuracy on your test set barely moves. What should you do?
   - a) Keep 4 loops, because more compute is always better
   - b) Switch to a bigger model immediately
   - c) Drop to fewer loops for this workload, and re-test on a larger eval
   <details><summary>Answer</summary>c. The loop count is a dial, and you tune it on your own data. If extra loops buy nothing, you are only paying in latency. Ten questions is a small sample, so confirm with a larger eval first.</details>
3. Which of these claims about Dory is safest to repeat as a fact?
   - a) It beats Qwen3.5-4B on every benchmark
   - b) It scored 59.5 on SWE-bench Verified, so it will do 59.5% of your coding tasks
   - c) It was released on 2026-10-16 under OpenMDW v1.1, per its model card
   <details><summary>Answer</summary>c. That comes from the primary model card. The others are wrong: Dory trails on some rows of NVIDIA's own table, and a benchmark score on one test set doesn't transfer to your tasks.</details>

## Go deeper
- [NVIDIA-Nemotron-Labs-Dory1.0-4B-MXFP8 model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-MXFP8) (NVIDIA on Hugging Face, release date 2026-10-16). This is the primary source for the architecture, licence, context length and training data.
- [Nemotron Labs Dory 1.0 4B overview](https://ai-tldr.dev/models/nemotron-labs-dory-1-0-4b/) (secondary summary, accessed 2026-11-02). This is where the 1/2/4-loop figures and NVIDIA's comparison numbers come from. Check them against the model card.
- [NVIDIA releases Dory 4B, a looped reasoning model](https://www.datastudios.org/post/nvidia-dory-4b-looped-reasoning-256k-context-elastic-inference-benchmarks) (Data Studios, accessed 2026-11-02). This is the source of the example vLLM serving command, which I could not verify against NVIDIA's docs.

---
⏭️ **Tomorrow:** 🧱 Tech Stack, prompt caching. We'll look at how repeating a stable prefix can cut both cost and latency, and how to structure prompts so the cache actually hits.
