---
date: 2026-10-27
track: tech-stack
topic: Streaming responses
slug: streaming-responses
tags: [streaming, sse, latency, ttft, tool-use, foundations]
read_time: 15 min
---

# 🧱 Streaming responses: show the first word in half a second, not the last word in twelve

> **TL;DR**
> - Streaming doesn't make the model faster. It sends the reply as a series of small events so the user sees text at *time to first token* (TTFT) instead of waiting for the finished answer.
> - The request is the same except for one flag. What changes is your code: you read events, assemble them yourself, and plan for a stream that dies halfway.
> - Tool arguments stream as *partial JSON strings*. Never parse or execute them until the block is complete.

## What it is

Normally you call an LLM API, wait, and get one finished object back. With **streaming** you send the same request (same model, same `max_tokens`, same messages) with streaming switched on. The reply comes back as a sequence of small **server-sent events** (SSE). SSE is a plain HTTP response that stays open while the server writes `event:` and `data:` lines to it. Your code reads each event as it arrives.

The API is still stateless. You aren't opening a chat session. You're changing how one reply is delivered.

Both big APIs use this shape, with different event names:

- **Claude Messages API:** you get a `message_start` event (an empty shell of the reply), then for each content block a `content_block_start`, many `content_block_delta` events and a `content_block_stop`. It ends with `message_delta` (stop reason and usage) and `message_stop`. `ping` events can appear anywhere. They are keep-alives with no content, so ignore them. The text lives in `text_delta` objects inside the deltas.
- **OpenAI Responses API:** you set `stream=True`. Common events for text are `response.created`, many `response.output_text.delta` events and `response.completed`. There are also events for refusals, reasoning summaries and function-call arguments.

If you only want the text, the Python SDKs hide most of this. Claude's `client.messages.stream()` gives you a `text_stream` iterator, and `get_final_message()` returns the assembled message at the end.

## Why it matters

- **Chat and copilot UIs:** the user starts reading after TTFT instead of staring at a spinner. Streaming converts one long wait into a short wait plus readable progress. TTFT is the number that governs how responsive the product feels.
- **Long generations:** Anthropic's docs warn against a large `max_tokens` without streaming (or the Batch API). Some networks drop idle connections after a while, and a non-streaming request can fail without a response. Streaming keeps bytes flowing, and the docs show `get_final_message()` for when you want the finished message anyway.
- **Agent UIs:** show "Running tests…" the moment a tool call starts, before its arguments are even complete. The Claude Agent SDK exposes the same `content_block_start` and `input_json_delta` events for this.

## How it works

```
your code                         API
   | --- request (stream on) --->  |
   | <-- message_start ----------  |   shell of the reply, input token count
   | <-- content_block_start ----  |   a text block (or tool_use block) begins
   | <-- content_block_delta ----  |   "Hel"   <- TTFT is the arrival of this first chunk
   | <-- content_block_delta ----  |   "lo, wo"
   | <-- ping -------------------  |   keep-alive, ignore
   | <-- content_block_stop -----  |   block is complete
   | <-- message_delta ----------  |   stop_reason + cumulative usage
   | <-- message_stop -----------  |
```

Five things to get right:

