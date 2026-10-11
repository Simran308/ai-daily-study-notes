---
date: 2026-10-11
track: recap
topic: Weekly recap, the real cost of a task and the scaffolding around agents
slug: weekly-recap
tags: [recap, pricing, reasoning, small-models, agents, evals]
read_time: 10 min
---

# 📅 Weekly recap: price per token is not cost per task

> **TL;DR**
> - Cost per task is price per token × tokens used. This week two lessons showed the second factor can cancel a big drop in the first: reasoning effort on GPT-6.1 Sol and Claude Haiku 5.5's token appetite.
> - Match the model, the effort level and the request size to the job: cheap workers for small well-defined steps, a stronger model to plan, and a watch on the 100k-token price cliff.
> - Reliable agents come from boring scaffolding around the model: prefetched context, a few curated tools, a sandbox, and real tests as the judge. Your own small eval is what tells you whether any of it works.

## What it is

This recap covers 2026-10-05 to 2026-10-10 (the first week's foundations lessons from 10-03 and 10-04 are the background). Here is what we covered, one line each:

| Date | Lesson | One-line version |
|---|---|---|
| 10-05 | 🆕 GPT-6.1 Sol | OpenAI's mid-tier GPT-6 model (released 2026-09-29), priced at $2 / $10 per 1M input / output tokens. OpenAI says it nearly matches the flagship Astra on agentic work at a fifth of the price (vendor-reported). `reasoning.effort` is the cost dial. |
| 10-07 | 🛠️ Effort-vs-cost bench | A tiny eval that runs the same tasks at each effort level and records accuracy, reasoning tokens, dollars and latency, changing only one variable. |
| 10-08 | 🆕 Claude Haiku 5.5 | A small model at $0.10 / $0.50 per 1M tokens up to 100k tokens per request, and $0.50 / $2.50 above that. Great sub-agent material, but you need to watch the price cliff. |
| 10-09 | 💼 Stripe Minions | An unattended coding agent: Slack message in, pull request out. Prefetched context, about 15 curated tools out of 400+, a sandbox, and CI as the judge. |
| 10-10 | 🔁 Review | Eight spaced-repetition cards from the first week. |

## Why it matters

The three most important ideas of the week:

- **Cost per task is price × tokens, and tokens hide.** Reasoning tokens are billed as output tokens, which cost about 5x input here. Anthropic estimates about 75% savings over Haiku 4.5 even though per-token prices fell 90%, because the new model reportedly uses more tokens per task. Neither number tells you your cost. Only a run on your own workload does.
- **Right-size everything.** Effort level, model tier and request size are all dials. A cheap model does the many small steps, a stronger one plans, and splitting a job so each request stays under 100k tokens can avoid the pricier tier (assuming the task decomposes cleanly and the higher rate applies to the whole request).
- **The model is the small part of a reliable agent.** Stripe's pattern puts deterministic code around the model. Ordinary code gathers context before the model runs, the model sees only the relevant few tools, it works in a sandbox with no internet and no production data, and the real tests decide whether it is done. A capped retry loop then hands off to a human.

## How it works

The three ideas connect through measurement:

```
        your task set (fixed inputs, known answers)
                        │
        ┌───────────────┼────────────────┐
   model / tier     effort level     request size
  (Sol vs Haiku)  (low … max)     (under or over 100k)
        └───────────────┼────────────────┘
                        ▼
      accuracy, tokens used, $ per task, latency
                        ▼
        pick the cheapest setup that is good enough
                        ▼
   wrap it in scaffolding: prefetch → few tools → sandbox → tests decide
```

The effort benchmark from 10-07 is the measuring instrument. Stripe's pipeline is what you do with the result. Haiku-class workers inside a larger agent are where cheap tokens matter most, because most of an agent's tokens flow through those small calls.

## Try it

This is the weekend build: **a cost-per-correct-answer comparison**. Extend the 10-07 benchmark with a second arm for Haiku 5.5, and compute dollars per *correct* answer rather than dollars per call. The helper below runs offline. The token counts and accuracies are made-up placeholders, so replace them with numbers read from your own runs (`response.usage` in each API).

```python
# No pip install needed. Prices are from the 10-05 and 10-08 lessons; re-check them before use.

def sol_cost(inp, cached, out):
    # GPT-6.1 Sol: $2 in, $0.10 cached in, $10 out per 1M tokens
    return ((inp - cached) * 2.00 + cached * 0.10 + out * 10.00) / 1e6

def haiku_cost(inp, out):
    # Claude Haiku 5.5: the tier depends on request size (assumed to apply to the whole request)
    pin, pout = (0.50, 2.50) if inp > 100_000 else (0.10, 0.50)
    return (inp * pin + out * pout) / 1e6

# (cost per call, accuracy): placeholder numbers, replace with your measured ones
runs = {
    "sol-medium": (sol_cost(1500, 0, 2500), 0.90),
    "haiku-5.5": (haiku_cost(1500, 6000), 0.80),  # more output tokens per task
}

for name, (cost, acc) in runs.items():
    print(f"{name}: ${cost:.5f} per call, ${cost / acc:.5f} per correct answer")
```

With the placeholder numbers you should see roughly $0.031 per correct answer for Sol and $0.004 for Haiku. The real exercise is replacing them with measured values. Then add a third row where the Haiku request exceeds 100k input tokens and see how much the cliff changes the answer. Also check for `status="incomplete"` in your Sol runs so a low token cap doesn't make a correct model look wrong.

## Where it fits

Three ways to set up a model for a recurring task:

| | One strong model for everything | One mid-tier model, tune effort | Route: cheap by default, escalate |
|---|---|---|---|
| Best for | Hard, varied tasks where simplicity matters | Tasks of mixed difficulty on one model | High-volume work with many easy, well-defined steps |
| Cost / licence | Highest per-token prices | Pay for reasoning tokens only where you turn effort up | Lowest average, but you pay for the router's complexity |
| Watch out for | Overpaying on easy steps | Hidden reasoning tokens, and hitting output caps | Wrong routing; needs an eval to know the cheap model is good enough |

## Flashcards
- **Q:** Why can a 90% per-token price cut still give only about 75% savings per task?
  **A:** Cost per task is price per token × tokens used. If the new model consumes more tokens per task, or requests land in a pricier tier, the savings shrink. Measure on your own workload.
- **Q:** What is the cost-per-correct-answer metric, and why is it better than cost per call?
  **A:** Total cost divided by the number of correct answers. A cheap model that is wrong more often can cost more per correct result than it first appears, and a pricier one may cost less.
- **Q:** What do Stripe's Minions have in common with the effort benchmark?
  **A:** Both rely on an objective check outside the model (CI tests, or a known-answer eval) rather than trusting the model's own claim of success.
- **Q:** Name three dials that change what an LLM task costs.
  **A:** Model tier, reasoning effort, and request size (for example staying under Haiku 5.5's 100k-token tier boundary). Caching and output length also matter.
- **Q:** Where does the model sit in a reliable unattended agent?
  **A:** In the middle of deterministic scaffolding: context is prefetched by ordinary code, only a few relevant tools are shown, it runs in a sandbox, and tests decide when it is done, with a capped retry loop.

## Quiz
1. A team switches to a model with 90% lower per-token prices, and their bill falls by only 40%. What is the most likely first thing to check?
   - a) Whether the provider quietly raised prices
   - b) Tokens used per task, including reasoning tokens and the long-request tier
   - c) Whether the context window is too small
   <details><summary>Answer</summary>b. Cost per task is price × tokens. Models that think more or write more, or requests that cross a price tier, can eat most of a per-token discount.</details>
