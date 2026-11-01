---
date: 2026-11-01
track: recap
topic: Weekly recap, measure every run and read the fine print
slug: weekly-recap
tags: [recap, streaming, agents, open-weights, evals, pricing, platform-engineering]
read_time: 12 min
---

# 📅 Weekly recap: measure every run and read the fine print

> **TL;DR**
> - Streaming changes when the user sees text, not how long the model takes. A good run log records both time to first token (TTFT) and total cost.
> - Agent loops need the same guards every time (turn cap, stop-reason check, cost counter). Duolingo's answer is to put those guards in a shared platform, so each team only writes the prompt, tools and eval cases.
> - "Open weights" is a spectrum. Mistral Large 4's weights finally shipped, and the licence has a catch you should read before you build on it.

## What it is

This week covered four lessons, from 2026-10-26 to 2026-10-30.

- **Mon 10-26, 🆕 Mistral Large 4:** A roughly 1T-parameter Mixture-of-Experts model. Only about 49B parameters are active per token, but all of them must sit in memory. At the time, the weights were promised but not downloadable.
- **Tue 10-27, 🧱 Streaming responses:** The reply arrives as server-sent events, so users see text at TTFT. Total latency is about the same. Streamed tool arguments are JSON fragments, so don't parse them until the block finishes.
- **Wed 10-28, 🛠️ Streaming agent build:** A tool-using loop with a turn cap, a `stop_reason` check and a per-run cost counter. It uses `get_final_message()` to read complete tool inputs after the live text.
- **Fri 10-30, 💼 Duolingo's agent platform:** Define an agent once and let a shared platform handle durable execution, a model gateway, sandboxes, evals and traces.

**Update on Monday's open question.** Last Monday's lesson said the weights were promised but not out, and the licence wasn't named. That has now resolved, according to several secondary write-ups (I did not find Mistral's own announcement page):

- The weights appeared on Hugging Face on 2026-10-29 as `mistralai/Mistral-Large-4-1T-A52B`. The model card says "52B active". Secondary sources explain that 49B is the count inside the experts, and 52B includes the embedding and output layers.
- The Hugging Face model card names the licence as the **Mistral Ecosystem Open-Weight License**. Secondary write-ups call it a modified MIT licence, with one notable clause. If you operate a "Model as a Service" business, you need a separate commercial licence from Mistral before using the model or derivatives commercially. They quote the licence text, but I haven't read the licence file myself, so read it before relying on this.
- The FP8 checkpoint is reportedly about 1.06 TB and the NVFP4 (4-bit) one about 610 GB. My Monday rule of thumb said about 525 GB for 4-bit, so the real file is bigger. The likely reason is that quantised formats store extra scale values, and some layers stay at higher precision. Treat the rule of thumb as a lower bound.

## Why it matters

The three most important ideas of the week:

- **Measure the run, not just the call.** TTFT is what the user feels, total latency and cost are what the business feels, and `stop_reason` tells you whether the run finished. One log record should hold all of them.
- **Guards belong in code, and in one place.** A turn cap, a stop-reason check and a cost counter are the same for every agent. Duolingo moves them into a platform so that no team has to remember them.
- **"Open" needs fine print.** Check the licence text and the memory footprint. Check that the final release matches the preview you tested, and run your own eval before switching.

## How it works

The week's lessons fit into one picture:

```
 team writes:   prompt + tools + eval cases      (Duolingo: the "agent definition")
                        │
                        ▼
 platform adds: gateway (cost/usage) → loop (turn cap, stop_reason check)
                        │
                        ▼
 model call:    streamed → TTFT, then final message (usage, stop reason)
                        │
                        ▼
 run record:    {ttft, cost, stop, pass?}  → evals, traces, per-team spend
                        │
                        ▼
 model choice:  API vs self-host? (Large 4: MoE memory, licence, hardware bill)
```

Streaming and the gateway both sit at the model call. Streaming controls how the answer is delivered. The gateway controls who pays for it and records what it cost. The loop guards sit between them. The model-choice question at the bottom is the one you answer with your own eval and cost per correct answer, not with a vendor table.

## Try it

**Weekend build:** a mini "agent platform" in about 35 lines. The agent is a plain dict (the definition), and one runner streams the reply, measures TTFT, computes cost and logs a JSONL record. It reuses Wednesday's streaming and cost ideas and Friday's "define once, platform does the plumbing" idea. Afterwards, add Wednesday's tool loop to `run`.

```python
# pip install anthropic
import json, os, time
import anthropic

client = anthropic.Anthropic()                      # reads ANTHROPIC_API_KEY
MODEL = os.environ.get("MODEL", "claude-haiku-5-5")  # confirm the exact ID in the docs
PRICE_IN, PRICE_OUT = 0.10, 0.50                    # $/1M tokens, requests <= 100k tokens

AGENT = {  # the "agent definition": the only part a team writes
    "system": "You are a support agent. Answer in one short sentence. "
              "If you are unsure or it is a legal threat, say 'escalate'.",
    "max_tokens": 4000,  # room for thinking tokens, which count toward the cap
    "cases": [("How do I reset my password?", "reset"),
              ("I will sue you in court!", "escalate")],
}

def run(agent, question):  # the "platform": same for every agent
    t0, ttft, text = time.time(), None, ""
    with client.messages.stream(
        model=MODEL, max_tokens=agent["max_tokens"], system=agent["system"],
        messages=[{"role": "user", "content": question}],
    ) as s:
        for chunk in s.text_stream:
            if ttft is None:
                ttft = time.time() - t0
            text += chunk
        final = s.get_final_message()
    u = final.usage
    cost = (u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6
    return {"q": question, "text": text, "ttft_s": ttft,
            "stop": final.stop_reason, "cost_usd": cost}

with open("runs.jsonl", "a") as log:
    for q, expect in AGENT["cases"]:
        rec = run(AGENT, q)
        rec["pass"] = expect in rec["text"].lower() and rec["stop"] == "end_turn"
        log.write(json.dumps(rec) + "\n")
        print(rec["pass"], f"${rec['cost_usd']:.6f}", rec["ttft_s"], rec["stop"])
```

