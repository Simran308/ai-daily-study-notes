---
date: 2026-10-08
track: new-models
topic: Claude Haiku 5.5 and the 100k-token price cliff
slug: claude-haiku-5-5
tags: [llm, anthropic, pricing, small-models, sub-agents, mistral]
read_time: 15 min
---

# 🆕 Claude Haiku 5.5 and the 100k-token price cliff

> **TL;DR**
> - Anthropic released Claude Haiku 5.5 on 2026-10-07. It costs $0.10 / $0.50 per 1M input / output tokens for requests under 100k tokens, and $0.50 / $2.50 above that.
> - Per-token prices fell about 90% against Haiku 4.5. Anthropic's own estimate of the real saving is about 75%, because the new model reportedly uses more tokens per task.
> - Two-tier pricing means your request size now affects your unit price. A cost estimator should model the cliff.

> **Verification note:** my research tools hit a usage limit before I could open Anthropic's own announcement and docs. The facts below come from several independent news and analytics write-ups that agree with each other. Anything I couldn't cross-check is marked *(unverified)*. Before you build on any number here, check the official Anthropic pricing page.

## What it is

On Wednesday 2026-10-07, Anthropic released **Claude Haiku 5.5**. It is the small, cheap, fast tier of the Claude 5.5 family and the successor to Haiku 4.5. Anthropic positions it for high-volume work: summarising documents, classifying text, querying databases, and acting as a **sub-agent**. A sub-agent is a cheap worker model that a bigger model delegates small tasks to.

The headline is price. Haiku 4.5 cost $1 / $5 per 1M input / output tokens. Haiku 5.5 charges less than that for short requests and has a second, higher tier for long ones:

| Per 1M tokens | Haiku 5.5, request ≤ 100k tokens | Haiku 5.5, request > 100k tokens | Haiku 4.5 |
|---|---|---|---|
| Input | $0.10 | $0.50 | $1.00 |
| Output | $0.50 | $2.50 | $5.00 |
| Cache read | $0.01 | $0.05 | $0.10 |
| Cache write | $0.125 | $0.625 | $1.25 |

Anthropic says about 90% of Haiku 4.5 requests fall under the 100k line. The short-request price matches OpenAI's GPT-6 Luna, as covered in earlier lessons. Anthropic's own estimate is that typical workloads cost roughly 75% less than on Haiku 4.5. That is smaller than the 90% sticker cut because one report notes Haiku 5.5 consumes more tokens. Anthropic's benchmark table (vendor-reported) has it ahead of GPT-6 Luna on all six listed benchmarks, with the biggest gaps in computer use and agentic coding. Treat that as a claim to test on your own data, not a fact.

**Also this week: Mistral Large 4 (preview).** Mistral released it on 2026-10-06 through its API and Mistral Studio. It has about 1 trillion parameters, with about 49B active per token. "Active" parameters are the ones used for any single token, so only a fraction of the model runs on each step. Mistral has promised open weights, which means a downloadable model. Reports give the date as 2026-10-27 or "end of October", so **you can't download it yet**. Artificial Analysis, an independent benchmarking site, scored the preview 38 on its Intelligence Index, level with GPT-6 Luna at max effort. Standard list pricing is $1.36 / $4.18 per 1M input / output tokens, with a launch discount of half that. Reports disagree on the context window (512k vs 1M), so check the docs.

## Why it matters

- **Classification and extraction at scale:** a support-ticket router handling millions of messages a day is dominated by input cost, so a 10x cut changes what you can afford to automate.
- **Sub-agents:** a larger model plans, then fans out dozens of small "read this file and report" calls to a Haiku-class model. Total agent cost is mostly the sub-calls.
- **Live, latency-sensitive features:** customer-support chat and autocomplete need fast responses as much as cheap ones, and small models are the usual fit.

## How it works

Haiku 5.5 is not a new technique. The new part is the **tiered price per request**. The tier is picked by the size of the request, not by your monthly volume.

