---
date: 2026-10-03
track: tech-stack
topic: Tokens, context windows and pricing
slug: tokens-context-windows-pricing
tags: [llm, tokens, pricing, context-window, foundations]
read_time: 15 min
---

# 🧱 Tokens, context windows and pricing: how to estimate what a call costs

> **TL;DR**
> - LLMs read and write **tokens** (chunks of text), not words. You pay per million tokens, and output tokens usually cost about 5x as much as input tokens.
> - The **context window** is the model's working memory for one request: system prompt + messages + tool definitions + the reply (including thinking). Go over it and the request fails or stops early.
> - Don't guess. Count input tokens before the call with the free token-counting endpoint, and read `usage` from the response afterwards. That `usage` field is what you get billed for.

## What it is

A **token** is the unit a model actually reads. A tokenizer splits text into common chunks: a frequent word like "the" is one token, and a rare word like "pgvector" might be three or four. Anthropic's rule of thumb is about 4 characters or 0.75 English words per token. But that rule comes from the older tokenizer. Claude Opus 4.7 and every later model use a newer tokenizer that produces **about 30% more tokens for the same text**. On those models, 1M tokens is roughly 555k words. Code, non-English text and JSON usually cost more tokens per word than plain English.

The **context window** is the most tokens a single request can involve. Anthropic's docs list exactly what counts: the system prompt, every message (tool results, images and documents included), your tool definitions, and the output the model generates, *including its thinking*. As of today, Claude Opus 5.5, Sonnet 5.5 and Fable 5.1 have a 1M-token window with up to 128k output tokens, and Haiku 4.5 has 200k with up to 64k output.

**Pricing** is quoted per million tokens ("MTok"), with separate input and output rates. Some vocabulary you'll see on every pricing page:
- **Input tokens**: what you send.
- **Output tokens**: what the model writes back. Thinking tokens are billed as output.
- **Cache reads/writes**: discounted re-use of a prompt prefix you've sent before (a lesson of its own later in the curriculum).
- **Batch**: async jobs at 50% off.

## Why it matters

- **Budgeting a feature before you build it**: "10k support chats a day on Sonnet 5.5" turns into a dollar figure in one line of arithmetic (worked example below).
- **Model routing**: Anthropic's own pricing page suggests Haiku for simple tasks, Sonnet for most production work and Opus for the hardest reasoning. Knowing the per-token gap (Haiku 4.5 costs a quarter of Opus 5.5 per token) is how you justify a router.
- **Agents blow up context quietly**: every tool definition, tool result and earlier turn is re-sent on every call. For example, declaring Anthropic's browser-use toolset adds about 6,600 input tokens to *each* request before you've typed anything.

## How it works

**The cost formula** (no caching or batch):

```
cost = input_tokens  x input_price  / 1,000,000
     + output_tokens x output_price / 1,000,000
```

**Worked example.** A support bot does 10,000 calls/day, each with 2,000 input tokens and 500 output tokens, on Claude Sonnet 5.5 ($2 input / $10 output per MTok):

```
input : 10,000 x 2,000 = 20M tokens x $2  = $40
output: 10,000 x   500 =  5M tokens x $10 = $50
                                     total = $90/day (about $2,700/month)
```

Output is a quarter of the tokens here but more than half the bill. That's typical, and it's why capping `max_tokens` and asking for concise answers saves real money.

**Context accumulates.** In a chat, each turn re-sends the whole history:

```
turn 1:  [system][tools][user1]                        -> reply1
turn 2:  [system][tools][user1][reply1][user2]          -> reply2
turn 3:  [system][tools][user1][reply1][user2][reply2][user3] -> ...
         \___________________ you pay input price for all of this, every turn
```

So a 20-turn conversation costs far more than 20x a single turn. Two more things to know:
1. **Bigger isn't automatically better.** Anthropic's docs warn about *context rot*: accuracy and recall drop as the context grows. A 1M window is a ceiling, not a target.
2. **What happens at the limit.** If the input alone is over the window, the API returns a 400 "prompt is too long" error. On Claude 4.5 and newer models, if input plus `max_tokens` is over the window, the request is accepted. If generation then runs out of room, it stops with `stop_reason: "model_context_window_exceeded"`.

On current Claude models, long context has no surcharge: a 900k-token request is billed at the same per-token rate as a 9k one.

## Try it

