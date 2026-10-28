---
date: 2026-10-28
track: build-it
topic: Build a streaming support agent with a turn cap, time to first token and cost per run
slug: streaming-agent-loop-ttft-cost
tags: [build-it, streaming, tool-use, agents, pricing, claude-haiku-5-5]
read_time: 15 min
---

# 🛠️ Build a streaming support agent: turn cap, time to first token and cost per run

> **TL;DR**
> - You will combine two earlier lessons, the tool-use loop (10-20) and streaming (10-27), into one ~40-line agent that prints text as it arrives.
> - The loop has three guards: a turn cap, a check of the stop reason before acting, and a cost counter read from `usage`.
> - On a model with thinking on by default, "first token" can mean a thinking token or a visible text token. Measure the one your user actually sees.

## What it is

This is a small customer-support agent. A user asks "where is order A100?". The model calls a `get_order_status` tool, your code runs it, and the model answers. The answer streams to the terminal as it is generated.

Nothing here is new, which is the point. A **Build It** day exists to make earlier lessons stick by wiring them together:

- **Tool-use loop (10-20):** the model only *asks* for a tool call. Your code runs it, sends back the result, and calls the API again until the stop reason is no longer `tool_use`.
- **Streaming (10-27):** the reply arrives as server-sent events. Text deltas can be shown immediately. Tool arguments arrive as JSON fragments that you must not parse until the block is finished.
- **Cost from `usage` (10-03 and 10-07):** you are billed on what `response.usage` reports, not on what you guessed.

We use `claude-haiku-5-5` as the model. It was released on 2026-10-07, and its API ID has no date suffix. Its price is $0.10 per 1M input tokens and $0.50 per 1M output tokens for prompts of up to 100,000 tokens, and $0.50 and $2.50 above that. Thinking is adaptive and on by default, and thinking tokens are billed as output. Those facts come from the third-party write-ups linked below, which match Anthropic's pricing page as they quote it. Check Anthropic's page before you budget real money.

## Why it matters

- **Support and chat UIs:** a user who sees words after about a second feels the product is fast, even if the full answer takes six seconds.
- **Agent frameworks:** most of them are this loop with more tools and more bookkeeping. If you can write it by hand, you can debug them.
- **Cost control in production:** a per-run cost number and a turn cap are the two cheapest safeguards against a runaway agent loop.

## How it works

```
user question
     │
     ▼
┌─────────────── turn 1 .. MAX_TURNS ───────────────┐
│ stream request ──► text deltas ──► print them     │
│        │            (note time of the first one)  │
│        ▼                                          │
│ get_final_message()  ← full message, usage, stop  │
│        │                                          │
│  add cost from usage                              │
│        │                                          │
│  stop_reason == "tool_use"?                       │
│     no  ──► done                                  │
│     yes ──► run tools, append tool_result, loop   │
└───────────────────────────────────────────────────┘
turns used up while still wanting tools ──► "stopped" message
```

Four design choices matter here.

1. **Stream for display, then take the final message for logic.** The SDK's stream helper hands you text pieces as they arrive. After the stream ends, `get_final_message()` gives you the assembled message. That message has complete, already-parsed tool-call inputs, the stop reason and the usage. You never hand-parse a partial JSON fragment.
2. **Append the whole assistant message back.** Pass `msg.content` as-is, not just the text. It contains the `tool_use` blocks, and with thinking on it can also contain thinking blocks. Dropping them can break the next turn.
3. **Time to first token depends on what you count.** With adaptive thinking, the model may think silently before any visible text. If you time the first *text* delta, that includes thinking time. That is the number your user feels. If you want pure network and queue latency, time the first event of any kind instead.
4. **Leave `max_tokens` generous.** Thinking tokens count toward the output limit. A tight cap can truncate the reply and leave you with a half-finished tool call. We use 4096, and the code checks the stop reason before acting.

## Try it

```python
# pip install anthropic   (export ANTHROPIC_API_KEY first)
import time, anthropic
client = anthropic.Anthropic()
MODEL, MAX_TURNS, IN_P, OUT_P = "claude-haiku-5-5", 6, 0.10, 0.50  # $/1M, prompt <= 100k

ORDERS = {"A100": "shipped, arriving Friday", "B200": "processing"}
def get_order_status(order_id): return ORDERS.get(order_id, "not found")
TOOLS = [{"name": "get_order_status", "description": "Look up an order's status by ID.",
          "input_schema": {"type": "object", "required": ["order_id"],
                           "properties": {"order_id": {"type": "string"}}}}]

def run(question):
    messages, cost, ttft, t0 = [{"role": "user", "content": question}], 0.0, None, time.perf_counter()
    for turn in range(1, MAX_TURNS + 1):
        with client.messages.stream(model=MODEL, max_tokens=4096, tools=TOOLS,
                                    messages=messages) as stream:
            for text in stream.text_stream:
                ttft = ttft or time.perf_counter() - t0
                print(text, end="", flush=True)
            msg = stream.get_final_message()
        cost += (msg.usage.input_tokens * IN_P + msg.usage.output_tokens * OUT_P) / 1e6
        if msg.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": msg.content})
        results = [{"type": "tool_result", "tool_use_id": b.id,
                    "content": get_order_status(**b.input)}
                   for b in msg.content if b.type == "tool_use"]
        messages.append({"role": "user", "content": results})
    else:
        print("\n[stopped: turn cap reached]")
    total = time.perf_counter() - t0
    print(f"\n\nturns={turn} stop={msg.stop_reason} ttft={ttft or 0:.2f}s "
          f"total={total:.2f}s cost=${cost:.6f}")

run("Where is order A100, and what about B200?")
```

You should see the answer appear word by word, followed by a stats line such as `turns=2 stop=end_turn ttft=…s cost=$0.0004…`. The exact timings and cost will differ on your machine. The cost should be a small fraction of a cent.