```
prompt tokens (input + cache reads + cache writes)
        │
        ├── ≤ 100,000 ──► $0.10 in / $0.50 out   (cheap tier)
        └──  > 100,000 ──► $0.50 in / $2.50 out   (5x the price)
```

Here is what that means for one summarisation job. *This assumes the higher tier applies to the whole request once it crosses the line, which is how the reports read. Confirm it in the docs.*

- 80k tokens in, 2k out: 0.08 × $0.10 + 0.002 × $0.50 = **$0.009**
- 120k tokens in, 2k out: 0.12 × $0.50 + 0.002 × $2.50 = **$0.065**, about 7x more for 1.5x more text.
- Two separate 60k requests, if the task splits cleanly: about **$0.013**.

Crossing 100k tokens can cost several times more. If your workload can be chunked, "map" over the pieces with small requests and "reduce" the results. Don't send one giant prompt.

**Price per token isn't price per task.** Suppose a model's price drops 90% but it uses 2.5x as many tokens per task. Your cost is 0.1 × 2.5 = 0.25 of the old cost, a 75% saving, not 90%. That is made-up arithmetic to show the mechanism, not Anthropic's actual token ratio. It's the reason to measure cost per task on your own data. Lesson 2026-10-07 showed how to do that.

## Try it

```python
# pip install anthropic   (needs ANTHROPIC_API_KEY in your environment)
import anthropic

MODEL = "claude-haiku-5-5"  # ID listed by API gateways (unverified): confirm in Anthropic's docs
# $ per 1M tokens: (input, output, cache_read, cache_write)
SHORT = (0.10, 0.50, 0.01, 0.125)   # request <= 100k tokens
LONG  = (0.50, 2.50, 0.05, 0.625)   # request  > 100k tokens

def cost(u):
    inp = u.input_tokens
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0
    i, o, r, w = SHORT if inp + cr + cw <= 100_000 else LONG
    return (inp * i + u.output_tokens * o + cr * r + cw * w) / 1e6

def what_if(prompt_tokens, out_tokens=2_000):
    t = SHORT if prompt_tokens <= 100_000 else LONG
    return (prompt_tokens * t[0] + out_tokens * t[1]) / 1e6

for n in (80_000, 99_000, 101_000, 120_000):
    print(f"{n:>7} tokens in -> ${what_if(n):.4f}")

client = anthropic.Anthropic()
resp = client.messages.create(
    model=MODEL, max_tokens=300,
    messages=[{"role": "user", "content": "Classify as bug/feature/question: 'App crashes on login'"}],
)
print(resp.content[0].text)
print(f"real usage cost: ${cost(resp.usage):.6f}")
```

The first four lines show the cost jump between 99k and 101k tokens. The last line prints a tiny dollar amount, a fraction of a cent, for the one real call. If the model ID is rejected, check the current model list and update `MODEL`.

## Where it fits

| | Claude Haiku 5.5 | GPT-6 Luna | Mistral Large 4 (preview) |
|---|---|---|---|
| Best for | High-volume classification, summaries, sub-agents | Same tier from OpenAI | Self-hosting later, EU-region hosting, multilingual (Mistral claims 160+ languages) |
| Cost / licence | $0.10 / $0.50 under 100k tokens, $0.50 / $2.50 above. Closed, API only | Reported at the same $0.10 / $0.50 | $1.36 / $4.18 list ($0.68 / $2.09 launch discount). Open weights promised, licence terms not confirmed in my sources |
| Watch out for | Price cliff at 100k. Reportedly uses more tokens per task | Compare on your own tasks, not vendor tables | Preview only, so no download yet. Most benchmark claims are Mistral's own. A 1T-parameter model needs serious GPUs to self-host |

## Flashcards
- **Q:** What are Claude Haiku 5.5's API prices per 1M input / output tokens, and where does the price change?
  **A:** $0.10 / $0.50 for requests of 100,000 tokens or fewer. Above 100k tokens it is $0.50 / $2.50. Haiku 4.5 was $1 / $5. It was released on 2026-10-07.
