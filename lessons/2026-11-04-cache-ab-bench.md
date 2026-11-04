---
date: 2026-11-04
track: build-it
topic: Build a cache A/B benchmark for Claude Haiku 5.5 that reads its own bill
slug: cache-ab-bench
tags: [build-it, caching, pricing, evals, claude-haiku-5-5, usage]
read_time: 15 min
---

# 🛠️ Build a cache A/B benchmark: prove prompt caching saves money on your own prompt

> **TL;DR**
> - Yesterday's lesson said caching cuts the price of repeated input. Today you measure it: run the same 6 questions against one long prompt with caching off, then on, and compute the cost from `response.usage`.
> - Put the cache breakpoint on the stable block (the long system prompt), not on the last message. The last message changes on every call, so a breakpoint there never gets reused.
> - `input_tokens` is only the uncached remainder. Real input is `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`. If you forget this, your cost maths will be wrong.

## What it is

This is a build lesson. There is no new model today. You will write a small script (about 30 lines) that settles a question you can't answer by reading docs: **does caching save money on my prompt, and how much?**

The setup is a support bot with a long, fixed policy sheet in the system prompt and a short, different customer question each call. That is the most common shape for caching. The script runs it twice on `claude-haiku-5-5` (released 2026-10-07):

1. **Cache off.** Every call pays full input price for the policy sheet.
2. **Cache on.** The policy sheet is marked with `cache_control`. Call 1 writes it to the cache, and calls 2–6 read it.

It sums the dollar cost of each run from the `usage` object the API returns. You are measuring your own bill, not trusting a vendor's headline percentage.

Two facts from the Haiku 5.5 docs shape the design. The minimum cacheable prompt is **512 tokens** (down from 4,096 on Haiku 4.5). A prompt shorter than that is processed without caching and no error is returned, so a tiny test prompt would silently show no savings. Also, the same text counts as more tokens than on Haiku 4.5, so recount before you assume a prompt is big enough.

## Why it matters

- **Support and FAQ bots:** a long policy or knowledge sheet followed by short questions is nearly all repeated input.
- **Coding and agent loops:** each turn resends tool definitions and the growing history, so most input tokens are repeats (see the tool-use lesson of 2026-10-20).
- **Document Q&A:** one contract or report is asked about many times. The first question pays a write, and the rest pay about a tenth.

## How it works

Caching matches a **prefix**. The prompt is processed in order (tools, then system, then messages), and the cache covers everything up to the block carrying `cache_control`. So where you put the breakpoint decides what can be reused.

```
Request 1:  [ policy sheet (3k tokens) ]* [ question A ]   -> writes the policy to cache
Request 2:  [ policy sheet (3k tokens) ]* [ question B ]   -> reads it from cache
                                       ^ breakpoint here, on the stable part
```

If you put the breakpoint on the last block instead, the cached prefix would include question A. Request 2 has question B, so that prefix no longer matches. The Claude docs say to place `cache_control` on the last block whose prefix is identical across the requests you want to share a cache. In this workload, that block is the system prompt.

The docs also offer "automatic caching": a top-level `cache_control` on the request. The docs describe it as the simplest start and say it works well in growing conversations, where the final block stays identical on the next turn. For a fixed prefix plus a changing question, I expect it to have the same problem as a breakpoint on the question. That is my inference, not something I tested, so use the explicit breakpoint here and test the other option yourself.

The cost per call becomes four terms:

```
cost = ( input_tokens          x $0.10     # uncached remainder (the question)
       + cache_creation_tokens x $0.125    # 5-minute write, 1.25x
       + cache_read_tokens     x $0.01     # read, 0.1x
       + output_tokens         x $0.50 ) / 1,000,000
```

These are Haiku 5.5's rates for prompts up to 100,000 tokens. Above 100k, every rate changes, so the script is only valid below that.

**Worked example (assumed token counts, not measured).** Say the policy is 3,000 tokens, each question is 30 tokens, and each answer is 200 tokens.

| | Per call | 6 calls |
|---|---|---|
| Cache off | (3,030 × 0.10 + 200 × 0.50) / 1M = $0.000403 | $0.002418 |
| Cache on, call 1 (write) | (30 × 0.10 + 3,000 × 0.125 + 100) / 1M = $0.000478 | |
| Cache on, calls 2–6 (read) | (30 × 0.10 + 3,000 × 0.01 + 100) / 1M = $0.000133 | $0.000665 |
| Cache on, total | | $0.001143 (about 53% cheaper) |

Two things stand out. With one call, caching is about 19% more expensive, because you paid the write premium and never got a read. By call 2 it is already ahead. Once the input is cached, the output tokens (100 of the 133 millionths per call above) are most of the bill, so the next saving has to come from shorter answers.

## Try it

```python
# pip install anthropic   (set ANTHROPIC_API_KEY first)
import time, anthropic

client = anthropic.Anthropic()
MODEL = "claude-haiku-5-5"
PRICE = dict(inp=0.10, write=0.125, read=0.01, out=0.50)  # $/1M, prompts <= 100k tokens
POLICY = "\n".join(f"Policy {i}: orders over ${10 + i} ship free; returns accepted within {20 + i} days."
                   for i in range(1, 121))               # ~3k tokens, above the 512 minimum
QUESTIONS = ["Do orders over $15 ship free?", "How long do I have to return item 7?",
             "What is the return window for policy 100?", "Is shipping free over $50?",
             "Which policy mentions 31 days?", "Can I return something after 200 days?"]

def run(cached):
    block = {"type": "text", "text": "Answer only from this policy sheet.\n" + POLICY}
    if cached:
        block["cache_control"] = {"type": "ephemeral"}   # breakpoint after the stable part
    cost, read, write, t0 = 0.0, 0, 0, time.time()
    for q in QUESTIONS:                                  # sequential: call 1 must finish first
        r = client.messages.create(model=MODEL, max_tokens=2000, system=[block],
                                   messages=[{"role": "user", "content": q}])
        assert r.stop_reason != "max_tokens", "truncated: raise max_tokens"
        u = r.usage
        rd, wr = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
        cost += (u.input_tokens * PRICE["inp"] + wr * PRICE["write"]
                 + rd * PRICE["read"] + u.output_tokens * PRICE["out"]) / 1e6
        read, write = read + rd, write + wr
    print(f"cached={cached!s:5}  cost=${cost:.6f}  read={read}  written={write}  {time.time()-t0:.1f}s")
    return cost

off, on = run(False), run(True)
print(f"saved {100 * (1 - on / off):.0f}%")
```

