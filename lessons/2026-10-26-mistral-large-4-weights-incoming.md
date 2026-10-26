---
date: 2026-10-26
track: new-models
topic: Mistral Large 4, a 1T-parameter open-weights model whose weights are due this week
slug: mistral-large-4-weights-incoming
tags: [llm, open-weights, mistral, moe, self-hosting, pricing, multimodal]
read_time: 15 min
---

# 🆕 Mistral Large 4: a 1T-parameter "open" model, and what you should check before you download it

> **TL;DR**
> - Mistral Large 4 has been in public API preview since 2026-10-06. The weights are promised by the end of October, and one outlet reported 27 October. As far as I could verify, they are not downloadable yet, and the licence is unnamed.
> - It is a Mixture-of-Experts (MoE) model: about 1.05T parameters in total, but only about 5% of them run for each token. Active parameters set your compute cost. Total parameters set your memory bill.
> - Self-hosting only pays off at very high volume or when you need control over your data. At small scale the API is far cheaper.

> **Verification note.** I could not open Mistral's own announcement today. Everything below comes from secondary write-ups that quote it, and I flag places where they disagree. Treat numbers as *(unverified)* until you check Mistral's model page.

## What it is

Mistral AI (Paris) released **Mistral Large 4** (internal nickname "le Chonk") as a public preview on **2026-10-06**. It is available through Mistral Studio and the Mistral API. It is a natively multimodal model, so it takes images as well as text. Reports say it was trained from scratch on 3,800 NVIDIA Grace Blackwell GPUs in Mistral's own European data centres.

You may remember it from the Claude Haiku 5.5 lesson, where it appeared as a one-line sidebar. This lesson goes deeper because the weights are about to land, and a 1T-parameter download raises questions that a normal model release doesn't.

What the sources agree on:
- **Architecture:** a "granular" Mixture-of-Experts with about 1.05T total parameters and a 1.6B-parameter vision encoder.
- **Context window:** 1M tokens per Mistral. Two outside evaluators reportedly measured 512K *(unverified)*.
- **Status:** the API is live. The weights are "by the end of the month", after red-teaming with security partners. The Hugging Face page was reported as "Upcoming release" with an expected date of 2026-10-31, as of a screenshot on 2026-10-10.
- **Weights may change.** A co-founder reportedly said a final version will ship with the weights, so the checkpoint you download may differ from today's preview.

