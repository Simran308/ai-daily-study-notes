---
date: 2026-11-03
track: tech-stack
topic: Prompt caching, cutting cost and latency
slug: prompt-caching
tags: [caching, pricing, latency, claude, openai, foundations]
read_time: 15 min
---

# 🧱 Prompt caching: stop paying full price to re-read the same prompt

> **TL;DR**
> - Every LLM call re-reads your whole prompt. Prompt caching lets the provider reuse its work on a *prefix* that is identical to a recent request, so that part of the input is billed at a steep discount and starts faster.
> - It only works on a prefix, so order matters: stable content first (tools, system prompt, documents, examples) and changing content last. One changed character early in the prompt means a miss for everything after it.
> - On Claude Haiku 5.5 a cache read costs 10% of the normal input price. A cache write costs 1.25x (5-minute lifetime) or 2x (1-hour lifetime). A prompt reused even once usually pays for itself.

## What it is

Your prompt is turned into tokens, and the model builds internal state (the "KV cache", its working memory of the prompt) before it can write the first output token. For a long prompt, that prefill work is a big part of both your bill and your wait. If the next request starts with exactly the same tokens, the provider can reuse the saved work instead of recomputing it.

That is **prompt caching**. The model's output is not affected, only the cost and latency of reading the input. OpenAI's guide says it does not influence the generated output, and it also says caching can cut latency by up to 80% and input cost by up to 90%. Treat those as best-case vendor numbers.

Each provider handles it a little differently, and the details have been changing.

