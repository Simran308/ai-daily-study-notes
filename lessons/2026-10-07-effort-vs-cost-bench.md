---
date: 2026-10-07
track: build-it
topic: Build an effort-vs-cost benchmark for GPT-6.1 Sol
slug: effort-vs-cost-bench
tags: [build-it, evals, reasoning, pricing, prompting, responses-api, gpt-6-1-sol]
read_time: 15 min
---

# 🛠️ Build It: An "Effort vs Cost" Benchmark for a Ticket Classifier

> **TL;DR**
> - Reasoning effort is a cost dial. The only way to pick a setting is to measure accuracy, tokens, dollars and latency on your own examples.
> - A 40-line script can do this. It combines Saturday's token and cost maths, Sunday's prompt structure (system prompt, XML tags, few-shot examples, an "other" exit) and Monday's `reasoning.effort` parameter.
> - The reasoning-token count is in `usage.output_tokens_details.reasoning_tokens`. It is billed as output, which makes it the line item that moves your bill.

## What it is

This is a mini-project, not a new product. You will build a small harness that sends the same eight labelled support tickets to `gpt-6.1-sol` at three reasoning efforts (`low`, `medium`, `high`). For each effort it prints:

- accuracy
- reasoning tokens used
- dollars spent
- wall-clock time

It reuses three things from the past few days:

1. **Cost maths (Oct 3).** `cost = fresh_input × input_price + cached_input × cached_price + output × output_price`, all per 1M tokens. Reasoning tokens count as output.
2. **Prompt structure (Oct 4).** The system prompt holds the stable rules. The per-request ticket goes in the input, wrapped in XML tags. There are three varied few-shot examples, including a "none of the above" case.
3. **GPT-6.1 Sol (Oct 5).** The model ID is `gpt-6.1-sol`. It is called through the Responses API. Its `reasoning.effort` accepts `low`, `medium` (the default), `high`, `xhigh` and `max`. `none` and `minimal` are not supported.

The outcome is a decision rule you can defend. For example: "`low` gets 8/8 on our tickets at a fraction of the cost, so we ship `low`." The alternative is picking `high` because it feels safer.

This is also a first, tiny version of an **eval**: a fixed set of inputs with known right answers that you re-run whenever you change the model, the prompt or a setting. We'll cover evals properly later in the Tech Stack track. Building a toy one now will make that lesson easier.

## Why it matters

- **Model migrations.** The Sol docs tell you to map old `none`/`minimal` effort settings to `low` and re-test. This harness is the re-test.
- **Support and ops triage.** Routing tickets, emails or alerts is a high-volume job where a small per-call saving multiplies across millions of calls.
- **Budget reviews.** "Why did our LLM bill double?" is easier to answer when each feature has a measured cost per call and a measured effort setting.

## How it works

```
 tickets + gold labels                 one API call per ticket
 ┌──────────────────┐   ┌───────────────────────────────────────────┐
 │ "billed $49..."  │──►│ instructions = SYSTEM (rules + examples)  │
 │  → billing       │   │ input = <ticket>…</ticket>                │
 └──────────────────┘   │ reasoning.effort = low | medium | high    │
                        └───────────────┬───────────────────────────┘
                                        ▼
                        response.output_text  → compare with gold
                        response.usage        → tokens → dollars
                                  ├ input_tokens (− cached_tokens)
                                  └ output_tokens (incl. reasoning_tokens)
```

Four details make the harness trustworthy:

**1. Read `usage`, don't estimate.** A Responses API result carries a `usage` object. `input_tokens_details.cached_tokens` tells you how many input tokens were billed at the cached rate. `output_tokens_details.reasoning_tokens` tells you how many output tokens were spent thinking. The script uses these fields, so the cost it prints is what you were billed. It is not a guess.