Where the sources **disagree** (check Mistral's page):
- **Active parameters:** Mistral's launch post is quoted as saying 49B active. Other pages, and the reported Hugging Face repo name (`...-1T-A52B`), say 52B.
- **API price:** most pages list **$1.36 input / $4.18 output** per 1M tokens. One lists a "Standard tier" of $0.68 / $0.07 cached / $2.09. A release tracker shows $0.75 / $2.30. The first is the most widely reported, and I use it below.
- **Licence:** not named. Mistral Large 3 shipped under Apache 2.0, and one outlet reports Large 4 will use a custom Mistral licence *(unverified)*. Whether you can use it commercially depends on this, so read it before you build on it.

## Why it matters

- **A European open-weights option:** teams with data-residency or sovereignty rules get a frontier-class candidate they could run on their own servers, if the licence allows it.
- **Fine-tuning and local control:** weights let you fine-tune, pin an exact version that never changes under you, and keep prompts inside your network.
- **A benchmark for the open-weights field:** it will be compared with DeepSeek V4.1 Flash (MIT licence, covered on 2026-10-19) and others, so you can run your own eval across all of them and compare cost per correct answer.

## How it works

A dense model uses every parameter for every token. An MoE model splits much of its feed-forward layers into many small "experts". A small router picks a few experts per token and the rest sit idle.

```
token ─► [attention] ─► router ─► picks a few experts out of many
                                   ┌────┐ ┌────┐ ┌────┐ ┌────┐ ...
                                   │ E1 │ │ E2 │ │ E3 │ │ E4 │   (most idle)
                                   └────┘ └────┘ └────┘ └────┘
                          only ~49B of 1,050B parameters do work for this token
```

Two consequences follow:

1. **Compute scales with active parameters** (about 49B). That is why a 1T-class model can be priced like a mid-tier model.
2. **Memory scales with total parameters** (about 1,050B), because any expert might be needed for the next token, so all of them must be loaded. At FP8 (8 bits, or 1 byte, per parameter) the weights alone are about 1,050 GB. That is why reports say you need a server with 8 large GPUs.

Different tokens use different experts, so the whole model has to stay in fast memory. "Only 5% is active" does not mean "runs on 5% of the hardware."

## Try it

```python
import math

TOTAL_B, ACTIVE_B = 1050, 49        # billions of parameters (Mistral's announcement)
GPU_GB = 141                        # one H200; change for your hardware
BYTES = {"BF16": 2, "FP8": 1, "4-bit": 0.5}   # bytes per parameter (4-bit is approximate)

print(f"Active per token: {ACTIVE_B / TOTAL_B:.1%} of the weights (sets compute)")
for fmt, b in BYTES.items():
    gb = TOTAL_B * b                # 1B params x 1 byte = 1 GB
    n = math.ceil(gb / GPU_GB)
    print(f"{fmt:>5}: weights ~{gb:,.0f} GB -> at least {n} GPUs, "
          f"{n * GPU_GB - gb:,.0f} GB left for KV cache")

IN_M, OUT_M = 2.0, 0.5              # millions of tokens per day
API_IN, API_OUT = 1.36, 4.18        # $/1M, preview list price (sources disagree)
GPU_HOUR = 3.00                     # ASSUMPTION: $/GPU-hour, replace with a real quote
api_day = IN_M * API_IN + OUT_M * API_OUT
own_day = 8 * GPU_HOUR * 24
print(f"API: ${api_day:,.2f}/day   8 GPUs 24/7: ${own_day:,.2f}/day")
print(f"Self-hosting breaks even at ~{own_day / api_day:,.0f}x this volume")
```

Expected output: about 4.7% active, FP8 weights of about 1,050 GB needing at least 8 GPUs with only about 78 GB left over, an API bill of about $4.81/day against $576/day for 8 rented GPUs, and a break-even near 120x the volume. The GPU price is my assumption, so plug in a real quote. The "KV cache" is the memory the model uses to remember the conversation so far. It grows with context length, so 78 GB is tight for long prompts. This is a simplified model that ignores batching, utilisation and the engineering time to run it.

## Where it fits

| | Mistral Large 4 | DeepSeek V4.1 Flash 1017 | Muse Wonder |
|---|---|---|---|
| Best for | Frontier-class open-weights candidate, multimodal, EU provenance | Cheap long-context agent work you can self-host | Long-running agents via a rented API |
| Cost / licence | Preview API about $1.36 / $4.18 per 1M *(sources differ)*. Weights and licence not yet published | $0.15 / $0.60 per 1M off-peak. MIT weights, 552B MoE | $4 / $20 per 1M. Closed weights |
| Watch out for | Weights are a promise until they ship. The final checkpoint may differ from the preview. Needs about 8 big GPUs at FP8 | Vendor-reported benchmarks, with the price varying by peak time and cache hits | Preview label, and no way to self-host |

The last two columns come from earlier lessons in this series (2026-10-19 and 2026-10-15).

## Flashcards

- **Q:** What is the status of Mistral Large 4 as of the sources I could reach (up to about 2026-10-10)?
  **A:** Public API preview since 2026-10-06. Weights are promised by the end of October (VentureBeat reported 27 Oct, and a Hugging Face page showed an expected 31 Oct). The licence is not named and the weights are not downloadable yet.
- **Q:** In a Mixture-of-Experts model, what do active parameters set and what do total parameters set?
  **A:** Active parameters (about 49B here) set compute per token, and so price and speed. Total parameters (about 1.05T) set memory, because all experts must be loaded even though a router picks only a few per token.
- **Q:** Roughly how much memory do the weights of a 1.05T-parameter model need at BF16, FP8 and 4-bit?
  **A:** About 2,100 GB, 1,050 GB and 525 GB (2, 1 and 0.5 bytes per parameter, so 4-bit is approximate). You then need extra memory for the KV cache, which grows with context length.
- **Q:** Why might self-hosting a 1T open-weights model cost far more than the API?
  **A:** You pay for about 8 big GPUs around the clock whether or not they are busy. With my assumed $3 per GPU-hour, that is about $576 a day against about $4.81 a day of API usage at 2M input and 0.5M output tokens. Self-host for control, privacy or very high volume, not to save money at small scale.
- **Q:** Name three things to check before building on an "open weights coming soon" model.
  **A:** (1) The licence terms, since Mistral Large 3 was Apache 2.0 but Large 4's terms were not named. (2) Whether the released checkpoint matches the preview you tested. (3) Your own eval results on your tasks, using cost per correct answer, not vendor benchmark tables.

## Quiz

1. A model has 1T total parameters and 50B active per token. Which resource does the *total* count mostly determine?
   - a) Compute (FLOPs) per generated token
   - b) Memory needed to hold the model
   - c) The number of tokens in the context window
   <details><summary>Answer</summary>b. The router can choose any expert for the next token, so all weights must be loaded. Active parameters (a) set compute per token. Context window (c) is a separate design choice.</details>