- **Anthropic (Claude)**: you opt in. Its docs describe two ways. *Automatic caching* moves the cache point forward as a conversation grows. *Explicit breakpoints* are `cache_control` markers you place on specific blocks. The default lifetime (TTL) is 5 minutes, with a 1-hour option.
- **OpenAI**: caching has historically been automatic, with no code changes, no write fee, and a 1,024-token minimum. The current docs page now also describes cache lifetime options and an explicit mode, with a table that differs by model. *(Unverified for GPT-6.1 Sol specifically: I could only read excerpts, so check your model's row before relying on any number.)*
- **DeepSeek**: prefix caching is automatic. The prices for V4.1 Flash are in our 2026-10-19 lesson: $0.15 per 1M on a miss and $0.003 on a hit, off-peak.

## Why it matters

- **Agent loops**: every turn resends the system prompt, the tool definitions and the whole conversation so far (our tool-use and streaming lessons). Nearly all of that input is a repeat of the previous turn.
- **Document Q&A**: put a 50-page contract or a codebase summary in the prompt once, then ask many questions against it, each reading the cached document.
- **Support bots with long policies**: a 5,000-token rulebook plus a 50-token customer message. The rulebook is the same on every call.

A worked example with Haiku 5.5's prices. Say you have a 10,000-token stable prefix, a 50-token question and a 200-token answer, repeated 1,000 times within the cache lifetime:

| Scenario | Input cost | Output cost | Total |
|---|---|---|---|
| No caching | 1,000 × 10,050 × $0.10/M ≈ $1.01 | 1,000 × 200 × $0.50/M = $0.10 | **≈ $1.11** |
| Cached prefix | 1 write ($0.00125) + 999 reads ($0.0999) + question tokens ($0.005) ≈ $0.11 | $0.10 | **≈ $0.21** |

Input cost drops by about 90%, but the total drops by about 81%, because output tokens are not cached. Caching helps most when input dominates your bill.

## How it works

```
Request 1:  [tools][system prompt][document]  [question A]
             └──────── cached prefix ───────┘   (new tokens)
             cache WRITE (1.25x)                 full price

Request 2:  [tools][system prompt][document]  [question B]
             └──────── identical prefix ────┘
             cache READ (0.1x)                   full price
```

Four rules explain nearly everything:

1. **Prefix only.** The cached unit is everything from the start of the prompt up to a breakpoint. Claude's docs say the prefix covers tools, then system, then messages, in that order. Any change inside that range invalidates the cache from that point on.
2. **Static first, dynamic last.** Anthropic's guidance is to put tool definitions, system instructions, context and examples at the beginning. Anything that changes per request goes after the cached part. Common cache-busters are a timestamp or user name in the system prompt, tools listed in a different order, or per-request text inserted early.
3. **Minimum length.** A prefix shorter than the model's minimum is simply not cached, with no error. The Haiku 5.5 overview lists 512 tokens. OpenAI's older docs say 1,024. Check the number for your model.
4. **It expires.** Claude's default lifetime is 5 minutes. The secondary pricing write-up I found says a cache read refreshes the timer, so steady traffic keeps the cache warm. If traffic is sparse, the cache expires and you pay the write price again.

**What Claude invalidates.** Anthropic's docs list changes that bust the cache. Two examples are toggling web search or citations, which modify the system prompt, and adding or removing images anywhere in the prompt. When your agent loop uses defer-loaded tools, the docs say the prefix stays untouched and so does the cache.

**Pricing multipliers on Haiku 5.5** (per 1M tokens, prompts up to 100k tokens, from the model overview):

| Item | Price | Relative to input |
|---|---|---|
| Normal input | $0.10 | 1x |
| 5-minute cache write | $0.125 | 1.25x |
| 1-hour cache write | $0.20 | 2x |
| Cache read | $0.01 | 0.1x |

Break-even follows from the table. A 5-minute write costs 0.25x extra, and each read saves 0.9x, so **one reuse** pays it back. A 1-hour write costs 1x extra, so it needs **two reads** to come out ahead. Use the 1-hour option when your traffic gaps are longer than 5 minutes but the prefix will still be reused several times.

**It interacts with the 100k tier.** A secondary write-up (eesel.ai, accessed 2026-11-03) says Anthropic counts cached tokens toward the 100k boundary, so a 120k-token prompt that is mostly cached still pays the over-100k rates, only with cached tokens at the cheaper cache-read price. *(Secondary source: confirm in Anthropic's pricing docs.)* So caching does not replace keeping prompts under the tier boundary.

## Try it

```python
# pip install anthropic   (export ANTHROPIC_API_KEY=...)
import os
import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")  # confirm the ID in the models overview
P = dict(inp=0.10, write=0.125, read=0.01, out=0.50)  # $/1M tokens, Haiku 5.5, prompts <= 100k

RULES = "\n".join(
    f"Rule {i}: Refunds for order type {i} are allowed within {10 + i} days if the item is unused."
    for i in range(1, 161)
)  # stable text, > 512 tokens, no timestamps
SYSTEM = [{"type": "text",
           "text": "You are a support agent. Answer only from these rules.\n" + RULES,
           "cache_control": {"type": "ephemeral"}}]  # breakpoint: cache everything up to here

client = anthropic.Anthropic()

def ask(question):
    r = client.messages.create(model=MODEL, max_tokens=2000, system=SYSTEM,
                               messages=[{"role": "user", "content": question}])
    u = r.usage
    w, rd = u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0
    cost = (u.input_tokens * P["inp"] + w * P["write"] + rd * P["read"]
            + u.output_tokens * P["out"]) / 1e6
    print(f"fresh={u.input_tokens} written={w} read={rd} out={u.output_tokens} cost=${cost:.6f}")

ask("How many days do I have to return an unused item of order type 7?")
ask("And for order type 42?")
```

Expected output: the first line shows a large `written` number and `read=0`. The second line, sent within 5 minutes, shows `written=0` and a `read` number of about the same size, with a lower cost. If `read` stays 0, the prefix is below the minimum or something in it changed between calls. Output and thinking tokens vary run to run, so costs will differ slightly.

On OpenAI the same check is `usage.input_tokens_details.cached_tokens` on the Responses API (`usage.prompt_tokens_details.cached_tokens` on Chat Completions). OpenAI also lets you pass `prompt_cache_key` consistently across requests that share a prefix, which helps route them to the same cache.

## Where it fits

| | Claude (Anthropic) | OpenAI | DeepSeek |
|---|---|---|---|
| How you turn it on | `cache_control` breakpoints, or automatic caching | Automatic on recent models. Newer docs also describe explicit controls, by model *(check yours)* | Automatic prefix matching |
| Write cost | 1.25x (5m) or 2x (1h) on Haiku 5.5 | No extra write fee in the older docs. Newer docs list write charges for some models *(check yours)* | None mentioned in our earlier lesson |
| Read price | 0.1x input on Haiku 5.5 | Discounted, varies by model | About 1/50 of a miss (our 2026-10-19 lesson) |
| Watch out for | 5-minute expiry, minimum length, cache busters in the prefix | Minimum length, and docs that differ by model | Peak vs off-peak pricing still applies |

## Flashcards
- **Q:** What does prompt caching actually cache, and what does it change about the response?
  **A:** The provider's work on an identical prompt prefix (the prefill state). It lowers the price and latency of reading that part of the input. It does not change the generated output.
- **Q:** What prompt layout gets the most cache hits, and why?
  **A:** Stable content first (tools, system prompt, reference documents, examples) and changing content last. Caching matches only a prefix, so a change early in the prompt invalidates everything after it.
- **Q:** What are Claude Haiku 5.5's cache prices relative to normal input (prompts up to 100k tokens)?
  **A:** 5-minute write 1.25x ($0.125/M), 1-hour write 2x ($0.20/M), read 0.1x ($0.01/M), against $0.10/M for normal input.
- **Q:** How many reuses does it take to pay back a 5-minute cache write, and a 1-hour write?
  **A:** One read for the 5-minute write (0.25x extra cost, 0.9x saved per read). Two reads for the 1-hour write (1x extra cost).
- **Q:** How do you check that caching worked on Claude and on OpenAI?
  **A:** Claude: `usage.cache_creation_input_tokens` and `usage.cache_read_input_tokens`, with `input_tokens` counting only the uncached remainder. OpenAI: `cached_tokens` inside the usage details. If the read count stays 0, the prefix changed, expired or is below the minimum length.

## Quiz
1. Your system prompt starts with "Today is {date}, the user is {name}." followed by 4,000 tokens of fixed rules. You never get cache hits. What is the best fix?
   - a) Switch to the 1-hour cache lifetime
   - b) Move the date and name after the fixed rules, or into the user message
   - c) Shorten the rules to under 512 tokens
   <details><summary>Answer</summary>b, because the cache matches only an identical prefix. The date and name change per request, so they invalidate everything after them. The 1-hour lifetime doesn't help if the prefix itself keeps changing, and shortening below the minimum would turn caching off.</details>
