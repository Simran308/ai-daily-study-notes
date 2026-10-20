---
date: 2026-10-20
track: tech-stack
topic: Tool use and function calling, the loop behind every agent
slug: tool-use-function-calling-loop
tags: [tool-use, function-calling, agents, claude, openai, responses-api, foundations]
read_time: 15 min
---

# 🧱 Tool use and function calling: the loop behind every agent

> **TL;DR**
> - The model never runs your code. It emits a structured request ("call `get_order` with `{"order_id": "A100"}`"), your code runs it, and you send the result back.
> - An agent is a `while` loop around that round trip. It keeps going while the model says it wants a tool and stops when the model gives a final answer.
> - Most production bugs live in the loop, not the model: dropped `tool_use_id`s, parallel calls handled wrongly, errors that crash instead of being reported, and no turn cap.

## What it is

**Tool use** (also called **function calling**) lets you describe functions to a model: a name, a plain-English description and a JSON Schema for the arguments. When a user request needs one, the model replies with a structured call instead of prose. Last week's structured-outputs lesson covered making the model's *answer* match a schema. Tool use applies the same idea to the model's *requests for action*.

Anthropic's docs describe it as a contract between your application and the model. You declare what operations exist and what shape their inputs and outputs take. Claude decides when and how to call them, but it "never executes anything on its own". It asks, and your code (or the vendor's servers, for built-in tools like web search) does the work.

There are two kinds of tools, and the difference affects your code:

- **Client tools** run in your application. These are your own functions, plus Anthropic-defined schemas such as `bash` and `text_editor`. You must execute them and return the result.
- **Server tools** (for example `web_search` and `code_execution`) run on the vendor's infrastructure. You just see the results.

This lesson is about client tools, because that is where the loop lives.

## Why it matters

- **Customer support agents** look up the order and then issue the refund (or refuse), instead of guessing from the prompt.
- **Coding agents**, such as the Stripe Minions covered on 2026-10-09, are tools (read file, edit file, run tests) plus a loop.
- **Data assistants** turn "how many signups last week?" into a SQL tool call and then explain the returned rows.

## How it works

The round trip has five steps. Every agent framework you will meet is a wrapper around it.

```
          ┌──────────────────────────────────────────┐
          │ 1. You send: messages + tool definitions │
          └───────────────────┬──────────────────────┘
                              ▼
                  ┌───────────────────────┐
                  │ 2. Model replies      │
                  └───────┬───────┬───────┘
        stop_reason ==    │       │   anything else
        "tool_use"        ▼       ▼   (e.g. "end_turn")
   ┌──────────────────────────┐  ┌────────────────┐
   │ 3. Your code runs each   │  │ 5. Done: show  │
   │    requested tool        │  │    final text  │
   └────────────┬─────────────┘  └────────────────┘
                ▼
   ┌──────────────────────────┐
   │ 4. Append the model's    │
   │    reply + tool results; │
   │    go back to step 1     │
   └──────────────────────────┘
```

Anthropic's docs call this canonical shape "a while loop keyed on `stop_reason`". While the stop reason is `"tool_use"`, execute the tools and continue the conversation.

**The same idea in two APIs.** The vocabulary differs, but the loop doesn't.

| Step | Claude Messages API | OpenAI Responses API |
|---|---|---|
| Declare a tool | `{"name", "description", "input_schema"}` | Flat `{"type": "function", "name", "description", "parameters"}` |
| Model asks for a call | `tool_use` block with `id`, `name`, `input` | `function_call` output item with `call_id`, `name`, `arguments` |
| You return the result | `tool_result` block with `tool_use_id` | `function_call_output` item with `call_id` and `output` |

Four details cause most of the pain:

1. **Every call has an ID, and the result must echo it.** The ID is how the model matches answers to questions, especially when it asks for several things at once.
2. **Continuation rules are strict on Claude.** The reply must be one user message containing *only* `tool_result` blocks, one for every `tool_use` block in the response. The request must also keep the same `tools` array.
3. **Keep the model's whole turn in the history.** Append the assistant's full response, not just its text. On OpenAI's newer GPT-6 models, the docs say to preserve reasoning and function-call items when you manage history yourself. If you'd rather not resend history, the Responses API supports `previous_response_id`.
4. **Parallel tool calls are normal.** On Claude, parallel tool use is on by default, so one response can contain several `tool_use` blocks. A loop that handles only the first block will break. One developer reported that a naive loop crashed on 388 of 1,200 eval runs for this reason (a single blog post, so treat the exact figure as an anecdote). Run every call and return all results together. Mark failures with `is_error: true`, so the model can recover instead of your program crashing.

Parallel calls are only safe when the tools are independent. For side-effecting tools such as `write_file` followed by `run_tests`, either run the blocks sequentially in order or turn parallelism off. On Claude, `disable_parallel_tool_use: true` goes **inside** the `tool_choice` object, not at the top level of the request. It costs extra turns, so use it only when order matters.

**Two model-specific notes (verified 2026-10-20):**

- For **GPT-6.1 Sol**, OpenAI says to use the Responses API for tool calling. Chat Completions works on that model only for requests without tools. If you built an old loop on Chat Completions, you must port it. GPT-6 also adds *async tool calling*: mark a function `async: true` and the model keeps working while your tool runs, then you return the result later using the original `call_id`. You still execute the tool and track what's pending.
- On Claude, some models don't support the `tool_choice` types `any` and `tool` (which force a tool call). The current parallel-tool-use docs list Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1. Check the docs for the model you use before relying on forced tool calls.

**Writing good tool definitions.** The model chooses tools based only on the name, description and schema. A vague description ("gets order stuff") gives vague behaviour. Say what the tool does, when to use it, and what the arguments mean. Fewer, clearly separated tools beat many overlapping ones, which is the same lesson as Stripe showing its agent about 15 tools out of 400+.

## Try it

```python
# pip install anthropic   (set ANTHROPIC_API_KEY in your environment)
import json, anthropic

client = anthropic.Anthropic()
MODEL = "claude-haiku-5-5"
ORDERS = {"A100": {"status": "shipped", "total": 42.0},
          "B200": {"status": "processing", "total": 130.0}}

def get_order(order_id):
    if order_id not in ORDERS:
        raise KeyError(f"no order with id {order_id}")
    return ORDERS[order_id]

IMPL = {"get_order": get_order}
tools = [{"name": "get_order",
          "description": "Look up one order by ID. Returns its status and total in USD.",
          "input_schema": {"type": "object",
                           "properties": {"order_id": {"type": "string"}},
                           "required": ["order_id"]}}]

def run(question, max_turns=8):
    messages = [{"role": "user", "content": question}]
    for turn in range(max_turns):                       # always cap the loop
        resp = client.messages.create(model=MODEL, max_tokens=2048,
                                      tools=tools, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":              # final answer
            return "".join(b.text for b in resp.content if b.type == "text")
        results = []
        for b in resp.content:                          # may be several (parallel)
            if b.type != "tool_use":
                continue
            try:
                out, is_err = json.dumps(IMPL[b.name](**b.input)), False
            except Exception as e:                      # report errors, don't crash
                out, is_err = f"Error: {e}", True
            print(f"turn {turn}: {b.name}({b.input}) -> {out}")
            results.append({"type": "tool_result", "tool_use_id": b.id,
                            "content": out, "is_error": is_err})
        messages.append({"role": "user", "content": results})
    return "Stopped: too many turns"

print(run("Which is more expensive, order A100 or B200? Has either shipped? Also check Z999."))
```

Expect to see two or three `get_order` calls printed, likely in the same turn, with `Z999` coming back as an error. The final answer should compare the two real orders and say that `Z999` doesn't exist. The exact number of turns can vary between runs.

Try this: delete the `is_error` handling and let `get_order("Z999")` raise. Then try removing `max_turns`, and notice what you'd be risking in production.

## Where it fits