1. **TTFT vs total latency.** Total latency is request to last token. TTFT is request to first token. One ClickHouse example has a 400 ms TTFT and a 12.7 s end-to-end time for 410 output tokens. That is the difference between "alive" and "hanging". Streaming only improves the first number. It does nothing for total time.
2. **Reasoning models delay the first visible token.** A reasoning model thinks before it writes the answer, so the first *text* can arrive much later than a non-reasoning sibling's. One engineering write-up reports models with similar total latency but a TTFT of 30 s instead of 400 ms. If you route traffic to a reasoning model, graph TTFT. Some APIs stream a reasoning summary (OpenAI has `response.reasoning_summary_text.delta`), which you can show as "thinking…" progress.
3. **Tool arguments are partial JSON.** For a `tool_use` block, each delta is a fragment of a JSON *string* (`input_json_delta` on Claude, `response.function_call_arguments.delta` on OpenAI). The final `input` is an object. Concatenate the fragments and parse once the block closes (`content_block_stop` on Claude, `...arguments.done` on OpenAI). Claude's docs also say there can be pauses between events while the model works on a tool call. Anthropic has an opt-in "fine-grained tool streaming" mode (`eager_input_streaming`) that sends arguments sooner. Its docs tell you to check the stop reason, and then retry with a higher `max_tokens` or repair the partial input, because a cut-off call can leave incomplete JSON.
4. **Errors can arrive mid-stream.** The HTTP status was already 200 when the stream began, so a failure shows up as an `error` event in the stream. Claude's docs give `overloaded_error` as an example, which would be an HTTP 529 without streaming. Your handler needs a plan: keep or discard the partial text, and retry, ideally without double-printing what the user has already seen.
5. **Usage is cumulative.** The token counts in Claude's final `message_delta` are running totals, not per-chunk values (a secondary tutorial says this, and it matches how the SDK's final message works). Don't add them up. Read the total once, or use `get_final_message().usage`.

A practical consequence: **streaming and validation pull in opposite directions.** A schema-enforced answer (last Tuesday's topic) is only guaranteed valid *once complete*. You can show prose as it streams, but don't act on a half-finished JSON object.

## Try it

```python
# pip install anthropic openai
# env: ANTHROPIC_API_KEY and OPENAI_API_KEY (the script skips a provider whose key is missing)
import os, time
import anthropic
from openai import OpenAI

PROMPT = "Explain what a token is in three sentences."
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")  # swap for any current model ID

def report(name, t0, first, usage):
    print(f"\n[{name}] first text {first - t0:.2f}s | total {time.perf_counter() - t0:.2f}s | {usage}")

def run_claude():
    client, t0, first = anthropic.Anthropic(), time.perf_counter(), None
    with client.messages.stream(model=CLAUDE_MODEL, max_tokens=2000,
                                messages=[{"role": "user", "content": PROMPT}]) as stream:
        for text in stream.text_stream:
            first = first or time.perf_counter()
            print(text, end="", flush=True)
        usage = stream.get_final_message().usage
    report("claude", t0, first, f"in={usage.input_tokens} out={usage.output_tokens}")

def run_openai():
    client, t0, first, usage = OpenAI(), time.perf_counter(), None, None
    stream = client.responses.create(model="gpt-6.1-sol", input=PROMPT, stream=True,
                                     max_output_tokens=2000)
    for event in stream:
        if event.type == "response.output_text.delta":
            first = first or time.perf_counter()
            print(event.delta, end="", flush=True)
        elif event.type == "response.completed":
            usage = event.response.usage
        elif event.type == "error":
            print("\nstream error:", event.message)
    report("openai", t0, first or t0, f"in={usage.input_tokens} out={usage.output_tokens}")

if os.environ.get("ANTHROPIC_API_KEY"): run_claude()
if os.environ.get("OPENAI_API_KEY"): run_openai()
```

You should see the text appear word by word, then a line like `[claude] first text 0.9s | total 3.4s | in=... out=...` for each provider. The first-text time will be well below the total time. Then try a longer prompt (for example "Write a 500-word story") and watch the gap grow. The Claude model ID comes from Anthropic's docs examples, so swap in whichever current model you use.

## Where it fits

| | Streaming | Non-streaming call | Batch API |
|---|---|---|---|
| Best for | Anything a human watches: chat, copilots, agent progress, very long outputs | Short calls inside your own backend, where nobody sees partial text | Large offline jobs where you can wait |
| Cost / licence | Same request, so billed on tokens as usual (I didn't check for a streaming surcharge, so confirm on the pricing page) | Same | Anthropic offers a Message Batches API for long-running work (check its pricing page for discounts) |
| Watch out for | Mid-stream errors, partial JSON, proxies that buffer SSE and ruin the effect, TTFT on reasoning models | Long requests can hit network timeouts, with a large `max_tokens` the main risk | Not interactive. Results arrive later |

## Flashcards

- **Q:** What does streaming change about an LLM request, and what does it not change?
  **A:** It changes delivery: the reply arrives as a sequence of server-sent events instead of one finished object, so users see text at time to first token (TTFT). It doesn't make the model generate faster, so total latency is roughly the same.
- **Q:** What is the order of events in a Claude Messages stream?
  **A:** `message_start`, then per content block `content_block_start`, many `content_block_delta`, `content_block_stop`, then `message_delta` (stop reason, cumulative usage) and `message_stop`. `ping` keep-alives can appear anywhere and should be ignored.
- **Q:** Which OpenAI Responses events do you need to stream plain text, and how do you turn streaming on?
  **A:** Set `stream=True`. Append `event.delta` from `response.output_text.delta` events. `response.completed` marks the end (its `response.usage` holds the token counts), and an `error` event signals failure.
- **Q:** Why must you not parse streamed tool-call arguments until the block finishes?
  **A:** Each delta is a fragment of a JSON string (`input_json_delta` on Claude, `response.function_call_arguments.delta` on OpenAI), so the partial text usually isn't valid JSON. Concatenate, then parse at `content_block_stop` (Claude) or `...arguments.done` (OpenAI).
- **Q:** Name two streaming-specific failure modes your code must handle.
  **A:** (1) Errors arrive as events inside a stream whose HTTP status was already 200 (for example `overloaded_error`), so decide whether to keep the partial text and retry. (2) A cut-off tool call or JSON object (for example from hitting `max_tokens`) leaves incomplete JSON, so check the stop reason before acting.

## Quiz

1. A reasoning model and a non-reasoning model finish a task in about the same total time. Users say the reasoning one feels slower in your chat UI. What's the most likely reason?
   - a) Streaming is disabled for reasoning models
   - b) The reasoning model's first visible token arrives much later, because it thinks first
   - c) Reasoning models send fewer tokens per second
   <details><summary>Answer</summary>b. Total latency hides the wait before anything appears. Perceived speed depends on TTFT, and thinking happens before the answer text starts. Measure TTFT separately, and consider showing a reasoning summary or "thinking…" state.</details>