- **Q:** Why does Anthropic estimate about 75% savings over Haiku 4.5 when per-token prices fell 90%?
  **A:** Haiku 5.5 reportedly consumes more tokens per task, and some requests land in the pricier long tier. Cost per task is price per token × tokens used, so measure it on your own workload.
- **Q:** How can you reduce cost when a task would push a request past the 100k-token tier?
  **A:** Split it into smaller requests that each stay under 100k (map), then combine the results (reduce). This assumes the task decomposes cleanly and that the higher rate applies to the whole request.
- **Q:** What is a sub-agent, and why are Haiku-class models a good fit for them?
  **A:** A cheap worker model that a larger planning model delegates small, well-defined tasks to (reading files, classifying, extracting). Most of an agent's tokens go through these calls, so low price and low latency matter most there.
- **Q:** What's the status of Mistral Large 4 as of 2026-10-08?
  **A:** Public API preview since 2026-10-06. It has about 1T total and about 49B active parameters per token. Open weights are promised for late October (reports say 2026-10-27 or "end of month") but are not downloadable yet.

## Quiz
1. A single Haiku 5.5 request has 120,000 prompt tokens. What input price per 1M tokens applies?
   - a) $0.10
   - b) $0.50
   - c) $1.00
   <details><summary>Answer</summary>b. Requests above 100k tokens use the long-request tier, $0.50 per 1M input. $0.10 is the short tier, and $1.00 was Haiku 4.5's price.</details>
2. Haiku 5.5's per-token prices are about 90% lower than Haiku 4.5's, yet Anthropic estimates roughly 75% lower workload cost. Why?
   - a) Output tokens are billed at a higher multiple
   - b) The new model reportedly uses more tokens per task, and some requests fall in the long tier
   - c) Cached tokens are not discounted
   <details><summary>Answer</summary>b. Cost per task is price × tokens used. More tokens per task, plus requests above 100k tokens, shrink the headline saving. Cache reads are actually discounted heavily ($0.01 per 1M in the short tier).</details>
3. Which statement about Mistral Large 4 is true today (2026-10-08)?
   - a) You can download the weights from Hugging Face
   - b) It is available only as a closed API with no plans to open it
   - c) It is available as an API preview, with open weights promised later in October
   <details><summary>Answer</summary>c. The API preview launched on 2026-10-06. The weights are promised for late October, and the Hugging Face page currently shows an "upcoming release" countdown.</details>

## Go deeper
- [Anthropic launches Claude Haiku 5.5 with 90% API price reduction, matching GPT-6 Luna](https://venturebeat.com/technology/anthropic-launches-claude-haiku-5-5-with-90-api-price-reduction-matching-gpt-6-luna) (VentureBeat, 2026-10-07). It has the full price table and the 90% / 75% explanation.
- [Anthropic launches Claude Haiku 5.5 with aggressive pricing, but it consumes far more tokens](https://www.neowin.net/news/anthropic-launches-claude-haiku-55-with-aggressive-pricing-but-it-consumes-far-more-tokens/) (Neowin, accessed 2026-10-08). It covers the benchmark comparison with GPT-6 Luna and the token-consumption caveat.
- [Mistral has released Mistral Large 4](https://artificialanalysis.ai/articles/mistral-large-4-france-ai) (Artificial Analysis, October 2026). Independent index scores and cost per task.
- [Europe's Mistral launches Large 4](https://thenextweb.com/news/mistral-releases-large-4-a-1-trillion-parameter-open-weight-ai-model) (The Next Web, October 2026). It covers the open-weights timeline.
- Primary sources to check first: Anthropic's pricing and models pages at platform.claude.com/docs and mistral.ai/news (I could not open these today).

---
⏭️ **Tomorrow:** 💼 Use Cases. We look at how a real company puts AI to work and the architecture behind it.
