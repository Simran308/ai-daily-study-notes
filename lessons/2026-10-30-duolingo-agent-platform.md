---
date: 2026-10-30
track: use-cases
topic: Duolingo's shared agent platform, define the agent once and let the platform do the plumbing
slug: duolingo-agent-platform
tags: [use-cases, agents, platform-engineering, evals, llm-gateway, temporal, duolingo]
read_time: 15 min
---

# 💼 Stop Rebuilding the Agent Plumbing: Duolingo's Shared Agent Platform

> **TL;DR**
> - Duolingo's engineers found that every team building an agent was rebuilding the same infrastructure. So they made a platform where a team defines an agent once, and the platform handles running it, watching it, orchestrating it and evaluating it.
> - The model call is the small part. The durable run, the cost-tracking gateway and the evals are the platform.
> - Evals use cheap deterministic checks first, with an optional LLM judge on top. They don't rely on one model grading another.

## What it is

On 2026-08-04, Duolingo's engineering blog published "Making production-ready agents the default: building Duolingo's agent platform". It is about three months old, so this is not a news item. It is a case study of a pattern you will meet in most companies once more than one team builds agents.

The problem it describes is familiar. Getting an agent to work on a laptop is mostly prompting. Running it in the cloud turns it into a productionizing problem, and the post lists the surrounding work: setting up MCP servers, preparing credentials, cloning repositories and more. Duolingo's TL;DR says teams kept rebuilding this same infrastructure. Their fix was a shared platform. A developer defines an agent once, and the platform handles execution, observability, orchestration and evaluation.

The post names some of the pieces. It uses Temporal and the OpenAI Agents SDK, plus reusable workflows. The runner calls the model through an LLM provider SDK, going via an internal LLM Gateway that provides cost tracking, usage tracking and provider abstraction. On evals, the post says exact diff assertions can be too brittle, so there is an optional LLM-as-judge. It also says they don't want one model judging another's work to be the only signal. Evals get the same durability properties as production agent runs.

**What I could and couldn't verify.** I could read search snippets of the post, not the full text. The facts above come from those snippets. The diff assertions suggest coding-style agents, but I haven't confirmed that. Everything in "How it works" below is a generic version of the pattern, not Duolingo's exact design. Read the original before you quote any detail.

## Why it matters

- **Duolingo:** a new team gets execution, logging, cost tracking and evals by writing an agent definition. It doesn't have to build them.
- **Uber:** the company reported in late August 2026 that it has built 3,600+ agent skills and runs 30,000+ skill executions per day. Weekly agent requests grew 9.4x from February to mid-August, while total AI spend has been roughly stable since April, according to its engineering blog. At that volume, shared infrastructure and shared cost tracking are what make growth survivable.
- **Your own company:** the second team to build an agent will otherwise copy the first team's glue code, and each copy will drift. A small shared module is the first step towards a platform.

## How it works

The core idea is to split an agent into the part that is different for each team and the part that is the same every time.

```
 Team writes (small, declarative)            Platform provides (shared, boring)
┌───────────────────────────────┐          ┌──────────────────────────────────────┐
│ AgentSpec:                    │          │ Runner     durable steps, retries     │
│  - name, owner team           │ ───────► │ Gateway    one door to the model:     │
│  - system prompt              │          │            cost, usage, provider swap │
│  - tools / skills             │          │ Sandbox    credentials, repo, MCP     │
│  - eval cases                 │          │ Evals      same runner as production  │
└───────────────────────────────┘          │ Traces     what happened, per run     │
                                           └──────────────────────────────────────┘
```

Four ideas carry most of the weight:

1. **Durable execution.** Temporal is a workflow engine. It records each step of a run as it completes, so a crashed or restarted run resumes from the last finished step instead of starting over. (This is a general description of Temporal, not a detail from the post.) Agent runs are long and expensive, so losing one at step 14 hurts.
2. **A gateway for every model call.** One internal door means every call is counted per team and per agent. It also means you can swap providers in one place. This is the same shape as the access gateway from the 2026-10-16 lesson, but it controls cost and routing instead of permissions.
3. **Evals run the way production runs.** If an eval executes in a different, simpler way than the real agent, a pass tells you less. Running evals on the same durable runner means a pass is evidence about the real system.
4. **Layered grading.** Start with deterministic checks (does the output match, parse or pass the tests?). They are cheap, repeatable and not fooled by confident prose. Add an LLM judge only where exact matching is too brittle, and keep a non-model signal beside it. You covered the judge's weaknesses in the eval lessons. Here it is a second opinion, not the referee.

## Try it

This is a toy version of the platform's skeleton: an agent as data, one gateway function that records cost, and an eval runner that grades with plain code. It has no durable execution and no tools. It only shows where each responsibility lives.