You should see one line per case with `True` or `False`, a cost of a fraction of a cent, a TTFT in seconds and `end_turn`. Expect TTFT to include some silent thinking time. The substring check is crude on purpose, so replace it with a real grader once you have more cases.

## Where it fits

| | Large model by API (Mistral Large 4) | Self-host the open weights | Cheap small model by API (Haiku 5.5) |
|---|---|---|---|
| Best for | Hard agent tasks with no infrastructure to run | Control, privacy, very high volume | High-volume, simple sub-tasks |
| Cost / licence | Per-token price, no GPUs to manage | Always-on GPU bill plus the Mistral Ecosystem Open-Weight License | $0.10 / $0.50 per 1M tokens up to 100k, higher above |
| Watch out for | The preview and the final weights may behave differently, so re-test | Roughly 0.6–1.1 TB of weights before KV cache, and the Model-as-a-Service clause | The 100k-token price tier and extra tokens per task |

## Flashcards
- **Q:** What happened to Mistral Large 4's open weights, and what is the licence's catch?
  **A:** The weights went up on Hugging Face on 2026-10-29 under the Mistral Ecosystem Open-Weight License, described as a modified MIT licence. Per secondary reports quoting it, anyone operating a "Model as a Service" business needs a separate commercial licence from Mistral. Read the licence file yourself.
- **Q:** Why does Mistral Large 4 show both "49B active" and "52B active"?
  **A:** 49B is the active parameter count inside the experts. 52B also counts the embedding and output layers (per the model card as described in secondary sources). Either way, active parameters set compute per token, and total parameters set memory.
- **Q:** What should one per-run log record contain for a streamed agent?
  **A:** TTFT (what the user feels), total latency, cost from `usage`, the `stop_reason`, and a pass/fail from an objective check. Together they show speed, spend and whether the run actually finished.
- **Q:** Why can a 4-bit memory estimate for a big model come out too low?
  **A:** The rule of thumb is 0.5 bytes per parameter. Real 4-bit checkpoints also store scale values, and some layers likely stay at higher precision. Mistral Large 4's NVFP4 checkpoint is reportedly about 610 GB against a naive 525 GB.
- **Q:** What are the three ideas of the week of 2026-10-26, in one line each?
  **A:** (1) Measure each run: TTFT, cost and stop reason. (2) Put the shared guards (turn cap, gateway, evals) in a platform and let teams write only the agent definition. (3) "Open weights" needs checking: licence text, memory footprint and your own eval.

## Quiz
1. A teammate says streaming will cut the total time of a nine-second answer. What's right?
   - a) Yes, streaming makes the model generate faster
   - b) No, it makes the first words appear sooner but total time is about the same
   - c) Yes, but only for tool calls
   <details><summary>Answer</summary>b, because streaming changes delivery of the same generation. Users feel TTFT, while total latency stays roughly the same.</details>
2. In Duolingo's setup, which of these is the shared platform's job and not the individual team's?
   - a) Writing the prompt
   - b) Choosing the tools for the agent
   - c) Tracking model cost and usage through a gateway
   <details><summary>Answer</summary>c, because cost tracking, durable running, sandboxes and traces are the same for every agent. The prompt, tools and eval cases are what differs per team.</details>
3. You want to run Mistral Large 4's weights for an internal support bot. What does the licence clause reported this week suggest?
   - a) You always need a separate paid licence
   - b) The extra licence requirement targets companies running a Model-as-a-Service business, but read the licence text yourself
   - c) Open weights never have conditions
   <details><summary>Answer</summary>b, because secondary reports say the carve-out is for Model-as-a-Service operators. Licences differ in detail and this isn't legal advice, so check the actual text.</details>

## Go deeper
- [Mistral-Large-4-1T-A52B model card](https://huggingface.co/mistralai/Mistral-Large-4-1T-A52B) (Hugging Face, accessed 2026-11-01). It names the licence. For the clause wording, open the LICENSE file in the repo.
- [Mistral's 1T weights are out, serve it as an API and you need a license](https://dev.to/gabrielanhaia/mistral-large-4s-1t-weights-are-out-serve-it-as-an-api-to-others-and-you-need-a-license-1pkc) (DEV Community, secondary source, accessed 2026-11-01)
- This week's lessons: [Streaming responses](2026-10-27-streaming-responses.md), [Streaming agent loop](2026-10-28-streaming-agent-loop-ttft-cost.md), [Duolingo's agent platform](2026-10-30-duolingo-agent-platform.md)

---
⏭️ **Tomorrow:** 🆕 Monday is New Models day, so expect a fresh release from the last two weeks that you can try the same day.
