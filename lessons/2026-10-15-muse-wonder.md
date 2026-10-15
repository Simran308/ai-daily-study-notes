---
date: 2026-10-15
track: new-models
topic: Meta Muse Wonder, a 1M-context agent model you can only rent
slug: muse-wonder
tags: [llm, meta, agents, pricing, closed-weights, long-context]
read_time: 15 min
---

# 🆕 Meta Muse Wonder, a 1M-context agent model you can only rent

> **TL;DR**
> - On 2026-10-12 Meta released **Muse Wonder** (`muse-wonder-1.0`). It has a 1,048,576-token context window and is priced at $4 / $20 per 1M input / output tokens. Meta's API labels it a preview.
> - There are two versions. The API gets the smaller one. The bigger **Muse Wonder Full** is only inside paid Muse Code plans, and neither version has downloadable weights.
> - It is 2x the per-token price of GPT-6.1 Sol and about 40x Claude Haiku 5.5's short-request price. Its selling points are long-running agent work and a flat price at any context length. Test it on your own tasks before you pay for it.

## What it is

Meta released Muse Wonder on 2026-10-12. Coverage describes it as Meta's most capable model so far, built for agent work: long tasks where the model plans, calls tools, delegates to sub-agents and recovers from its own errors. Input can be text, images, video, audio and PDFs. Output is text. Reasoning effort runs from "minimal" to "max", which is the same dial you met in the GPT-6.1 Sol lessons.

The naming is confusing, so here it is plainly:

- **Muse Wonder** (`muse-wonder-1.0`) is the one you can call. It is on the Meta Model API, on OpenRouter (slug `meta/muse-wonder`, per third-party coverage) and inside every Muse Code plan. The API still labels it a preview.
- **Muse Wonder Full** (`muse-wonder-full-1.0`) is the larger variant and scores higher on most benchmarks. It is only available in the Muse Code Power ($50/month) and Max ($200/month) plans. Setting standard Wonder to max effort does **not** switch you to Full.
- **Weights:** VentureBeat reports that neither model has publicly downloadable weights. This is not an open-weights release like the Mistral Large 4 weights promised for late October.

On benchmarks, one third-party page reports Meta's numbers on Artificial Analysis's Intelligence Index v4.3 as 52 for Wonder, 56 for Wonder Full and 58 for Claude Opus 5.5 *(vendor-reported, relayed by a third party, not independently checked)*. If that is accurate, Wonder is a strong second-tier model rather than the leader. Most of the headline benchmark numbers you will see online are for Full, which you can't call from code.

*Sourcing note:* I could not open Meta's own announcement or docs while researching. The facts below come from several secondary write-ups that agree with each other and quote Meta's model page. Anything I couldn't cross-check is marked *(unverified)*. Confirm prices on Meta's pricing page before budgeting.

## Why it matters

- **Long-running coding and ops agents.** Meta positions Wonder for multi-hour runs that plan, delegate and retry, the same shape as the Stripe Minions lesson.
- **Document-heavy work (legal, research).** A 1M-token window with no long-context surcharge lets you put a big contract set in one prompt. Check that quality holds up at that length on your own documents.
- **Multimodal intake.** One model accepts a screen recording, a PDF and an audio clip, so you don't need a separate transcription step. This is useful for support and QA tooling.

## How it works

Meta hasn't published an architecture for Wonder that I could find, so this section covers what you can observe and reason about. It is not a claim about the model's internals.

```
        planner (Wonder, high effort)
          |        |         |
   sub-agent   sub-agent  sub-agent     <- cheap model, e.g. Haiku-class
   (read repo) (run tests) (summarise)
          \        |        /
           memory / context (up to 1,048,576 tokens)
```

Three things change your design:

1. **Flat pricing over a huge window.** Meta lists no long-context premium. Claude Haiku 5.5 doubles its token rates past 100k tokens, so Wonder's cost is linear in tokens. Cost per call is still large when you actually fill the window.
2. **Caching matters a lot.** Cached input is $0.20 per 1M tokens, 5% of the normal $4. In a long agent loop most input is the same growing prefix, so a cache hit changes the bill far more than the headline price does.
3. **Effort is a dial, not a model switch.** Raising effort on Wonder spends more reasoning tokens, which are billed as output at $20 per 1M. Choosing Full is a plan upgrade, not an API parameter.

Other numbers from the coverage: the web search tool costs $2.50 per 1,000 queries, and the rate limit is listed as 3,000 requests and 4M tokens per minute *(unverified beyond one source)*. Wonder has no "contributor" discount tier, where cheaper tokens come in exchange for letting the vendor train on your data.

## Try it

Run this first without any key. It compares the three rate cards from this week's lessons on two workloads. If you set `OPENROUTER_API_KEY`, it also makes one real call and prices it from `usage`.

```python
# pip install openai
import os

RATES = {  # (input, output) in $ per 1M tokens, from each vendor's launch notes
    "muse-wonder-1.0": lambda n: (4.00, 20.00),                      # flat, no long-context premium
    "gpt-6.1-sol":     lambda n: (2.00, 10.00),
    "claude-haiku-5.5": lambda n: (0.10, 0.50) if n <= 100_000 else (0.50, 2.50),
}

def cost(model, tokens_in, tokens_out):
    p_in, p_out = RATES[model](tokens_in)
    return (tokens_in * p_in + tokens_out * p_out) / 1e6

for label, t_in, t_out in [("small agent turn", 80_000, 8_000),
                           ("big repo read", 400_000, 20_000)]:
    print(label, f"({t_in:,} in / {t_out:,} out, no caching)")
    for m in RATES:
        print(f"  {m:18s} ${cost(m, t_in, t_out):.3f}")

# Optional live call through OpenRouter (slug from third-party coverage, verify it)
if os.environ.get("OPENROUTER_API_KEY"):
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"])
    r = client.chat.completions.create(
        model="meta/muse-wonder",
        messages=[{"role": "user", "content": "In one sentence, what is a sub-agent?"}],
        max_tokens=2000)  # leave room: reasoning tokens count toward the cap
    u = r.usage
    print(r.choices[0].message.content)
    print("real usage:", u.prompt_tokens, "in,", u.completion_tokens, "out ->",
          f"${cost('muse-wonder-1.0', u.prompt_tokens, u.completion_tokens):.5f}")
```