| | Hand-written tool loop (this lesson) | Agent SDK / framework | Fixed workflow (no tool loop) |
|---|---|---|---|
| Best for | Learning, small agents, full control over logging and permissions | Many tools, memory, sub-agents, less boilerplate | Tasks where the steps are known in advance |
| Cost / licence | Only the tokens you use; each loop turn resends the history, so cost grows with turns | Same token cost, plus a dependency to learn | Cheapest and most predictable |
| Watch out for | You own every edge case: parallel calls, errors, turn caps, truncation | Hides the loop, so bugs are harder to see if you never learned it | Can't adapt when the task needs a different path |

Don't build the loop if a fixed pipeline does the job. A tool loop earns its keep only when the model needs to decide *which* step comes next.

## Flashcards

- **Q:** Who actually executes a function the model "calls", and what does the model produce?
  **A:** Your code does (for client tools). The model only emits a structured request: the tool name plus a JSON object of arguments. You run it and send the result back.

- **Q:** What is the shape of the agent loop on Claude's Messages API?
  **A:** Call the API with the messages and `tools`. While `stop_reason == "tool_use"`, run every `tool_use` block, append the assistant's reply, then append one user message of `tool_result` blocks, and call again. Stop on any other stop reason, such as `end_turn`.

- **Q:** How do you pair a tool result with its request on Claude vs OpenAI's Responses API?
  **A:** Claude: a `tool_result` block carrying the `tool_use_id` of the `tool_use` block. OpenAI: a `function_call_output` item carrying the `call_id` of the `function_call` item.

- **Q:** What should a loop do when the model returns several tool calls in one turn, and when should you disable parallel calls?
  **A:** Execute all of them and return all results together, marking failures with `is_error: true`. Disable parallel calls only when order matters (for example, write a file and then run tests). On Claude, set `disable_parallel_tool_use` inside `tool_choice`.

- **Q:** Which API do you need for tool calling with GPT-6.1 Sol, and what safeguard does every hand-written loop need?
  **A:** The Responses API, because on this model Chat Completions works only without tools. Every loop needs a maximum number of turns so a confused model can't loop (and bill you) forever.

## Quiz

1. Your loop reads only the first `tool_use` block from a Claude response and ignores the rest. Intermittently, the next request fails. What's the most likely cause?
   - a) The model hallucinated a tool name
   - b) The model returned several `tool_use` blocks (parallel calls) and you didn't return a `tool_result` for each
   - c) `max_tokens` was set too high
   <details><summary>Answer</summary>b. Parallel tool use is on by default, and the continuation must include one `tool_result` for every `tool_use` block in the response.</details>

2. A tool raises an exception (a missing order ID). What's the best handling in the loop?
   - a) Let the exception crash the program so you notice
   - b) Silently return an empty string
   - c) Catch it and return a `tool_result` with the error message and `is_error: true`
   <details><summary>Answer</summary>c. The model can then read the error, explain it to the user, or try something else. A crash ends the conversation, and an empty string hides the problem from the model.</details>

3. You have a `write_file` tool and a `run_tests` tool. The model sometimes requests both in one turn, and you execute them with `asyncio.gather`. What's wrong, and what are two fixes?
   - a) Nothing, parallel is always faster
   - b) Tests may run before the file is written, because `gather` gives no ordering guarantee; fix by running the blocks sequentially in order, or by disabling parallel tool use
   - c) The model should be switched to a larger tier
   <details><summary>Answer</summary>b. Side-effecting tools with ordering dependencies shouldn't run concurrently. Run them in order, or set `disable_parallel_tool_use` in `tool_choice` (at the cost of extra turns).</details>

## Go deeper

- [How tool use works](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works) (Anthropic Claude Platform docs, accessed 2026-10-20)
- [Parallel tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use) (Anthropic Claude Platform docs, accessed 2026-10-20)
- [Function calling guide](https://developers.openai.com/api/docs/guides/function-calling) (OpenAI API docs, accessed 2026-10-20)
- [Using GPT-6](https://developers.openai.com/api/docs/guides/latest-model) (OpenAI API docs, accessed 2026-10-20), which covers the Responses requirement and async tool calling

---
⏭️ **Tomorrow:** 🛠️ Build It. We'll take today's loop and wrap it in a gateway that checks permissions and logs every tool call, so an agent can't do more than the user who asked.