Notes on the code:

- **Cost formula:** it ignores caching, so it is only right while you aren't using prompt caching. If you add caching, also read the cache fields on `usage`. For scale: 2,000 input and 300 output tokens cost 2,000×0.10/1M + 300×0.50/1M = $0.00035.
- **Parallel calls:** the model may ask for both orders in one turn. The list comprehension handles that and returns all results in one user message.
- **Turn cap:** the `for ... else` prints the "stopped" message only if the loop ran out of turns without a `break`.
- **Not re-verified today:** I could not re-open Anthropic's SDK docs while writing this. The helper names `messages.stream`, `text_stream` and `get_final_message` are the SDK's documented streaming helpers as I know them. If your installed version differs, check the streaming docs linked below.

**Extend it (pick one, 20 minutes):**

1. Add a `print(msg.usage)` per turn and watch the input tokens grow on turn 2, then explain why.
2. Make the tool raise on unknown IDs and return `is_error: true` in the `tool_result`. See how the model explains the failure to the user.
3. Set `MAX_TURNS = 1` and ask the two-order question. Confirm the cap message appears, and note what you would show a real user at that point.

## Where it fits

| | Hand-written streaming loop (this lesson) | Non-streaming loop | Agent framework (SDK or LangGraph) |
|---|---|---|---|
| Best for | Chat UIs where a person watches the reply, and for learning what frameworks do | Batch jobs and back-end pipelines where nobody is waiting | Many tools, memory, branching, retries and tracing |
| Cost / licence | Same token bill as the others. A few extra lines of code | Same token bill, simplest code | Same token bill, plus a dependency to learn and keep updated |
| Watch out for | Mid-stream errors, truncated tool calls, and thinking time hiding inside "TTFT" | Users stare at a spinner for the whole generation | Hidden extra turns and tokens. Add your own cap and cost counter anyway |

## Flashcards
- **Q:** Why does the streaming agent loop use `get_final_message()` after the text stream ends, instead of parsing tool arguments from the deltas?
  **A:** Streamed tool arguments are JSON fragments that aren't valid until the block finishes. The final message has the complete, parsed tool inputs, the stop reason and the usage, so your logic works on a finished object while the user still sees text live.
- **Q:** What must you append to `messages` after a turn where the model asked for tools, and why?
  **A:** The full assistant `msg.content` (the `tool_use` blocks, plus any thinking blocks), followed by one user message of `tool_result` blocks. Each result carries the matching `tool_use_id`. Sending only the text breaks the pairing between request and result.
- **Q:** On a model with thinking on by default, what does "time to first token" depend on, and how do you measure what the user feels?
  **A:** Visible text may only start after silent thinking, so the first text delta includes that thinking time. Time the first text delta for the user-felt number, or the first stream event of any kind for network and queue latency. Say which one you measured.
- **Q:** What three guards does a safe agent loop need, as built in this lesson?
  **A:** (1) A turn cap, so a confused model can't loop and bill you forever, with a clear "stopped" result when it is hit. (2) A check of `stop_reason` before acting, so truncated output isn't treated as a finished tool call. (3) A cost counter from `response.usage`, so every run reports what it spent.
- **Q:** How do you compute the cost of one run from per-turn usage, and when does that formula stop being enough?
  **A:** Sum (input_tokens × input price + output_tokens × output price) / 1M over every turn. It stops being enough once you use prompt caching, because cache reads and writes are billed at different rates, or when a prompt crosses a pricing tier such as Haiku 5.5's 100k-token boundary.

## Quiz
1. In the loop, the model's final message has `stop_reason == "max_tokens"` and contains a half-written `tool_use` block. What should your code do?
   - a) Run the tool with whatever arguments arrived and continue
   - b) Treat it as a failed or incomplete turn: don't run the tool, and retry with a higher `max_tokens` or hand off
   - c) Ignore the stop reason, because streaming guarantees complete blocks
   <details><summary>Answer</summary>b, because a truncated block means the JSON may be incomplete or wrong. Acting on it risks running a tool with bad arguments. The stop reason is the signal to check first.</details>
2. You switch the same task from non-streaming to streaming. What do you expect?
   - a) Total time drops a lot, because the model generates faster
   - b) The token bill drops, because streamed tokens are cheaper
   - c) The user sees text sooner, but total time and token cost stay roughly the same
   <details><summary>Answer</summary>c, because streaming changes delivery, not generation speed or pricing. It improves perceived latency because words appear at the first text token.</details>
3. Your agent's cost counter reads far below the dashboard bill after you turn on prompt caching. What is the most likely cause?
   - a) The counter only sums `input_tokens` and `output_tokens`, and ignores the cache read and write fields on `usage`
   - b) Streaming hides some tokens from `usage`
   - c) The turn cap removed some calls from the bill
   <details><summary>Answer</summary>a, because cache writes and reads are separate usage fields billed at their own rates. A formula built before caching won't see them, so extend the counter when you add caching.</details>

## Go deeper
- [Claude Haiku 5.5: specs, effort levels, pricing, and how to use it](https://www.eesel.ai/blog/claude-haiku-5-5) (eesel.ai, third-party summary, about 2026-10-09; the source for the model ID, 1M context and price tiers above)
- [Claude Haiku 5.5: Features, Benchmarks, and Pricing](https://www.datacamp.com/blog/claude-haiku-5-5) (DataCamp, about 2026-10-08; a second source confirming the prices and the model ID)
- [Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming) (Anthropic docs, not re-opened while writing, so check it for current SDK helper names and event types)

---
⏭️ **Tomorrow:** 🆕 New Models. Thursday is a fresh look at a recent release, or a round-up of three, with one thing you can try the same day.