2. On Haiku 5.5, you send a 10,000-token prefix exactly twice, 20 minutes apart, using the default 5-minute lifetime. What do you expect?
   - a) Two cache writes, because the first entry expired
   - b) One write and one read
   - c) One write and one read, because caches never expire
   <details><summary>Answer</summary>a, because the default lifetime is 5 minutes and the gap is 20 minutes. Each request pays the 1.25x write price, so this pattern costs slightly more than no caching. Use the 1-hour option or send traffic more often.</details>
3. A pipeline's bill is mostly output tokens, with short prompts of about 300 tokens. How much will prompt caching help?
   - a) A lot, because every call is cached
   - b) Very little: the prompt is likely below the minimum cacheable length, and caching doesn't touch output costs
   - c) It will make output tokens cheaper
   <details><summary>Answer</summary>b, because caching discounts only the reused input prefix and has a minimum length (512 tokens on Haiku 5.5). Output tokens are billed at the normal output rate, so look at output length or model choice instead.</details>

## Go deeper
- [Prompt caching (Claude Platform Docs)](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) (Anthropic, accessed 2026-11-03)
- [Prompt caching (OpenAI API guide)](https://developers.openai.com/api/docs/guides/prompt-caching) (OpenAI, accessed 2026-11-03)
- [Claude Haiku 5.5 overview, with pricing and the 512-token minimum](https://platform.claude.com/docs/en/models/haiku-5-5/overview) (Anthropic, accessed 2026-11-03)
- [Claude Haiku 5.5 pricing: the 100k cliff](https://www.eesel.ai/blog/claude-haiku-5-5-pricing) (eesel.ai, secondary source, accessed 2026-11-03)

---
⏭️ **Tomorrow:** 🛠️ Build It, a small harness that logs cache hit rate and cost per run, so you can see exactly what caching saves on your own agent loop.