Without a key you should see Wonder at $0.480 and $2.000, Sol at $0.240 and $1.000, and Haiku 5.5 at $0.012 and $0.250. The Haiku jump from $0.012 to $0.250 comes from the 100k-token tier. With a key you also get one sentence and a cost line. OpenRouter may charge a different rate than Meta's own API, so treat that line as an estimate. Prices are per-token, and different models count tokens differently, so compare on real `usage`, not on text length.

## Where it fits

| | Muse Wonder | GPT-6.1 Sol | Claude Haiku 5.5 |
|---|---|---|---|
| Best for | Long agent runs and huge single prompts, multimodal input | Near-flagship agentic work at a lower price | Cheap sub-agent steps and high-volume small tasks |
| Cost / licence | $4 / $20 per 1M, cached $0.20; closed weights; preview | $2 / $10 per 1M, cached $0.10; closed weights | $0.10 / $0.50 up to 100k tokens, then $0.50 / $2.50; closed weights |
| Watch out for | Costs more per token than Sol. Top version (Full) is not in the API. Preview status. | Doesn't support `none` or `minimal` effort values | Reportedly uses more tokens per task, so measure cost per task |

A reasonable pattern is to let a strong model plan and a Haiku-class model do the cheap steps. Wonder earns its price only if it finishes tasks that Sol can't, or in fewer retries. That is a cost-per-correct-answer question, which you already know how to measure.

## Flashcards

- **Q:** What are the two Muse Wonder variants, and which one can you call through the API?
  **A:** Muse Wonder (`muse-wonder-1.0`) is on the Meta Model API, OpenRouter and Muse Code. Muse Wonder Full (`muse-wonder-full-1.0`) is only in the Muse Code Power and Max plans. Max reasoning effort on standard Wonder does not select Full.
- **Q:** What are Muse Wonder's API price, context window and licence status?
  **A:** $4 per 1M input, $20 per 1M output and $0.20 per 1M cached input. The context window is 1,048,576 tokens with no long-context premium. Weights are not downloadable. Released 2026-10-12 and labelled a preview.
- **Q:** Why is cached input especially important for a model like Muse Wonder?
  **A:** Long agent loops resend a growing prefix, so most input tokens can be cache hits. At $0.20 versus $4 per 1M, a cache hit costs 5% of the normal input price.
- **Q:** How does Muse Wonder's pricing shape differ from Claude Haiku 5.5's?
  **A:** Wonder is flat at any context length. Haiku 5.5 charges $0.10 / $0.50 up to 100k tokens and $0.50 / $2.50 above that. Wonder costs more per token, but its cost grows in a straight line.
- **Q:** What kind of workload is Muse Wonder aimed at, and what should you do before adopting it?
  **A:** Long-running agent work where the model plans, delegates to sub-agents, calls tools and recovers from errors, plus large multimodal prompts. Benchmark it on your own tasks using cost per correct answer, because most headline scores are vendor-reported and several are for the Full variant.

## Quiz

1. You set `muse-wonder-1.0` to max reasoning effort. Which model are you now using?
   - a) Muse Wonder Full, because max effort unlocks it
   - b) Standard Muse Wonder, spending more reasoning tokens
   - c) A different model chosen automatically by the API
   <details><summary>Answer</summary>b. Effort changes how many reasoning tokens are spent. Full is a separate model that is only available in the Power and Max Muse Code plans.</details>

2. An agent loop resends 300k tokens of mostly unchanged context on every step. What lowers your Wonder bill most?
   - a) Switching from text to PDF input
   - b) Making sure the stable prefix is served from cache ($0.20 instead of $4 per 1M)
   - c) Asking for shorter answers only
   <details><summary>Answer</summary>b. In a long loop, input dominates, and cached input is 5% of the normal rate. Shorter answers help too, but they save less.</details>

3. A teammate says "Wonder is open, so we can self-host it." What is wrong with that?
   - a) Nothing, it is released under an open licence
   - b) Weights are only available for the Full version
   - c) Neither Wonder model has downloadable weights, so you can only use it through Meta's API, OpenRouter or Muse Code
   <details><summary>Answer</summary>c. VentureBeat reports no public weights for either model. Mistral Large 4 is the one with open weights promised for late October.</details>

## Go deeper
- [Meta's new Muse Wonder and Muse Wonder Full models achieve frontier performance, but only the weaker one is available via API](https://venturebeat.com/technology/metas-new-muse-wonder-and-muse-wonder-full-models-achieve-frontier-performance-but-only-the-weaker-one-is-available-via-api) (VentureBeat, 2026-10-13, accessed 2026-10-15)
- [Meta Muse Wonder: what it is, what it costs, and which version you get](https://www.eesel.ai/blog/meta-muse-wonder) (eesel.ai, accessed 2026-10-15)
- [Model Drop: Muse Wonder](https://handyai.substack.com/p/model-drop-muse-wonder) (Handy AI, accessed 2026-10-15)

---
⏭️ **Tomorrow:** 💼 Use Cases, how a real company puts an AI agent into production and what architecture sits behind it.
