---
date: 2026-10-14
track: build-it
topic: Build a ticket-triage eval with schema-enforced output and cost per correct answer
slug: ticket-triage-eval-bench
tags: [build-it, structured-outputs, evals, pricing, pydantic, claude-haiku-5-5]
read_time: 15 min
---

# 🛠️ Build a Ticket-Triage Eval: Schema-Enforced Output Plus Cost per Correct Answer

> **TL;DR**
> - You'll build a ~40-line script that classifies support tickets with a Pydantic schema, scores itself against known answers, and prints **cost per correct answer**.
> - It reuses two earlier lessons. Structured outputs (Oct 13) remove parsing failures, and the eval-and-cost mindset (Oct 7 and the weekly recap) turns "seems fine" into numbers.
> - The harness counts three outcomes separately: correct, wrong, and failed (truncated or refused). Only the second one is a judgement error.

## What it is

Today is a build day, so there is no new concept. You'll glue two things you already know into one reusable tool.

On Oct 13 you learned that a JSON schema guarantees the output *parses* and has the right fields and types, but not that the *values* are right. On Oct 7 you built a benchmark that varied one setting and measured accuracy, tokens and cost. This lesson combines them into a small harness for a realistic job: triaging support tickets into a category and a priority.

The model is **Claude Haiku 5.5** (`claude-haiku-5-5`). Anthropic released it on 2026-10-07. Its price is $0.10 per 1M input tokens and $0.50 per 1M output tokens for requests up to 100,000 tokens, and $0.50 / $2.50 above that. Anthropic positions it for high-volume work such as classification, extraction and routing, which is exactly what we're doing. The script takes the model name and prices from environment variables, so you can rerun it on any other model.

Two Haiku 5.5 details matter here:

- **Thinking is adaptive and on by default.** Anthropic's migration guide says responses can begin with thinking blocks even if you don't ask. Thinking tokens count toward the output limit and are billed as output, so `max_tokens` has to leave room for them.
- **Old thinking settings now fail.** Code that sends `thinking: {"type": "enabled", "budget_tokens": N}` (the Haiku 4.5 style) returns a 400 error. We don't set `thinking` at all, so we're fine, but remember this if you port old code.

## Why it matters

- **Support desks** (Zendesk-style queues) route tickets by category and urgency before a human sees them. A wrong "low" on a double-charge is a real cost.
- **Classification in any pipeline**, such as email routing, content moderation or lead scoring, has the same shape: fixed labels in, one label out, high volume.
- **Model migrations.** When a cheaper model ships, a 6-line eval tells you in minutes whether to switch, instead of in production a week later.

## How it works

```
 ticket text ──► messages.parse(schema=Triage) ──► Triage(category, priority)
                        │                                   │
                        ▼                                   ▼
                 response.usage                     compare with gold label
              (input/output tokens)                 ok / BAD / FAILED
                        │                                   │
                        └────────► cost += tokens × price ◄─┘
                                          │
                                          ▼
                       total cost ÷ number correct = cost per correct answer
```

Three design choices carry most of the value:

1. **A `Literal` schema with an escape hatch.** `category` can only be one of four values, including `"other"`. That's the "not found" rule from the prompting lesson in schema form: the model is never forced to pick a wrong label. The SDK turns the Pydantic class into a JSON schema, sends it as `output_config.format`, validates the response and hands you a typed object in `parsed_output`.
2. **No `reasoning` field in the schema.** Last lesson suggested putting a reasoning field before the answer so the model can think first. Haiku 5.5 already thinks adaptively, so a reasoning field would make you pay for the thinking twice. With a non-thinking model, add it back.
3. **Three outcomes, not two.** A request can end *correct*, *wrong*, or *failed* (an exception because the output was truncated at `max_tokens` or refused). Mixing "failed" into "wrong" hides a config problem, such as a too-small `max_tokens`, behind what looks like a model-quality problem. This is the same lesson as the `incomplete` status in the Oct 7 benchmark.

