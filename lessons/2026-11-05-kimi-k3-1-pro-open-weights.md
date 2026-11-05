---
date: 2026-11-05
track: new-models
topic: Kimi K3.1 Pro open weights, a 2.8T-parameter model you can download and the licence line that decides if you can use it
slug: kimi-k3-1-pro-open-weights
tags: [llm, open-weights, moonshot, kimi, moe, licensing, self-hosting, pricing]
read_time: 15 min
---

# 🆕 Kimi K3.1 Pro open weights: 2.8T parameters, 1.56 TB, and one licence clause worth reading

> **TL;DR**
> - Moonshot AI published the weights of Kimi K3.1 Pro on Hugging Face on 2026-11-04. It is a 2.8T-parameter Mixture-of-Experts model (104B active per token) with a 1M-token context, and the repo is ungated.
> - The checkpoint is about 1.56 TB, not the ~5.6 TB you get from a BF16 estimate. It was trained to run with 4-bit weights, so check what a checkpoint actually weighs before planning hardware.
> - The licence is custom ("MIT-style" in secondary summaries). Reports say hosted-service businesses above roughly $20M revenue need a separate agreement. Read the LICENSE file before you build a product on it.

## What it is

Kimi K3.1 Pro is the newest flagship from Moonshot AI, a Beijing lab. It is **not a brand-new model**. Moonshot launched it through its API on 2026-10-23 as the first model in a "K3.1" series. According to Moonshot's model card it is post-trained from Kimi K3 with large-scale reinforcement learning. Secondary coverage says the architecture is unchanged from K3. The new part, and the reason for this lesson, is that on **2026-11-04** Moonshot made good on its launch promise and put the full weights on Hugging Face (`moonshotai/Kimi-K3.1-Pro`). Moonshot announced it on X that day. One outlet reported 2 November, but Moonshot's own post and most coverage say 4 November, so I use that.

The specs from the model card: a Mixture-of-Experts (MoE) design with **2.8T total parameters and 104B activated per token**, 93 layers, and a context window of 1,048,576 tokens. It takes text and images as input. Moonshot says it improves coding, 3D creation, financial research and factual accuracy. The weights are stored in a 4-bit format (MXFP4) with 8-bit activations (MXFP8). Secondary reports say Moonshot used quantization-aware training, meaning the model was trained knowing it would be compressed. The model card recommends serving it with vLLM, SGLang or TokenSpeed.

You can also call it without downloading anything. The API model ID is `kimi-k3.1-pro` on platform.kimi.ai, with OpenAI- and Anthropic-compatible endpoints. At the 10-23 launch, secondary sources reported the price as **$2 per 1M input tokens and $10 per 1M output tokens**. Check the pricing page before you budget.

## Why it matters

- **A frontier-sized model you can inspect and fine-tune.** The repo is public and ungated. Moonshot's own benchmark table compares it with Claude Opus 5.5 and GPT-6 Astra, but those scores are vendor-reported. Now outside teams can run it on their own harnesses.
- **Data-residency and control use cases.** A bank or hospital that can't send text to a third-party API can run the weights in its own cloud, if it has the hardware. A third option exists too. Secondary reports say Ollama Cloud, Nebius and Databricks added support quickly, and OpenRouter lists many hosts. Which host you use matters for the licence (see below).
- **A price anchor for negotiations.** Even if you never self-host, an open 2.8T model that other companies can host puts pressure on closed-model API prices.

## How it works

The two numbers that matter for a big MoE model are different resources:

```
              total params (2.8T)            active params (104B)
              ───────────────────            ────────────────────
 sets...      MEMORY: every expert must      COMPUTE per token: only a few
              be loaded on GPUs              experts run, chosen by a router
 you pay...   once, as hardware              on every token, as speed and price
```

Only about 3.7% of the parameters run for any one token. That keeps speed and per-token cost closer to a ~100B model. But the whole 1.56 TB still has to sit in GPU memory, plus the **KV cache** (the saved attention state for every token in the context, which grows with prompt length).

**Why 1.56 TB and not 5.6 TB?** The BF16 estimate is 2 bytes per parameter, so 2.8T × 2 = 5.6 TB. Some early coverage quoted that figure. The real repo is 1.56 TB across 96 shards of about 17 GB. That works out to about 0.56 bytes per parameter. It's a bit above the naive 4-bit figure of 0.5, because real 4-bit files also store scale values and some layers likely stay at higher precision. We saw the same effect with Mistral Large 4 recently. Rule: **read the file sizes on the Hub, not a formula.**