2. Your team wants to build on Mistral Large 4's weights. Which action is most sensible today?
   - a) Buy 8 GPUs now and start planning production around the preview checkpoint
   - b) Test the preview API on your own eval set, and wait for the licence and the final weights before committing hardware
   - c) Assume it is Apache 2.0 because Large 3 was
   <details><summary>Answer</summary>b. The API lets you measure quality and cost per correct answer now. The weights, final checkpoint and licence are not confirmed, so (a) and (c) are bets on a promise.</details>

3. At about 2M input and 0.5M output tokens per day, why did the script say renting 8 GPUs costs about 120x the API bill?
   - a) The API is subsidised, so it can never be beaten
   - b) GPUs bill for every hour they are reserved, but this workload only uses a sliver of their capacity
   - c) MoE models cannot run on rented GPUs
   <details><summary>Answer</summary>b. Self-hosting is a fixed cost, while API pricing is pay per token. It wins only when volume is high enough to keep the GPUs busy, or when you need data control. This relies on my assumed GPU price.</details>

## Go deeper

- [Mistral AI releases Mistral Large 4 (MarkTechPost, 2026-10-06)](https://www.marktechpost.com/2026/10/06/mistral-ai-releases-mistral-large-4-le-chonk-a-1-05t-parameter-open-weight-multimodal-moe/): a summary of the launch, including 49B active, 1M context and the API price.
- [Mistral Large 4: Benchmarks, Pricing and Open Weights (Beam, accessed 2026-10-26)](https://beam.ai/agentic-insights/mistral-large-4-open-weights): release timing, the 27 October report and the licence question.
- [Mistral Large 4, explained (System Design Academy, accessed 2026-10-26)](https://www.systemdesign.academy/explained/mistral-large-4): hardware sizing, with the roughly 1,050 GB FP8 figure.
- [Mistral Large 4 explained simply (Airtics, accessed 2026-10-26)](https://www.airtics.org/mistral-large-4/): the Hugging Face "Upcoming release" page, with an expected date of 2026-10-31 as of a screenshot on 2026-10-10.
- Not covered, since I could not verify details: release trackers also list Kimi K3.1 Pro (2026-10-23), MiniMax M3.1 Flash (2026-10-19) and Ling 3.1 Flash 1019 (2026-10-22). Check the official model pages before relying on any of them.

---
⏭️ **Tomorrow:** 🧱 Tech Stack, streaming responses: how to show tokens as they arrive, and what changes in your code when you do.