**2. Reasoning tokens eat your output budget.** `max_output_tokens` caps visible output *and* reasoning. If the model hits it, the response comes back with `status="incomplete"` and `incomplete_details.reason="max_output_tokens"`, and there may be no text at all. A tight cap on a high-effort run can therefore look like a wrong answer. We set 4000, which is generous for a one-word label. In a real harness you would also count incomplete responses separately.

**3. Grade mechanically.** Because the system prompt demands `<label>name</label>`, grading is a string check, `"<label>bug</label>" in r.output_text`. No second LLM is needed. Asking for output in tags you can parse is one of the main payoffs of Sunday's prompt structure.

**4. Keep the prompt identical across efforts.** Only `reasoning.effort` changes. If you changed anything else, you wouldn't know which change caused the difference.

One caution about the numbers. Eight tickets is a **demo**, not evidence. A 7/8 vs 8/8 difference on eight examples is noise. Treat the script as a harness, then swap in 50–200 of your own real, labelled tickets.

## Try it

```python
# pip install openai   (needs OPENAI_API_KEY in your environment)
import time
from openai import OpenAI

client, MODEL = OpenAI(), "gpt-6.1-sol"
PRICE_IN, PRICE_CACHED, PRICE_OUT = 2.00, 0.10, 10.00  # $ per 1M tokens

SYSTEM = """You classify support tickets into exactly one label:
billing, bug, how_to, other. Use other if none fits.
Reply with only <label>name</label>.
<example><ticket>I was charged twice this month</ticket><label>billing</label></example>
<example><ticket>Export button throws a 500 error</ticket><label>bug</label></example>
<example><ticket>Do you ship to Canada?</ticket><label>other</label></example>"""

TICKETS = [
    ("I was billed $49 but my plan is $29", "billing"), ("App crashes when I upload a PNG over 10 MB", "bug"),
    ("How do I add a teammate to my workspace?", "how_to"), ("Are you hiring backend engineers?", "other"),
    ("Dark mode resets every time I reopen the app", "bug"), ("Can I change the language of the dashboard?", "how_to"),
    ("Refund me, the charge on 3 Oct was a mistake", "billing"), ("What's the weather like in Berlin?", "other"),
]

def cost(u):
    cached = u.input_tokens_details.cached_tokens
    return ((u.input_tokens - cached) * PRICE_IN + cached * PRICE_CACHED
            + u.output_tokens * PRICE_OUT) / 1e6

for effort in ["low", "medium", "high"]:
    hits = spent = thinking = 0
    start = time.time()
    for text, gold in TICKETS:
        r = client.responses.create(
            model=MODEL, instructions=SYSTEM, input=f"<ticket>{text}</ticket>",
            reasoning={"effort": effort}, max_output_tokens=4000)
        hits += f"<label>{gold}</label>" in r.output_text
        spent += cost(r.usage)
        thinking += r.usage.output_tokens_details.reasoning_tokens
    print(f"{effort:6} acc {hits}/{len(TICKETS)}  reasoning_tokens {thinking:5}  "
          f"cost ${spent:.4f}  time {time.time() - start:.1f}s")
```

You should see three lines, one per effort, in this shape: `low    acc N/8  reasoning_tokens …  cost $…  time …s`. Expect reasoning tokens, cost and time to rise from `low` to `high`. Whether accuracy rises too is the thing you are testing. The run should cost a few cents in total, but the exact figure depends on how much the model thinks. I haven't run this against the live API for this lesson, so I'm not quoting results.

**Stretch ideas (30 minutes each):**
- Add `"xhigh"` to the list, and see whether you pay more for the same accuracy.
- Replace the eight tickets with 50 real ones from your own inbox or logs. Add a few that are genuinely ambiguous.
- Print `r.status` and count any `incomplete` responses.
- Prices are hard-coded from Monday's lesson ($2 input, $0.10 cached input, $10 output per 1M tokens). Re-check OpenAI's pricing page before relying on them. The script ignores any separate cache-write charge.

## Where it fits