```python
# pip install anthropic
# export ANTHROPIC_API_KEY=...   (never hard-code keys)
import anthropic

# USD per million tokens (input, output), from Anthropic's pricing page, Oct 2026
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
MAX_OUT = 500
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
system = "You are a concise technical writer."
messages = [{"role": "user", "content": "Explain what an LLM token is in 3 sentences."}]

def cost(model, n_in, n_out):
    p_in, p_out = PRICES[model]
    return (n_in * p_in + n_out * p_out) / 1_000_000

# 1) Before the call: count input tokens (free) and price the worst case.
for model in PRICES:
    n_in = client.messages.count_tokens(model=model, system=system, messages=messages).input_tokens
    print(f"{model:18} input={n_in:3} tok  worst case=${cost(model, n_in, MAX_OUT):.5f}")

# 2) After the call: response.usage is what you are actually billed for.
model = "claude-sonnet-5-5"
resp = client.messages.create(model=model, max_tokens=MAX_OUT, system=system, messages=messages)
u = resp.usage
print(f"\nactual on {model}: in={u.input_tokens} out={u.output_tokens} "
      f"cost=${cost(model, u.input_tokens, u.output_tokens):.5f}")
print("".join(b.text for b in resp.content if b.type == "text"))
```

You'll see three lines of estimates and then the real usage and answer. Expect Haiku 4.5's input count to be noticeably *lower* than the Opus/Sonnet counts for the same prompt, because Haiku 4.5 still uses the older tokenizer. Every cost will be a tiny fraction of a cent.

## Where it fits

| | Token-counting API (`count_tokens`) | Rule of thumb (chars / 4) | Read `usage` after the call |
|---|---|---|---|
| Best for | Exact pre-flight checks: "will this fit?", routing, budgets | Napkin math in a design doc | Billing, dashboards, per-user cost tracking |
| Cost / licence | Free (rate-limited by usage tier) | Free, offline | Free, comes with every response |
| Watch out for | It's an estimate, can differ slightly; can't count requests that use server tools (e.g. web search) | Off by about 30% on Claude Opus 4.7+ tokenizers, worse for code/non-English | Only known *after* you've spent the money; output length is unknown up front |

## Flashcards
- **Q:** Roughly how many tokens is a word of English text, and what changed with Claude Opus 4.7?
  **A:** Classic rule: 1 token ≈ 4 characters ≈ 0.75 words. Claude Opus 4.7 and later use a newer tokenizer that produces about 30% more tokens for the same text (1M tokens ≈ 555k words).
- **Q:** What counts toward a Claude model's context window?
  **A:** Everything in the request (system prompt, all messages including tool results/images/documents, tool definitions) plus the output generated for that turn, including thinking.
- **Q:** How are thinking tokens billed?
  **A:** As output tokens, once, when they are generated. They are part of max_tokens and count toward rate limits.
- **Q:** What's the cost formula for a single LLM call (no caching or batch)?
  **A:** input_tokens × input_price / 1M + output_tokens × output_price / 1M. Output is usually priced about 5x higher than input.
- **Q:** How do you know a request's real token usage before vs after sending it?
  **A:** Before: call the free token-counting endpoint (client.messages.count_tokens) for input tokens. After: read response.usage (input_tokens, output_tokens, cache fields), which is what you're billed on.

## Quiz
1. A chatbot sends 1,000 input tokens and gets 1,000 output tokens back on a model priced at $2 input / $10 output per MTok. What does the call cost?
   - a) $0.002
   - b) $0.012
   - c) $0.020
   <details><summary>Answer</summary>b. 1,000 × $2/1M = $0.002 input, plus 1,000 × $10/1M = $0.010 output, for $0.012 total. Output is most of the bill.</details>
2. You send a prompt that is longer than the model's context window. What happens?
   - a) The API silently truncates the oldest messages
   - b) The API returns a 400 "prompt is too long" error
   - c) The request succeeds but is billed at a long-context surcharge
   <details><summary>Answer</summary>b. The API doesn't truncate for you; chat apps like claude.ai may manage this, but the raw API rejects it. Current Claude models have no long-context surcharge either.</details>
3. You migrate an app from Claude Sonnet 4.6 to Claude Sonnet 5.5 and reuse your old token measurements to forecast cost. What's the main risk?
   - a) None, tokens are the same across all Claude models
   - b) You'll overestimate, because newer tokenizers are more compact
   - c) You'll underestimate, because Opus 4.7+ era tokenizers produce about 30% more tokens for the same text
   <details><summary>Answer</summary>c. Anthropic's docs say to recount prompts against the model you plan to use rather than reusing counts from earlier models.</details>

## Go deeper
- [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) (Anthropic docs, accessed 2026-10-03)
- [Context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows) (Anthropic docs, accessed 2026-10-03)
- [Token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) (Anthropic docs, accessed 2026-10-03)
- [Models overview](https://platform.claude.com/docs/en/models/overview) (Anthropic docs, accessed 2026-10-03)

---
⏭️ **Tomorrow:** 📅 Weekly recap: we'll tie this week's lessons together and pick a weekend build.