**Cost per correct answer** is total cost divided by correct answers. It's the metric from the weekly recap: a cheap model that gets more wrong, or fails more often, can cost more per *useful* result than its price suggests.

## Try it

```python
# pip install anthropic pydantic   (export ANTHROPIC_API_KEY=...)
import os, anthropic
from typing import Literal
from pydantic import BaseModel

MODEL = os.getenv("MODEL", "claude-haiku-5-5")
PRICE_IN = float(os.getenv("PRICE_IN", "0.10"))    # $ per 1M input tokens
PRICE_OUT = float(os.getenv("PRICE_OUT", "0.50"))  # $ per 1M output tokens

class Triage(BaseModel):
    category: Literal["billing", "bug", "feature_request", "other"]
    priority: Literal["low", "medium", "high"]

SYSTEM = ("Triage the support ticket inside <ticket>. priority=high only if money is "
          "wrong or the user is blocked. Use category 'other' if nothing fits.")
CASES = [  # (ticket, expected category, expected priority)
    ("I was charged twice for October.", "billing", "high"),
    ("The export button does nothing, so I can't send my report.", "bug", "high"),
    ("Please add dark mode.", "feature_request", "low"),
    ("The PDF footer is 2px off-centre.", "bug", "low"),
    ("Can you send me last year's invoice?", "billing", "low"),
    ("Do you have a referral programme?", "other", "low"),
]

client = anthropic.Anthropic()
cost, correct, failed = 0.0, 0, 0
for text, want_cat, want_pri in CASES:
    try:
        r = client.messages.parse(model=MODEL, max_tokens=4000, system=SYSTEM,
            messages=[{"role": "user", "content": f"<ticket>{text}</ticket>"}],
            output_format=Triage)
    except Exception as e:  # truncated or refused: count it, don't hide it
        print("FAILED:", text, type(e).__name__); failed += 1; continue
    cost += (r.usage.input_tokens * PRICE_IN + r.usage.output_tokens * PRICE_OUT) / 1e6
    got = r.parsed_output
    ok = (got.category, got.priority) == (want_cat, want_pri)
    correct += ok
    print("ok " if ok else "BAD", got.category, got.priority, "|", text)
print(f"{MODEL}: {correct}/{len(CASES)} correct, {failed} failed, ${cost:.5f} total")
if correct: print(f"cost per correct answer: ${cost / correct:.5f}")
```

You should see one `ok` or `BAD` line per ticket, then a summary line with the correct count, the failure count and a total cost of a fraction of a cent. The exact numbers will differ per run and per model. I checked the scoring and cost arithmetic offline against a mocked client. I did not run it against the live API, so if a call fails, check the SDK version and the error message first.

**Back-of-envelope cost (my assumptions, not measurements):** if each call used about 300 input and 500 output tokens (thinking included), one call costs 300 × $0.10/1M + 500 × $0.50/1M ≈ $0.00028. Ten thousand tickets would then be about $2.80. The same token counts at $2 / $10 would be about $56, so measure real token counts rather than trusting this estimate.

**Extend it (pick one):**
1. Replace the six cases with 20–30 real, anonymised tickets. Six cases show the mechanics but prove little statistically.
2. Rerun with `MODEL=<another model id> PRICE_IN=... PRICE_OUT=...` and compare cost per correct answer. Take both values from the provider's pricing page.
3. Add a business rule in code, for example "billing tickets can never be `low` if they mention 'charged'", and count violations separately. A schema can't express that rule.

## Where it fits

| | This harness (Haiku 5.5 + schema) | Same idea on GPT-6.1 Sol | Prompt-and-parse (no schema) |
|---|---|---|---|
| Best for | High-volume classification and extraction at the lowest price | Harder judgement calls where a mid-tier model is worth paying for | Quick throwaway scripts |
| Cost / licence | $0.10 / $0.50 per 1M tokens (≤100k prompts), proprietary API | $2 / $10 per 1M tokens, $0.10 cached input, proprietary API | Same token price, plus retries when parsing breaks |
| API shape | `client.messages.parse(..., output_format=Model)` → `parsed_output` | `client.responses.parse(..., text_format=Model)` → `output_parsed` | `json.loads` on free text |
| Watch out for | Thinking tokens bill as output, so a low `max_tokens` causes failures. The same text also counts as roughly 30% more tokens than on older Claude tokenizers (reported). | Prompts over 272K input tokens are billed at higher rates for the whole request. Tools require the Responses API. | Parse failures get mixed into accuracy numbers |

