---
date: 2026-10-16
track: use-cases
topic: One gateway, act as the user, log everything, the access pattern behind production agents
slug: agent-gateway-act-as-the-user
tags: [use-cases, agents, mcp, security, access-control, airbnb, rippling]
read_time: 15 min
---

# 💼 One Gateway, Act as the User, Log Everything: How Production Agents Get Access to Real Systems

> **TL;DR**
> - Companies that run agents in production tend to give the model one controlled doorway to their systems. Airbnb is reported to route its trust-and-support agents through MCP as the only path, with logging and access control.
> - A second pattern is "act as the user": the agent gets the permissions of the person who asked, never more (Rippling is the example).
> - Limits such as refund caps belong in ordinary code behind the doorway. The model can ask for anything, and the code decides what happens.

> ⚠️ **Verification note.** I could not open the companies' own engineering write-ups when writing this lesson. The company details below come from one secondary roundup (Taskade, 2026-10-07) and I have not checked them against primary sources. I mark them *(unverified)*. The architecture pattern and the code are general and don't depend on those details. Treat the company names as pointers to go and read, not as established facts.

## What it is

Last Friday's lesson ([Stripe's Minions](2026-10-09-stripe-minions-unattended-coding-agents.md)) was about the scaffolding around an agent that writes code. This lesson is about a different question: when an agent can call tools that touch real systems (tickets, payments, customer records), **how does it get access, and who controls that access?**

A roundup published on 2026-10-07 looked at 12 production agent deployments and listed access patterns for several of them. Four are useful for us *(all unverified, from the secondary roundup)*:

- **Airbnb** (trust and support workflows): MCP is described as the only path to about 10 trust systems, with logging and access control.
- **Rippling** (the admin's own Rippling account): the agent takes the role of the user who asks.
- **JPMorgan Chase** (existing systems such as quant models and portfolio tools): the agent uses the bank's own infrastructure, with data kept inside its walls.
- **Anthropic** (a design-tool plugin and a chat app): an MCP server for the ads platform API, plus CSV files of past ads.

Put the first two together and you get a pattern worth naming. I'll call it **gateway + act-as-user + audit log**. Every tool call the model proposes goes through one gateway. The gateway checks it against the permissions of the human on whose behalf the agent is working, enforces business rules, and writes down what happened.

Some jargon, defined once. **MCP (Model Context Protocol)** is an open protocol for exposing tools and data to AI applications. You write an *MCP server* that lists tools, and any MCP-capable *client* (your agent) can discover and call them. We'll do a full MCP lesson on a Tech Stack day. For today, what matters is that it gives you a single, standard place to put access control.

## Why it matters

- **Support and trust teams (Airbnb, per the roundup):** an agent that reads cases and takes actions across about ten internal systems is only safe if there is exactly one audited path to those systems. *(unverified)*
- **HR and payroll admin tools (Rippling, per the roundup):** an agent that inherits the asking admin's permissions can never do something that admin couldn't do by hand. *(unverified)*
- **Regulated industries (JPMorgan Chase, per the roundup):** keeping data inside your own infrastructure is often a legal requirement, so the agent goes to the data and not the other way round. *(unverified)*

The common thread is that none of these designs relies on the model behaving well. That matters because a model can be wrong, can be tricked by text in a ticket (prompt injection, which we will cover later), or can simply misread a request.

## How it works

```
 user (ana) ──asks──▶ agent (LLM)
                         │ proposes: refund(amount=5000)
                         ▼
                ┌─────────────────┐
                │    GATEWAY      │  1. is this a known tool?
                │ (MCP server or  │  2. may *ana* call it?
                │  plain code)    │  3. do business rules pass?
                │                 │  4. write audit log entry
                └───────┬─────────┘
                        │ only if all checks pass
                        ▼
                 real systems (tickets, payments, DB)
        denied? ──▶ error text goes back to the model as the tool result
```

Three design choices carry most of the weight:

1. **One path in.** If the model can only reach your systems through the gateway, you have exactly one place to add checks, rate limits and logging. If there are ten ad-hoc integrations, you have ten places to forget one.
2. **Identity travels with the request.** The gateway checks the permissions of the *human user*, not a powerful shared service account. A shared admin key means that anyone who can talk to the agent effectively has admin rights.
3. **Rules live in code, not in the prompt.** "Never refund more than $100" in a system prompt is a request. The same rule in the gateway is a guarantee. This is the same lesson as Stripe's "tests decide, not the agent", applied to permissions.

An important detail: when the gateway denies a call, return a clear error as the *tool result*. The model can then explain to the user, or escalate to a human, instead of crashing or retrying blindly.

Tradeoffs to be honest about: a gateway adds latency and engineering work, and a strict one makes the agent less capable because it says "no" more often. Logging also means you now store potentially sensitive arguments, so the audit log needs its own retention and access rules.

## Try it

```python
# No pip install needed: standard library only
import json, time

PERMISSIONS = {"ana": {"read_ticket"}, "bo": {"read_ticket", "refund"}}
REFUND_LIMIT = 100  # business rule enforced in code, not in the prompt
AUDIT = []

TOOLS = {
    "read_ticket": lambda a: {"id": a["id"], "status": "open"},
    "refund": lambda a: {"refunded": a["amount"]},
}

def gateway(user, tool, args):
    """The ONLY path from the model to your systems."""
    entry = {"ts": round(time.time()), "user": user, "tool": tool, "args": args}
    try:
        if tool not in TOOLS:
            raise LookupError("unknown tool")
        if tool not in PERMISSIONS.get(user, set()):
            raise PermissionError(f"{user} may not call {tool}")
        if tool == "refund" and args["amount"] > REFUND_LIMIT:
            raise ValueError("amount over limit, needs a human")
        result = TOOLS[tool](args)
        entry["outcome"] = "ok"
    except Exception as e:
        result = {"error": str(e)}  # sent back to the model as the tool result
        entry["outcome"] = f"denied: {e}"
    AUDIT.append(entry)
    return result

# Pretend the model proposed these calls on behalf of different users:
proposed = [("ana", "read_ticket", {"id": 7}), ("ana", "refund", {"amount": 20}),
            ("bo", "refund", {"amount": 20}), ("bo", "refund", {"amount": 5000}),
            ("bo", "delete_db", {})]
for user, tool, args in proposed:
    print(user, tool, "->", gateway(user, tool, args))
print(json.dumps([e["outcome"] for e in AUDIT], indent=1))
```

You should see five lines: Ana can read a ticket but her refund is denied, Bo's $20 refund succeeds, his $5000 refund is denied by the limit, and the made-up `delete_db` tool is rejected. The final JSON list shows one audit outcome per call. I ran this script and the output matched.

To use it with a real model, put `gateway(...)` inside the tool-use loop where you would normally call your tool function directly. Nothing else changes. We'll build that loop properly in the Tool use lesson.

## Where it fits

| | Gateway + act-as-user (this) | Shared service account | Prompt-only rules |
|---|---|---|---|
| Best for | Agents touching real systems with different users | Quick internal prototypes | Demos, tone and format guidance |
| Cost / licence | Engineering time, extra latency per call; MCP is an open protocol | Cheapest to build | Free |
| Watch out for | Gateway bugs become single points of failure; audit logs hold sensitive data | Every user inherits the account's full power | The model can ignore or be talked out of the rules |

## Flashcards
- **Q:** What is the "gateway + act-as-user + audit log" pattern for agents?
  **A:** Every tool call the model proposes goes through one gateway. The gateway checks it against the permissions of the human who asked, enforces business rules in code, and logs the call and its outcome.
- **Q:** Why should an agent act with the asking user's permissions instead of a shared admin account?
  **A:** The agent then can never do more than that user could do by hand. With a shared admin account, anyone who can talk to the agent effectively has admin rights.
- **Q:** Why put a rule like "refunds over $100 need a human" in the gateway code and not only in the system prompt?
  **A:** A prompt rule is a request the model can ignore, misread, or be tricked out of. A code rule is enforced every time, whatever the model says.
- **Q:** What should a gateway return when it denies a tool call?
  **A:** A clear error as the tool result, so the model can explain to the user or escalate to a human instead of crashing or retrying blindly.
- **Q:** According to a 2026-10-07 secondary roundup, how does Airbnb give agents access to its trust systems, and how sure can you be of that?
  **A:** Reportedly MCP is the only path to about 10 trust systems, with logging and access control. It's unverified: the claim comes from a secondary summary, so check Airbnb's own write-up.

## Quiz
1. An agent uses one shared admin API key for every user. What is the main risk?
   - a) The agent will run more slowly
   - b) Any user who can talk to the agent effectively gets admin power
   - c) The model's context window fills up faster
   <details><summary>Answer</summary>b, because the permissions check happens against the key, not the person. Act-as-user fixes this by checking the permissions of whoever asked.</details>
2. Where should the rule "refunds above $100 need human approval" be enforced?
   - a) In the system prompt, in capital letters
   - b) In the few-shot examples
   - c) In the gateway code that executes the tool
   <details><summary>Answer</summary>c, because only code runs every time regardless of what the model outputs. Prompts can still be ignored or overridden by injected text.</details>
3. The model asks for a tool called `delete_db` that doesn't exist. What should the gateway do?
   - a) Reject it, log it, and return an error as the tool result
   - b) Try the closest-named tool
   - c) Ignore it silently so the model doesn't get confused
   <details><summary>Answer</summary>a, because unknown tools should never run, and the log shows you the model tried. A silent drop leaves the model guessing and hides the event from you.</details>

## Go deeper
- [12 Production AI Agents: What They Have in Common](https://www.taskade.com/blog/ai-agent-deployments) (Taskade, 2026-10-07; secondary roundup and the source of the company details above, which I haven't verified against primary sources)
- [Model Context Protocol](https://modelcontextprotocol.io) (official site, accessed 2026-10-16; check its current authorization docs before building a remote server)
- [How Stripe's Minions turn a Slack message into a pull request](2026-10-09-stripe-minions-unattended-coding-agents.md) (earlier lesson in this series, the "scaffolding around the model" idea this builds on)

---
⏭️ **Tomorrow:** 🔁 Saturday review: a spaced-repetition quiz on cards from the past two weeks.
