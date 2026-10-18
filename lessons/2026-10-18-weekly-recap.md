---
date: 2026-10-18
track: recap
topic: Weekly recap, guarantees you can check and rules you can enforce
slug: weekly-recap
tags: [recap, structured-outputs, evals, pricing, agents, security]
read_time: 12 min
---

# 📅 Weekly recap: guarantees you can check, rules you can enforce

> **TL;DR**
> - A schema guarantees the *shape* of a model's output, never its truth, so you still need an eval and code-level validation.
> - Judge models by cost per correct answer on your own tasks, and look at the shape of the price curve as well as the headline rate.
> - Anything that must always hold, such as permissions and refund limits, belongs in code around the model, not in the prompt.

## What it is
This recap covers the five lessons from 2026-10-13 to 2026-10-17. The 2026-10-11 recap covered the week before, so it isn't repeated here.

- **Tue 10-13, Structured outputs and JSON schemas:** There are three levels of getting JSON from a model: ask and parse, JSON mode, and schema-enforced output. Only the last guarantees the fields and types match your schema.
- **Wed 10-14, Ticket-triage eval bench:** You build an eval using schema-enforced output and report cost per correct answer. It counts failed calls (truncation, refusals) separately from wrong answers.
- **Thu 10-15, Meta Muse Wonder:** A 1M-context agent model you can only rent. It has flat pricing at any context length and cheap cached input. Weights are not downloadable, and most headline scores are vendor-reported.
- **Fri 10-16, Agent gateway:** Every tool call goes through one gateway. The gateway acts with the asking user's permissions, enforces business rules in code, and logs everything.
- **Sat 10-17, Review:** Eight spaced-repetition cards from weeks one and two.

## Why it matters
The three most important ideas of the week:

- **Shape is not truth.** A schema stops formatting failures, so the mistakes left are real wrong judgements. It does not catch wrong values, truncation at `max_tokens`, or business-rule violations like out-of-range numbers. You validate those in code and measure them with an eval.
- **Measure cost per correct answer, not price per token.** A cheap model that is wrong more often can cost more per correct result. Price *shape* matters too. Haiku 5.5 is cheaper per token but has a step at 100k tokens. Muse Wonder costs more per token but grows in a straight line, and its cached input is 5% of the normal input price.
- **Put hard rules in code, not in the prompt.** A prompt rule is a request the model can ignore, misread, or be tricked out of. A rule in the gateway runs every time. This is the same lesson as last week's Stripe Minions: the model sits in the middle of deterministic scaffolding.

## How it works
The week's ideas fit into one request path. The model proposes an action, and ordinary code checks the shape, the permissions and the policy. An eval measures the whole path.

```
ticket ──► model (schema-enforced output)
              │  proposes: {tool, amount, reasoning}
              ▼
        gateway (plain code)
          ├─ is this tool allowed for THIS user?   → else deny
          ├─ business rule (refund > $100?)        → else escalate
          └─ log proposal + outcome (audit trail)
              ▼
        action runs, or a human takes over

eval harness around everything:
   failed calls (truncation, refusal)  ← config problems
   wrong answers                       ← model-quality problems
   total cost ÷ correct answers        ← the number to compare models on
```

Each piece covers a gap in the others:

- The schema makes the model's proposal parseable.
- The gateway makes it safe to act on.
- The eval tells you whether the model's judgement is good enough, and what it costs.

## Try it
This weekend build combines all three pieces. A support agent proposes one action per ticket as schema-enforced output. A gateway enforces a refund limit in code and writes an audit log. The script prints correct answers, failed calls and cost per correct answer. Here "correct" is judged on the final outcome after the gateway, so you can see a rule in code rescue a model's mistake.

```python
# pip install openai pydantic   (needs OPENAI_API_KEY in your environment)
import json
from typing import Literal
from openai import OpenAI
from pydantic import BaseModel

class Action(BaseModel):
    reasoning: str
    tool: Literal["refund", "reply", "escalate"]
    amount_usd: float | None

USER = {"name": "dana", "can": {"refund", "reply", "escalate"}, "refund_limit": 100}
TICKETS = [
    ("I was charged twice for my $40 plan. Please refund the extra charge.", "refund"),
    ("Your outage cost us $900. We want all of it refunded.", "escalate"),
    ("How do I change my password?", "reply"),
]
client, total_cost, correct, failed = OpenAI(), 0.0, 0, 0

def gateway(a, user):
    if a.tool not in user["can"]:
        return "denied"
    if a.tool == "refund" and (a.amount_usd or 0) > user["refund_limit"]:
        return "escalate"
    return a.tool

for text, expected in TICKETS:
    r = client.responses.parse(model="gpt-6.1-sol", reasoning={"effort": "low"},
        max_output_tokens=2000, input=text, text_format=Action,
        instructions="You are a support agent. Pick one tool. Refund only billing mistakes.")
    total_cost += (r.usage.input_tokens * 2 + r.usage.output_tokens * 10) / 1e6
    a = r.output_parsed
    if a is None:
        failed += 1
        continue
    final = gateway(a, USER)
    correct += final == expected
    with open("audit.jsonl", "a") as f:
        f.write(json.dumps({"user": USER["name"], "proposed": a.model_dump(), "final": final}) + "\n")

print(f"correct={correct}/{len(TICKETS)} failed={failed} cost=${total_cost:.4f}")
print("cost per correct:", total_cost / correct if correct else "n/a")
```