I ran this script against a stub client to check that it executes and that the cost arithmetic matches the table. I have not run it against the live API, so your first real run is the real test. The output is two lines plus a savings line. The `cached=False` line should show `read=0 written=0`. The `cached=True` line should show `written` of about one policy sheet and `read` of about five times that. If `read` stays 0, the prefix changed, the prompt is under 512 tokens, or the cache expired. The `written` number is also your real token count, which on Haiku 5.5 may be higher than you guessed.

Three traps to try on purpose:
- **Run it twice within 5 minutes.** The second run's "call 1" will be a cache read, because the first run's write is still alive. Wait out the TTL, or add a unique line to the policy, for a clean cold start.
- **Fire the six questions in parallel.** The docs say a cache entry only becomes available after the first response starts. Parallel requests sent before then all miss. That is why the loop is sequential.
- **Shrink `POLICY` to 5 lines.** The prompt drops under 512 tokens, `cache_creation_input_tokens` stays 0, and you pay full price with no error.

## Where it fits

| | Explicit breakpoint on the system block (today) | Automatic caching (top-level `cache_control`) | No caching |
|---|---|---|---|
| Best for | Fixed long prefix, changing question | Growing conversations and agent loops, per the docs | One-off calls, prompts under 512 tokens |
| Cost / licence | 5-min write 1.25x, read 0.1x of input price | Same prices; 1-hour TTL is a 2x write | Plain input price |
| Watch out for | A change anywhere before the breakpoint invalidates the cache | Check the usage fields to confirm it hit (I haven't tested it on a changing-question workload) | Repeated input is paid in full every call |

## Flashcards
- **Q:** In a bot with a long fixed system prompt and a different question each call, where should the cache breakpoint go, and why?
  **A:** On the long system block, the last part that is identical across requests. A breakpoint on the changing question would cache a prefix that never matches again.
- **Q:** On Claude, what does `usage.input_tokens` mean when caching is active, and what is the total input?
  **A:** `input_tokens` is only the part after the last breakpoint. Total input is `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
- **Q:** What is the per-call cost formula for Haiku 5.5 with caching (prompts up to 100k tokens)?
  **A:** `(input_tokens × $0.10 + cache_creation × $0.125 + cache_read × $0.01 + output_tokens × $0.50) / 1M`. These are the 5-minute write and read rates. Above 100k tokens the rates change.
- **Q:** Why must a cache benchmark send its calls sequentially, not in parallel?
  **A:** A cache entry only becomes available after the first response starts. Parallel requests sent before that all miss the cache, so call 1 must finish first.
- **Q:** Once a large prompt is cached, where does most of the remaining cost come from, and what does that suggest?
  **A:** From output tokens, which are priced 5x input here and are never cached. The next saving comes from shorter answers, or from a lower effort setting.

## Quiz
1. Your cached run shows `cache_creation_input_tokens` of 0 and `cache_read_input_tokens` of 0 on every call, with no error. What is the most likely cause?
   - a) The API key lacks caching permission
   - b) The prompt is below the model's minimum cacheable length (512 tokens on Haiku 5.5)
   - c) Streaming is turned off
   <details><summary>Answer</summary>b. Prompts under the minimum are processed without caching and no error is returned. An expired TTL or a changed prefix would still show a write on the first call, so a total of 0 points to the minimum length.</details>
2. A call reports `input_tokens: 30`, `cache_read_input_tokens: 3000` and `cache_creation_input_tokens: 0`. How many input tokens did the request contain?
   - a) 30
   - b) 3,000
   - c) 3,030
   <details><summary>Answer</summary>c. Total input is the sum of all three fields. Only 30 of them were billed at the full input rate. The other 3,000 were billed at the read rate.</details>
3. When does a 5-minute cache write cost you more than not caching at all, using this lesson's prices?
   - a) When the cached prefix is read at least once
   - b) When you write the cache and never read it before it expires
   - c) Never, because writes are free
   <details><summary>Answer</summary>b. A write costs 1.25x the normal input price, so a write with no reads is a 25% surcharge on that part. One read at 0.1x more than makes up for it, which is why call 2 was already ahead in the worked example.</details>

## Go deeper
- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) (Claude Platform Docs, accessed 2026-11-04)
- [Claude Haiku 5.5 overview](https://platform.claude.com/docs/en/models/haiku-5-5/overview) (Claude Platform Docs, accessed 2026-11-04; pricing and the 512-token minimum)
- [What's new in Claude Haiku 5.5](https://platform.claude.com/docs/en/models/haiku-5-5/whats-new-haiku-5-5) (Claude Platform Docs, accessed 2026-11-04; tokenizer change and the lower cache minimum)

---
⏭️ **Tomorrow:** 🆕 New Models. We look at another release from the last two weeks that you can try today.