Third-party sources list Claude Sonnet 5.5 at $2 / $10 per 1M tokens. I did not confirm its model ID against Anthropic's docs *(unverified)*, so look it up before using it in `MODEL`. Likewise, one third-party source lists structured outputs as supported on Haiku 5.5, while Anthropic's own structured-outputs page I checked was written for earlier models, so confirm on the current docs if your call is rejected.

## Flashcards
- **Q:** Why does a schema-enforced eval measure model quality more cleanly than a prompt-and-parse eval?
  **A:** The schema guarantees every response parses and uses valid labels, so mistakes you see are wrong judgements, not formatting failures mixed into the score.
- **Q:** Why should an eval count "failed" calls separately from "wrong" answers?
  **A:** Failures (truncation at `max_tokens`, refusals, exceptions) are usually config problems, while wrong answers are model-quality problems. Merging them hides which one to fix.
- **Q:** What is cost per correct answer, and how is it computed in the harness?
  **A:** Total cost divided by the number of correct answers. Cost is summed per call as (input_tokens × input price + output_tokens × output price) / 1M, using `response.usage`.
- **Q:** On Claude Haiku 5.5, why must `max_tokens` leave room beyond the visible JSON?
  **A:** Thinking is adaptive and on by default, and thinking tokens count toward the output limit and are billed as output. A low cap can truncate the response and make the call fail.
- **Q:** What are the Python SDK entry points that return a typed object from a Pydantic model for Claude and for OpenAI's Responses API?
  **A:** Claude: `client.messages.parse(..., output_format=Model)` and read `parsed_output`. OpenAI: `client.responses.parse(..., text_format=Model)` and read `output_parsed`.

## Quiz
1. Your eval shows 4/6 correct and 2 failed on a Haiku 5.5 run with `max_tokens=200`. What should you do first?
   - a) Conclude the model is bad at classification and switch models
   - b) Raise `max_tokens` and rerun, because thinking tokens count toward the cap and may be truncating output
   - c) Remove the schema so the model can answer freely
   <details><summary>Answer</summary>b. Thinking is on by default and shares the output budget, so a tiny cap can cause failures that aren't judgement errors. Fix the config, then compare models.</details>
2. Model A costs $0.002 total and gets 4 of 6 right. Model B costs $0.009 and gets 6 of 6 right. Which statement is correct?
   - a) A is cheaper per correct answer ($0.0005 vs $0.0015)
   - b) B is cheaper per correct answer because it is more accurate
   - c) You can't compare them without more information
   <details><summary>Answer</summary>a. A: $0.002 / 4 = $0.0005 per correct answer. B: $0.009 / 6 = $0.0015. Whether A's two errors are acceptable is a separate business question, and six cases is too few to be confident either way.</details>
3. Which requirement can your Pydantic schema NOT enforce in this harness?
   - a) `priority` is one of low, medium, high
   - b) The output has exactly the fields `category` and `priority`
   - c) A ticket mentioning "charged twice" is never marked low priority
   <details><summary>Answer</summary>c. A schema guarantees structure and allowed values, not business rules about what the values should be for a given input. Check those in code or with eval cases.</details>

## Go deeper
- [Structured outputs, Claude Platform Docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) (Anthropic, accessed 2026-10-14)
- [Claude Haiku 5.5 migration guide](https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide) (Anthropic, accessed 2026-10-14)
- [Structured model outputs, OpenAI API docs](https://platform.openai.com/docs/guides/structured-outputs) (OpenAI, accessed 2026-10-14)

---
⏭️ **Tomorrow:** 🆕 New Models, a recent release you can try today. Thursday is also a good day to rerun this harness on whatever ships.