| | This harness | Eyeballing a few prompts | A full eval framework |
|---|---|---|---|
| Best for | Choosing one setting (effort, model, prompt) with numbers | Quick sanity check while prototyping | Many test sets, graders, dashboards, CI gates |
| Cost / effort | ~40 lines, a few cents per run | Free, minutes | Setup time, plus often a hosted tool |
| Watch out for | Tiny test sets give noisy results; grading must be mechanical | Remembers the wins and forgets the misses; no cost figures | Overkill for a one-off decision |

## Flashcards

- **Q:** In the Responses API, where do you read how many tokens the model spent on reasoning?
  **A:** `response.usage.output_tokens_details.reasoning_tokens`. Those tokens are part of `output_tokens` and are billed at the output rate.
- **Q:** How do you compute the dollar cost of one call from `usage` when some input was cached?
  **A:** `((input_tokens − cached_tokens) × input_price + cached_tokens × cached_price + output_tokens × output_price) / 1M`, where `cached_tokens` comes from `usage.input_tokens_details`.
- **Q:** What happens if a reasoning model hits `max_output_tokens`, and why does it matter for evals?
  **A:** The response has `status="incomplete"` with `incomplete_details.reason="max_output_tokens"`. Reasoning tokens count toward the cap, so a low cap can leave you with little or no visible text. That makes a correct model look wrong.
- **Q:** What is a minimal LLM eval?
  **A:** A fixed set of inputs with known right answers, graded mechanically (for example by parsing a tagged label), re-run whenever the model, prompt or settings change.
- **Q:** Why change only `reasoning.effort` between runs in an effort benchmark?
  **A:** So any difference in accuracy, tokens, cost or latency can be attributed to the one variable you changed.

## Quiz

1. Your benchmark shows `low` and `high` both score 8/8 on your 8 tickets, and `high` costs about 4× more. What's the best conclusion?
   - a) Ship `low`; effort doesn't matter for this task.
   - b) Treat `low` as the leading candidate, then confirm on a larger, harder set of real tickets before shipping.
   - c) Ship `high`; a higher setting is always safer.
   <details><summary>Answer</summary>b. Eight easy tickets can't show that effort "doesn't matter". They only show that you haven't found a difference yet. Use the cheaper setting as the candidate and test it on more, and harder, data. (c) pays for thinking you haven't shown you need.</details>

2. A high-effort run returns an empty `output_text` and `status="incomplete"`. What is the most likely cause?
   - a) The model refused to answer.
   - b) `max_output_tokens` was too low, so reasoning tokens used up the budget before any visible text.
   - c) Prompt caching failed.
   <details><summary>Answer</summary>b. Reasoning tokens count toward `max_output_tokens`. Check `incomplete_details.reason` and raise the cap.</details>

3. Why does the script read `r.usage` instead of estimating tokens with the "1 token ≈ 4 characters" rule?
   - a) Reasoning tokens are invisible in the text, so character counts can't see them.
   - b) The rule only works for Python code.
   - c) `usage` is free, but estimates cost money.
   <details><summary>Answer</summary>a. Reasoning never appears in the output text, so you can only learn how much of it you were billed for from the `usage` fields.</details>

## Go deeper
- [Reasoning models guide](https://developers.openai.com/api/docs/guides/reasoning) (OpenAI developer docs, accessed 2026-10-07): effort levels, the `usage` fields for reasoning tokens, and how `max_output_tokens` interacts with reasoning.
- [GPT-6.1 Sol model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol) (OpenAI developer docs, accessed 2026-10-07): supported efforts, the Responses-API-for-tools note, and the model's specs.
- [Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) (OpenAI developer docs, accessed 2026-10-07): how `cached_tokens` is reported and how to track your cache-hit rate. This is useful once your system prompt grows.

---
⏭️ **Tomorrow:** 🆕 New Models. We look at another recent release you can try, or a three-item "this week in AI" round-up.