**The hardware.** One post circulating on X describes a setup of 8 NVIDIA B300 GPUs with about 2.3 TB of total GPU memory as one way to run it. That leaves roughly 0.7 TB for KV cache and overhead. This is one possible setup, not a minimum spec I could verify.

**The licence.** On Hugging Face the licence is tagged `other` with the name `kimi-k3.1-pro`, so it isn't Apache 2.0 or MIT. Two secondary sources summarise it as permission to use, modify, fine-tune, sell and redistribute, with two conditions for very large operators:

1. Businesses that sell the model as a hosted service and exceed about $20M in revenue need a separate agreement with Moonshot.
2. Very large products must display the model's name.

*(unverified: I could not open the LICENSE file myself, and the exact thresholds and wording should be read there.)* The practical point is that the clause targets "model-as-a-service" companies. It probably doesn't affect a team using the model inside its own product, but a lawyer should confirm that.

## Try it

A back-of-envelope calculator for the "download it or rent it" decision. Every `ASSUMED` line is a guess you should replace with a real quote.

```python
# No pip install needed. Edit the ASSUMED numbers for your own situation.
TOTAL_PARAMS = 2.8e12      # Kimi K3.1 Pro total parameters (model card)
ACTIVE_PARAMS = 104e9      # active per token (model card)
REPO_TB = 1.56             # size of the published checkpoint on Hugging Face (reported)
GPU_GB = 288               # ASSUMED: one B300-class GPU
GPUS = 8                   # ASSUMED: one server
GPU_HOUR_USD = 5.0         # ASSUMED rental price per GPU-hour, check your quote
API_IN, API_OUT = 2.0, 10.0  # USD per 1M tokens, launch API price (reported)

print("Weights if stored at different precisions (TB):")
for name, bytes_per in [("BF16", 2), ("FP8", 1), ("4-bit naive", 0.5)]:
    print(f"  {name:12s} {TOTAL_PARAMS * bytes_per / 1e12:5.2f}")
print(f"  {'actual repo':12s} {REPO_TB:5.2f}  -> {REPO_TB * 1e12 / TOTAL_PARAMS:.2f} bytes/param")

vram_tb = GPU_GB * GPUS / 1000
print(f"\nGPU memory: {vram_tb:.2f} TB, left for KV cache: {vram_tb - REPO_TB:.2f} TB")
print(f"Active fraction per token: {ACTIVE_PARAMS / TOTAL_PARAMS:.1%}")

daily_gpu = GPUS * GPU_HOUR_USD * 24
for in_m, out_m in [(2, 0.5), (200, 50), (2000, 500)]:  # millions of tokens per day
    api = in_m * API_IN + out_m * API_OUT
    print(f"{in_m:>5}M in / {out_m:>5}M out per day: API ${api:>8,.0f} vs GPUs ${daily_gpu:,.0f} (always on)")
```

Expected output: a weights table (5.60 / 2.80 / 1.40 TB, then the actual 1.56 TB at 0.56 bytes per parameter), about 0.74 TB left for KV cache, and three volume rows. At my assumed $5 per GPU-hour, the API costs $9 a day at small volume against $960 for the always-on GPUs. The two cross at about 213M input and 53M output tokens a day. Whether one server can actually serve that volume is something you have to measure, and the calculator does not tell you. The calculator also ignores engineering time, which is usually the biggest hidden cost of self-hosting.

## Where it fits

| | Kimi K3.1 Pro | Mistral Large 4 | DeepSeek V4.1 Flash |
|---|---|---|---|
| Best for | Frontier-class agentic coding and long-context work where you want the option to self-host | Large open MoE with weights available since 2026-10-29 | Cheap, high-volume agent work with an MIT licence |
| Size | 2.8T total, 104B active, 1M context | ~1T total, ~49B active | 552B total, 1M context |
| Cost / licence | API reportedly $2 / $10 per 1M tokens. Custom Kimi licence, with a reported ~$20M hosted-service clause | Modified-MIT licence. Anyone running a "Model as a Service" business needs a commercial licence | MIT. API $0.15 input (cache miss) and $0.60 output per 1M off-peak, double at peak |
| Watch out for | ~1.56 TB of weights, licence text, vendor-only benchmarks | Same licence-reading homework, plus a big memory footprint | Smaller model, so run your own eval on hard tasks |

