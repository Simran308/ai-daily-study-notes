---
date: 2026-10-25
track: recap
topic: Weekly recap, your code runs the loop and your own numbers decide
slug: weekly-recap
tags: [recap, tool-use, pricing, caching, evals, agents, open-weights]
read_time: 10 min
---

# 📅 Weekly recap: your code runs the loop, and your own numbers decide

> **TL;DR**
> - The model only *proposes* actions. Your code executes them, enforces the rules, caps the loop and checks the result.
> - A price is a shape, not one number. Cache hits, peak hours and thinking tokens change a bill more than the headline rate does.
> - Vendor tables and case studies are leads. Your own eval, with "model alone" and "model plus code rules" scored separately, is the evidence.

## What it is

This week (2026-10-19 to 2026-10-25) had four lessons. Nothing was logged for the 21st or 22nd, so this recap covers only what's in your log.

- **Mon 10-19, 🆕 DeepSeek V4.1 Flash 1017.** It's an MIT-licensed 552B Mixture-of-Experts model with a 1M-token context, released 2026-10-17. Its API price depends on cache hit vs miss, peak vs off-peak and thinking on vs off.
- **Tue 10-20, 🧱 Tool use and function calling.** The model emits a tool name plus JSON arguments, your code runs the tool, and you send the result back in a loop. That loop sits behind every agent.
- **Fri 10-23, 💼 Eval-first agents.** Write the test cases first and score the model alone and the model plus code rules separately. Track missed escalations apart from overall accuracy. The Numan architecture itself was *not* verified: only that LangChain's blog listed the post.
- **Sat 10-24, 🔁 Review.** Eight cards from weeks one to three.

## Why it matters

The three most important ideas of the week:

- **1. The model proposes and your code disposes.** In the tool loop, your code is the one that executes anything. That makes it the natural place for the safety rules:
  - A turn cap stops a confused model from looping and billing you forever.
  - Business rules live in code, not in the prompt.
  - Failures go back as `is_error` tool results the model can react to.
- **2. Price is a shape.** On DeepSeek's off-peak rates, a cache hit costs about 1/50 of a miss ($0.003 vs $0.15 per 1M input tokens). Peak is double. Thinking changes output tokens. Put the stable prefix (system prompt, tool definitions, reference documents) first so it can be cached.
- **3. Measure it yourself.**
  - DeepSeek's own benchmark table shows a competitor ahead on some rows, which is a reminder that these tables are chosen by the vendor.
  - The eval-first pattern gives you a way to check a claim on your own tasks.
  - Splitting "model alone" from "model plus rules" tells you how much your safety net is rescuing.

## How it works

The three lessons are one system:

```
                 ┌─────────── eval set (inputs + required behaviour) ───────────┐
                 │                                                              │
user ─▶ [stable prefix: system + tools + docs]  ◀── cached, cheap (idea 2)     │
                 │                                                              │
                 ▼                                                              │
             MODEL proposes tool call ─▶ CODE gateway: rules, permissions,      │
                 ▲                          turn cap, executes (idea 1)         │
                 └──── tool_result / is_error ◀─┘                               │
                 │                                                              │
                 ▼                                                              ▼
            final outcome ───────────────▶ scored: cost per correct answer (idea 3)
```

The link between the tool loop and caching is that every turn resends the whole conversation so far. Input tokens grow with each turn, so the first part of the prompt is read again and again, and that is exactly the part caching discounts. The link between the loop and evals is that the loop's final outcome is the thing you score. It's also where the code rules do their rescuing.

## Try it

**Suggested weekend build (about 1 hour):** a refund agent with a code guard, then a tiny eval around it.

1. Run the script below. It's a tool loop with a turn cap and a gateway rule in code. It also sums `usage` across turns, so you can watch input tokens grow.
2. Add 8–10 test requests with known right outcomes: small refunds that should pass, big ones that should be denied, and a paraphrased "send my money back, it's $450" case.
3. Score each run twice. The first score covers what the model *tried* to do. The second covers the *final outcome* after the gateway. Count failed calls separately from wrong answers.
4. Compute cost per correct answer from the summed tokens. If you can, run it once with a stable prefix first and once with a shuffled one to see what caching does.