```python
# pip install anthropic   (set ANTHROPIC_API_KEY and LLM_MODEL, the model ID from your console)
import os, time
from dataclasses import dataclass
import anthropic

client = anthropic.Anthropic()
MODEL = os.environ["LLM_MODEL"]
PRICE_IN = float(os.environ.get("PRICE_IN", "0.10"))    # $ per 1M input tokens
PRICE_OUT = float(os.environ.get("PRICE_OUT", "0.50"))  # $ per 1M output tokens
LEDGER = []                                             # the gateway's usage log

@dataclass
class AgentSpec:            # the only thing a team writes
    name: str
    team: str
    system: str

def gateway_call(spec, user_text):
    t0 = time.time()
    r = client.messages.create(model=MODEL, max_tokens=4000, system=spec.system,
                               messages=[{"role": "user", "content": user_text}])
    cost = (r.usage.input_tokens * PRICE_IN + r.usage.output_tokens * PRICE_OUT) / 1e6
    LEDGER.append({"agent": spec.name, "team": spec.team, "cost": cost, "secs": time.time() - t0})
    return "".join(b.text for b in r.content if b.type == "text")

def run_evals(spec, cases):  # the platform's job: run every case, grade it, report cost
    passed = 0
    for text, check in cases:
        ok = check(gateway_call(spec, text))
        passed += ok
        print("PASS" if ok else "FAIL", repr(text[:40]))
    spent = sum(e["cost"] for e in LEDGER if e["agent"] == spec.name)
    print(f"{passed}/{len(cases)} passed, ${spent:.5f} total, ${spent / max(passed, 1):.5f} per pass")

headline = AgentSpec("headliner", "docs", "Rewrite the user's text as a headline of at most 8 words. Reply with the headline only.")
cases = [("Our team shipped a new billing page after months of work on invoices", lambda o: len(o.split()) <= 8),
         ("Tell me about our refund policy in a long and rambling way", lambda o: not o.endswith("."))]
run_evals(headline, cases)
```

You should see one PASS or FAIL line per case, then a summary such as `2/2 passed` with a total cost of a fraction of a cent. The default prices are Claude Haiku 5.5's list prices from the 2026-10-08 lesson. Override them with `PRICE_IN` and `PRICE_OUT` if you use another model. I ran the logic against a stub client, not the live API, so check the model ID in your console. Stretch goal: add a second `AgentSpec` and print the `LEDGER` grouped by `team`. That is the seed of Duolingo-style cost tracking.

## Where it fits

| | Shared agent platform | Each team builds its own | Framework only (SDK, no platform) |
|---|---|---|---|
| Best for | Many teams, many agents, a need for consistent cost, logs and evals | One agent, one team, a prototype | A single well-scoped agent where the SDK covers the needs |
| Cost / licence | Platform-team time up front; per-call cost visible per team | Cheapest on day one, then duplicated work | Free SDKs plus your own glue |
| Watch out for | Building it too early, or making the spec so rigid that teams work around it | Drifting copies, no shared cost view, inconsistent safety rules | The SDK runs the loop but doesn't give you durable runs, a gateway or evals |

## Flashcards
- **Q:** What problem did Duolingo's agent platform solve?
  **A:** Teams building agents kept rebuilding the same surrounding infrastructure. In the platform a developer defines an agent once, and the platform handles execution, observability, orchestration and evaluation.
- **Q:** Which parts of an agent are team-specific, and which belong in a shared platform?
  **A:** Team-specific: the prompt, tools and eval cases. Shared: durable running, a model gateway with cost and usage tracking, sandbox and credentials setup, evals and traces.
- **Q:** What does a durable-execution engine like Temporal give an agent run?
  **A:** Each completed step is recorded, so a crashed or restarted run resumes from the last finished step instead of starting over. That matters for long, paid runs.
- **Q:** What does routing every model call through an internal LLM gateway buy you?
  **A:** Per-team cost and usage tracking, plus the ability to swap providers in one place. Duolingo's gateway is described as providing cost tracking, usage tracking and provider abstraction.
- **Q:** Why layer evals as deterministic checks first and an LLM judge second?
  **A:** Deterministic checks are cheap, repeatable and can't be charmed by fluent text. Use a judge only where exact matching is too brittle, and don't let one model grading another be your only signal.

## Quiz
1. A second team asks to build an agent, and you notice the first team's code handles credentials, retries and cost logging. What's the best next step?
   - a) Let the second team copy it so they ship fast
   - b) Pull the shared parts into one module or service and let each team supply only its prompt, tools and eval cases
   - c) Ban the second team from building agents until a full platform exists
   <details><summary>Answer</summary>b. Extract the repeated plumbing, which is the pattern Duolingo describes, but start small. Copying creates drifting duplicates (a), and waiting for a perfect platform (c) is the over-building trap.</details>
2. Why run evals on the same durable runner as production agents?
   - a) It makes the evals cheaper
   - b) A pass then reflects how the real system behaves, rather than a simpler test harness
   - c) It removes the need for deterministic checks
   <details><summary>Answer</summary>b. If evals run through a different path, a pass may not carry over to production. Same-runner evals also inherit the durability of real runs. Evals aren't automatically cheaper, and they still need deterministic checks.</details>
3. Your eval uses only an LLM judge to grade outputs. What is the main risk, and what is the fix?
   - a) The judge can be wrong or biased in ways no one notices, so add deterministic checks (tests, exact or parsed matches) beside it
   - b) The judge is too slow, so switch to a bigger model
   - c) The judge only works on short outputs, so truncate the outputs
   <details><summary>Answer</summary>a. One model grading another can share its blind spots. Deterministic signals are an independent check, which is why Duolingo keeps the judge optional and not the only signal.</details>

## Go deeper
- [Making production-ready agents the default: building Duolingo's agent platform](https://blog.duolingo.com/production-ready-ai-agent-platform/) (Duolingo Engineering, 2026-08-04). Primary source. I only read excerpts, so check the details here.
- [Running a Software Factory Efficiently at Uber Scale](https://www.uber.com/us/en/blog/efficient-software-factory/) (Uber Engineering, August 2026). Primary source for the Uber scale and spend numbers. Secondary summaries gave 27 and 29 August as the date, so confirm it on the page.
- [Designing MCP Gateway: Uber's MCP Management Platform](https://www.uber.com/us/en/blog/designing-mcp-gateway/) (Uber Engineering, 2026-10-01). The access-control side of the same shared-platform idea, which pairs with the 2026-10-16 lesson.

---
⏭️ **Tomorrow:** 🔁 Saturday review. Eight flashcards from the past four weeks, including this week's streaming and gateway cards.