## Flashcards

- **Q:** What did Moonshot AI release on 2026-11-04, and how does it relate to the 2026-10-23 launch?
  **A:** The open weights of Kimi K3.1 Pro on Hugging Face (`moonshotai/Kimi-K3.1-Pro`, ungated). The model itself launched on the API on 2026-10-23 and is post-trained from Kimi K3. The weights arrived about 12 days later, as promised.
- **Q:** What are Kimi K3.1 Pro's size and context window, and what do the "total" and "active" numbers each set?
  **A:** 2.8T total and 104B active parameters per token, with a 1,048,576-token context. Total parameters set memory, because every expert must be loaded. Active parameters set compute per token, so speed and price.
- **Q:** Why is the Kimi K3.1 Pro checkpoint about 1.56 TB when 2.8T parameters at BF16 would be 5.6 TB?
  **A:** The weights are stored in 4-bit MXFP4, and the model was reportedly trained with quantization-aware methods. The real file is ~0.56 bytes per parameter, a little above the naive 0.5 because of scales and some higher-precision layers. Read the real file sizes on the Hub.
- **Q:** What kind of licence do the Kimi K3.1 Pro weights have, and what is the catch?
  **A:** A custom "Kimi K3.1 Pro License", not Apache or MIT. Secondary summaries call it MIT-style, but hosted-service businesses above about $20M revenue need a separate agreement, and very large products must show the model's name. Unverified, so read the LICENSE file.
- **Q:** What are the three ways to use an open-weights model like this, and when does self-hosting beat the API?
  **A:** (1) The vendor's API, (2) a third-party host, (3) self-hosting. Self-hosting means paying for GPUs around the clock, so it tends to win only at very high steady volume or when privacy or control rules out an API. Compute the break-even with your own quote and measure throughput first.

## Quiz

1. A teammate says "2.8T parameters at 2 bytes each, so we need 5.6 TB of GPU memory for Kimi K3.1 Pro." What is the best response?
   - a) Correct, because weights are always stored in BF16
   - b) Wrong: the published checkpoint is 4-bit, about 1.56 TB, though you still need extra memory for the KV cache
   - c) Wrong: only the 104B active parameters need to be in memory
   <details><summary>Answer</summary>b. The release is stored at about 4 bits per parameter. And (c) is the common mistake: a router picks different experts for different tokens, so all experts must be loaded even though few run per token.</details>

2. Your company sells an "AI platform" that lets other businesses call open models through your own API, and it makes more than $20M a year. What should you do before hosting Kimi K3.1 Pro?
   - a) Nothing, because the weights are public and ungated
   - b) Read the LICENSE file, because reports say hosted-service businesses above a revenue threshold need a separate agreement
   - c) Switch to a model with a larger context window
   <details><summary>Answer</summary>b. "Ungated download" doesn't mean "no conditions". Per secondary summaries, that clause targets exactly your situation. Confirm the real text and thresholds with a lawyer.</details>

3. At small volume, why can the API be far cheaper than self-hosting this model?
   - a) API tokens are always free for open-weights models
   - b) Self-hosting pays for the GPUs every hour whether or not they are busy, while the API charges only for tokens you use
   - c) MoE models can't run on GPUs
   <details><summary>Answer</summary>b. In the calculator, 8 GPUs at an assumed $5 per hour cost $960 a day regardless of load, against about $9 a day of API usage at 2M input and 0.5M output tokens.</details>

## Go deeper
- [moonshotai/Kimi-K3.1-Pro model card](https://huggingface.co/moonshotai/Kimi-K3.1-Pro) (Moonshot AI on Hugging Face, accessed 2026-11-05)
- [Releasing the model weights of Kimi K3.1 Pro](https://x.com/Kimi_Moonshot/status/2118010528123773297) (Moonshot AI on X, 2026-11-04)
- [Kimi K3.1 Pro Weights: 1.56 TB and a $20M Licence Line](https://www.orcarouter.ai/blog/kimi-k3-1-pro-weights-released-self-hosting-cost) (OrcaRouter, secondary source on size and licence, accessed 2026-11-05)

---
⏭️ **Tomorrow:** 💼 Use Cases, a look at how a real company wires an AI agent into its workflow and what the architecture behind it looks like.