```python
# pip install anthropic   |   export ANTHROPIC_API_KEY=... MODEL=<a current Claude model ID from the docs>
import os, anthropic
client = anthropic.Anthropic()
MODEL = os.environ["MODEL"]
MAX_TURNS = 6
TOOLS = [{"name": "refund", "description": "Refund an order; amount in dollars.",
          "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"},
          "amount": {"type": "number"}}, "required": ["order_id", "amount"]}}]

def run_tool(name, args):
    if name == "refund" and args["amount"] > 100:
        return "DENIED: refunds over $100 need a human. Escalate.", True
    if name == "refund":
        return f"Refunded ${args['amount']} on {args['order_id']}", False
    return f"Unknown tool {name}", True

def agent(question):
    messages = [{"role": "user", "content": question}]
    in_tok = out_tok = 0
    for turn in range(1, MAX_TURNS + 1):
        r = client.messages.create(model=MODEL, max_tokens=2000, tools=TOOLS, messages=messages)
        in_tok += r.usage.input_tokens; out_tok += r.usage.output_tokens
        if r.stop_reason != "tool_use":
            text = "".join(b.text for b in r.content if b.type == "text")
            return text, turn, in_tok, out_tok
        messages.append({"role": "assistant", "content": r.content})
        results = []
        for b in r.content:
            if b.type == "tool_use":
                out, err = run_tool(b.name, b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, "is_error": err})
        messages.append({"role": "user", "content": results})
    return "STOPPED: max turns", MAX_TURNS, in_tok, out_tok

for q in ["Refund $40 on order A1.", "Refund $450 on order B2, I'm very upset."]:
    print(agent(q))
```

Each line printed is a tuple: the final reply text, the number of turns used, and the total input and output tokens. The $450 request should be denied by your code even if the model tries the refund.

## Where it fits

| | Prompt-only rules | Code rules (gateway) | Code rules + eval |
|---|---|---|---|
| Best for | Tone, format, soft preferences | Money, permissions, safety limits | Anything you plan to ship |
| Cost / effort | Free | A few lines of code | A test set and a scoring script |
| Watch out for | The model can ignore or misread them | Keywords miss paraphrases | The test set must include paraphrases and edge cases |

## Flashcards
- **Q:** What are the three ideas of the week of 2026-10-19, in one line each?
  **A:** (1) The model proposes and your code executes and enforces. (2) Price is a shape: cache, peak and thinking change the bill. (3) Measure on your own eval, not on vendor tables.
- **Q:** Why does the input-token count grow on every turn of a tool-use loop, and how does that connect to caching?
  **A:** Each turn resends the whole conversation so far plus the new tool results. The stable early part is read repeatedly, so a cache-friendly prefix (stable content first) makes those repeated reads much cheaper.
- **Q:** Why is a turn cap a cost control as well as a safety control?
  **A:** Each extra turn is another paid call with a larger input. Without a cap, a confused model can loop and bill you indefinitely. After the cap, return a clear "stopped" result and hand off to a human.
- **Q:** What should you record per eval case when an agent has a code gateway?
  **A:** What the model tried to do, the final outcome after the gateway, and whether the call failed (truncation, refusal, exception). Failures are config problems, not wrong answers, and the gap between the first two shows what the code rules rescued.
- **Q:** What are DeepSeek V4.1 Flash's three price factors, and what are the off-peak input prices?
  **A:** Cache hit vs miss, peak vs off-peak, and thinking on vs off. Off-peak input is $0.15 per 1M on a miss and $0.003 on a hit. Peak is double.

## Quiz
1. Your agent's refund tool is denied by a gateway rule, and you return `is_error: true` with a clear message. What should the model do next?
   - a) Crash the loop
   - b) Read the error and explain or escalate to a human
   - c) Retry the same call until it succeeds
   <details><summary>Answer</summary>b. A clear error as the tool result lets the model respond sensibly. Blind retries just burn turns and money, which is what the turn cap is for.</details>
2. You want cheap cache hits on a long agent run. Which prompt layout is best?
   - a) Per-request question first, then the system prompt and tool definitions
   - b) System prompt, tool definitions and reference docs first, then the changing part last
   - c) Random order, because caching is automatic
   <details><summary>Answer</summary>b. Caching reuses a repeated prefix, so anything that changes early invalidates what follows it.</details>
3. A vendor's table says Model X beats Model Y on five benchmarks. What's the best next step?
   - a) Switch now
   - b) Run your own test set and compare cost per correct answer
   - c) Ignore the table completely, because it's always wrong
   <details><summary>Answer</summary>b. The numbers are vendor-reported on chosen benchmarks, so they're a lead rather than proof. They're also not worthless, so test them on your own tasks.</details>

## Go deeper
- [DeepSeek V4.1 Flash 1017 lesson](2026-10-19-deepseek-v4-1-flash-1017.md) (this course, 2026-10-19)
- [Tool use and function calling, the loop behind every agent](2026-10-20-tool-use-function-calling-loop.md) (this course, 2026-10-20)
- [Eval-first agents, how to read a health-coach case study](2026-10-23-eval-first-health-coach-pattern.md) (this course, 2026-10-23)

---
⏭️ **Tomorrow:** 🆕 New Models. Mistral Large 4 had open weights promised for late October, so we'll check whether they've landed before deciding what to cover.