2. You are building the Haiku arm of a benchmark. Some inputs are 150k tokens. What should you do?
   - a) Ignore it, since the price is flat
   - b) Compute their cost at the higher tier, and consider splitting them into smaller requests (map) and combining results (reduce)
   - c) Switch to a reasoning model
   <details><summary>Answer</summary>b. Above 100k tokens the per-token rate is higher, so splitting can keep each request in the cheaper tier if the task decomposes cleanly.</details>
3. In a coding-agent loop, who decides that the work is finished?
   - a) The agent, when it says it is done
   - b) The real tests or CI, with the number of attempts capped
   - c) A second, larger model asked to approve
   <details><summary>Answer</summary>b. The agent's claim of success is not evidence. Objective checks decide, and a cap on attempts hands off to a human.</details>

## Go deeper
- [GPT-6.1 Sol lesson](2026-10-05-gpt-6-1-sol.md) (this course, 2026-10-05)
- [Claude Haiku 5.5 and the 100k-token price cliff](2026-10-08-claude-haiku-5-5.md) (this course, 2026-10-08)
- [How Stripe's Minions turn a Slack message into a pull request](2026-10-09-stripe-minions-unattended-coding-agents.md) (this course, 2026-10-09)

---
⏭️ **Tomorrow:** 🆕 Monday is New Models day, so expect a fresh release from the last two weeks that you can try the same day.