2. Your agent streams a `tool_use` block. When is it safe to run the tool?
   - a) As soon as the first `input_json_delta` arrives
   - b) After each delta, by parsing whatever JSON you have so far
   - c) After the block is complete (`content_block_stop`) and the arguments parse as valid JSON
   <details><summary>Answer</summary>c, because the deltas are partial JSON strings and the model can be cut off (for example by `max_tokens`), leaving the input incomplete. Parse once the block closes, and check the stop reason.</details>

3. You compute cost from a streamed Claude response by adding up the `usage` numbers from every event. What's wrong?
   - a) Nothing, streaming usage is per-chunk
   - b) The counts in `message_delta` are cumulative, so summing them over-counts. Use the final total (for example `get_final_message().usage`)
   - c) Streaming responses don't report usage
   <details><summary>Answer</summary>b. Usage in the stream is a running total, not a per-chunk amount. Read it once at the end, or let the SDK's final message do it for you.</details>

## Go deeper

- [Streaming messages, Claude Platform Docs](https://platform.claude.com/docs/en/build-with-claude/streaming) (Anthropic, accessed 2026-10-27)
- [Fine-grained tool streaming, Claude Platform Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming) (Anthropic, accessed 2026-10-27)
- [Claude API errors: long requests](https://platform.claude.com/docs/en/api/errors) (Anthropic, accessed 2026-10-27)
- [Streaming API responses](https://developers.openai.com/api/docs/guides/streaming-responses) (OpenAI, accessed 2026-10-27)
- [Time-to-First-Token Is the Latency SLO You Aren't Instrumenting](https://tianpan.co/blog/2026/04/23/ttft-latency-slo-streaming-reasoning-models) (TianPan.co, 2026-04-23, a blog post, so treat its numbers as illustrative)

---
⏭️ **Tomorrow:** 🛠️ Build It: a small harness that streams the same prompt at several reasoning-effort levels and charts TTFT against cost.