You should see a summary line like `correct=3/3 failed=0` with a cost of a fraction of a cent. `audit.jsonl` gets one line per ticket. The prices in the code are GPT-6.1 Sol's list prices ($2 / $10 per 1M tokens) and ignore cached input, so the cost is slightly overstated. Stretch goals:

- Remove `"refund"` from `USER["can"]` and watch the gateway deny it.
- Grow `TICKETS` to 20 and add a few that tempt the model to over-refund.
- Run the same set at `effort: "high"` and compare cost per correct answer.

## Where it fits
Three ways to make an agent behave, from weakest to strongest:

| | Prompt rule | Schema | Gateway code |
|---|---|---|---|
| Best for | Style, tone, judgement calls | Guaranteed parseable shape and valid labels | Permissions, limits, anything that must always hold |
| Cost / licence | Free, but costs input tokens on every call | Free, with a subset of JSON Schema supported | Normal engineering time |
| Watch out for | The model can ignore or be talked out of it | Doesn't guarantee correct values or business-rule validity | Only protects the calls that actually go through it |

## Flashcards
- **Q:** What does a schema guarantee, and what must you still check yourself?
  **A:** It guarantees that the output parses and has the right fields and types. You still have to check that values are correct, that the output wasn't truncated, and that business rules hold (ranges, limits).
- **Q:** Why compare models on cost per correct answer instead of price per token?
  **A:** Price per token ignores how many tokens a task uses and how often the model is wrong. Cost per correct answer is total cost divided by correct answers, so it captures all three.
- **Q:** How does a flat price curve differ from a tiered one, and why does it matter?
  **A:** With flat pricing (Muse Wonder) cost grows in a straight line with request size. With tiered pricing (Haiku 5.5 above 100k tokens) the rate jumps at a boundary, so you can save money by keeping requests under it.
- **Q:** Why does the gateway check the asking user's permissions instead of the agent's own?
  **A:** The agent then can never do more than that user could do by hand. A shared admin identity would give admin power to anyone who can talk to the agent.
- **Q:** In a triage-plus-gateway eval, why score the final outcome after the gateway, and why track failed calls separately?
  **A:** The final outcome is what the customer actually experiences, and it shows whether code rules rescue model mistakes. Failed calls (truncation, refusals) are config problems, so merging them with wrong answers hides which one to fix.

## Quiz
1. Your structured-output call returns valid JSON that matches the schema, but the refund amount is $900 and your limit is $100. What is the right fix?
   - a) Add "never refund over $100" in capitals to the system prompt
   - b) Check the amount in gateway code and escalate to a human
   - c) Switch to JSON mode for stricter validation
   <details><summary>Answer</summary>b, because a schema only guarantees shape, and a prompt rule can be ignored. A code rule runs every time. JSON mode (c) is weaker than a schema, not stricter.</details>
2. Model A costs $0.30 per run and gets 60% of 100 tasks right. Model B costs $0.50 per run and gets 95% right. Which has the lower cost per correct answer?
   - a) Model A, about $0.50
   - b) Model B, about $0.53
   - c) They are equal
   <details><summary>Answer</summary>a. A: $30 total / 60 correct = $0.50. B: $50 total / 95 correct ≈ $0.53. The gap is smaller than the price gap suggests, so a cheaper model isn't always the cheaper choice. If B's accuracy were slightly higher it would win, so measure both on your own tasks.</details>
3. An eval run shows 8 failures out of 50 calls, and the logs show `status="incomplete"` on the reasoning model. What should you suspect first?
   - a) The model is bad at the task
   - b) `max_output_tokens` is too low, because reasoning tokens count toward the cap
   - c) The schema has too many fields
   <details><summary>Answer</summary>b, because reasoning tokens are billed as output and count toward the cap. A low cap can truncate the visible answer. This is a config problem, not a model-quality problem.</details>

## Go deeper
- [Structured outputs and JSON schemas](2026-10-13-structured-outputs-json-schemas.md) (this course, 2026-10-13)
- [Ticket-triage eval bench](2026-10-14-ticket-triage-eval-bench.md) (this course, 2026-10-14)
- [Agent gateway, act as the user](2026-10-16-agent-gateway-act-as-the-user.md) (this course, 2026-10-16)

---
⏭️ **Tomorrow:** Monday is 🆕 New Models day, so expect a recent release you can try, with its price shape and a cost-per-correct-answer check.
