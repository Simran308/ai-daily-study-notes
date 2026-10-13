---
date: 2026-10-13
track: tech-stack
topic: Structured outputs and JSON schemas
slug: structured-outputs-json-schemas
tags: [structured-outputs, json-schema, pydantic, foundations, tool-use]
read_time: 15 min
---

# 🧱 Structured Outputs and JSON Schemas: Making the Model Return Data, Not Prose

> **TL;DR**
> - A JSON schema is a contract for the shape of the model's reply. With schema-constrained decoding, the API guarantees the reply parses and matches that shape.
> - There are three levels: asking nicely in the prompt, "JSON mode" (valid JSON, any shape), and strict schema enforcement. Use the third whenever code consumes the output.
> - The schema guarantees shape, not truth. A perfectly formatted answer can still be wrong, so keep validating values and keep your evals.

## What it is

Until now, every call we've made returned text. Real applications usually need data: a ticket category, a list of extracted invoice lines, a yes/no flag. The old approach was to write "Reply only with JSON" in the prompt and call `json.loads()` on the result. That works most of the time. The rest of the time you get a markdown fence around the JSON, a missing field, a friendly "Sure! Here's the JSON:", or output cut off mid-object.

**Structured outputs** fix this at the API level. You send a **JSON Schema** (a standard, machine-readable description of an object: its field names, types, which fields are required and which values are allowed) along with your prompt. The provider then constrains generation so the reply fits the schema. Groq's docs describe this as constrained decoding: the model is limited at the token level to outputs that stay valid. OpenAI introduced the idea in August 2024, and Anthropic now offers it too, as do others (Groq, xAI, Cohere, vLLM for self-hosting).

The parameter names differ per provider:

- **OpenAI (Responses API):** put the schema in `text.format` with `type: "json_schema"`, a `name`, the `schema` and `strict: true`. In Chat Completions the same thing lives in `response_format`. OpenAI also offers it on function calling by setting `strict: true` on a tool definition.
- **Anthropic (Messages API):** put the schema in `output_config.format` with `type: "json_schema"` and the `schema`. Claude's docs describe this as "JSON outputs", one of two complementary structured-output features. The other one is outside today's scope.
- **Claude Agent SDK:** pass `output_format` (Python) or `outputFormat` (TypeScript). The final result message then carries a validated `structured_output` field.

## Why it matters

- **Extraction pipelines:** invoices, résumés, contracts or emails go in, typed rows come out for your database, with no regex clean-up step.
- **Classification and routing:** a support-ticket triager returns `category` from a fixed list, so your code can `switch` on it safely.
- **Agents and UIs:** a model's decision ("which tool, which arguments") or a UI payload must parse every time, because one malformed reply can break a whole run or render.

## How it works

There are three levels of "please give me JSON". Each is more reliable than the last.

```
Level 1  Prompt only      "Reply in JSON"           -> may be wrong shape, may not parse
Level 2  JSON mode        type: json_object         -> parses, but any shape
Level 3  Schema enforced  type: json_schema         -> parses AND matches your schema
                          (strict)
```

OpenAI's own docs compare JSON mode and Structured Outputs side by side. JSON mode only asks for valid JSON, while `json_schema` ties the output to your schema.

**Anatomy of a schema.** A schema for a ticket triager looks like this:

```json
{
  "type": "object",
  "properties": {
    "category": {"type": "string", "enum": ["billing", "bug", "feature_request", "other"]},
    "urgent":   {"type": "boolean"},
    "summary":  {"type": "string"}
  },
  "required": ["category", "urgent", "summary"],
  "additionalProperties": false
}
```

Three rules show up across providers:

1. **Every object is closed.** Set `additionalProperties: false`. Claude's docs (as mirrored on Google Cloud) require this for objects, and Groq's strict mode does too.
2. **Strict modes want every field listed as `required`.** Groq's docs say so explicitly, and OpenAI's examples do the same. To make a field optional, allow `null` as one of its types, as in `["string", "null"]`. The field is still present, it just has no value.
3. **Only a subset of JSON Schema works.** OpenAI says so, and Claude's docs list unsupported features. On Claude, numeric limits (`minimum`, `maximum`) and string-length limits are not supported. So "age between 0 and 120" can't be enforced by the decoder. Check the range in your own code afterwards.

**Practical design tips:**

- **Use `enum` for closed choices**, and always include an escape hatch like `"other"` or `"unknown"`. This is the schema version of the "if it isn't there, say `not found`" rule from the prompt-engineering lesson. Without an escape hatch, the model is forced to pick something wrong.
- **Field names and `description` strings act as prompts.** `"urgent"` with the description "true only if the customer states a deadline" will behave better than a bare `"urgent"`.
- **Field order matters.** The model writes fields in order. If you want it to reason first, put a `reasoning` string field before the `answer` field. OpenAI's launch example does exactly this.
- **Keep schemas small and flat.** The first request with a new schema is slower. OpenAI's launch post said that typical schemas took under 10 seconds to process on the first request and complex ones up to a minute, and that the result is cached for later requests. That was in 2024, so treat the numbers as a ballpark and re-measure.

**What the schema does not guarantee:**

- **Truth.** `{"category": "billing"}` is valid even when the ticket is about a bug.
- **Complete output.** If generation hits `max_tokens` the JSON can be cut off. Check `stop_reason` (Claude) or `status` (OpenAI) before parsing. Reasoning tokens count toward the cap, as in the effort benchmark we built last week.
- **Business rules** such as ranges, cross-field consistency, or "this ID exists in our database". Validate these in code.

## Try it

```python
# pip install anthropic openai pydantic
# export ANTHROPIC_API_KEY=... OPENAI_API_KEY=...
import os
from typing import Literal
from anthropic import Anthropic
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid")  # emits additionalProperties: false
    category: Literal["billing", "bug", "feature_request", "other"]
    urgent: bool
    summary: str

TEXT = "I was charged twice for October and my CFO wants it fixed today."
PROMPT = f"Classify this support ticket.\n<ticket>{TEXT}</ticket>"

# 1) Claude: pass a raw JSON schema in output_config.format
msg = Anthropic().messages.create(
    model=os.environ.get("CLAUDE_MODEL", "claude-opus-5-5"),  # swap in a cheaper tier
    max_tokens=1024,
    messages=[{"role": "user", "content": PROMPT}],
    output_config={"format": {"type": "json_schema",
                              "schema": Ticket.model_json_schema()}},
)
print("stop_reason:", msg.stop_reason)  # "max_tokens" would mean truncated JSON
print("Claude:", Ticket.model_validate_json(msg.content[0].text))

# 2) OpenAI: hand the Pydantic class to responses.parse
resp = OpenAI().responses.parse(model="gpt-6.1-sol", input=PROMPT, text_format=Ticket)
print("OpenAI:", resp.output_parsed)
```

You should see two `Ticket` objects printed, most likely `category='billing'` and `urgent=True`, with slightly different summaries. The `ConfigDict(extra="forbid")` line is what makes Pydantic emit `additionalProperties: false`, which Claude requires. The Claude model ID comes from Anthropic's docs example, and I couldn't confirm it against the live model list today, so override it with `CLAUDE_MODEL` if the call errors. The Pydantic validation on the Claude side is deliberate. It gives you a typed object, and a second line of defence if you later switch to a provider or model without strict enforcement.

## Where it fits

| | Schema-enforced structured output | JSON mode | Prompt-only + parse + retry |
|---|---|---|---|
| Best for | Anything your code consumes: extraction, routing, agent payloads | Quick prototypes on providers or models without schema support | Models or providers with no JSON features; one-off scripts |
| Cost / licence | No separate fee in the docs I read. The schema adds input tokens, and the first call with a new schema is slower | Same as normal calls | Retries cost extra calls |
| Watch out for | Only a JSON Schema subset works; truncation at `max_tokens`; shape is guaranteed, truth is not | Valid JSON can still have missing or renamed fields | Failures are rare enough to miss in testing, then happen in production |

If you only need the model to pick from a few options, an `enum` field gets you most of the value with the simplest schema.

## Flashcards
- **Q:** What are the three levels of getting JSON out of an LLM, from weakest to strongest?
  **A:** (1) Ask in the prompt and parse, with no guarantee. (2) JSON mode, which guarantees valid JSON in any shape. (3) Schema-enforced structured output, which guarantees valid JSON that matches your schema.
- **Q:** Where does the schema go in the OpenAI Responses API and in the Claude Messages API?
  **A:** OpenAI: `text.format` with `type: "json_schema"`, `name`, `schema` and `strict: true`. Claude: `output_config.format` with `type: "json_schema"` and `schema`.
- **Q:** What two schema rules do strict structured-output modes commonly require?
  **A:** Every object sets `additionalProperties: false`, and fields are listed as `required`. Make a field optional by allowing `null` as one of its types. Only a subset of JSON Schema is supported.
- **Q:** What does a schema guarantee, and what doesn't it?
  **A:** It guarantees the output parses and has the right fields and types. It does not guarantee the values are correct, complete (truncation at `max_tokens`), or valid under business rules such as number ranges. Claude's structured outputs don't enforce numeric or string-length limits, so validate those in code.
- **Q:** Why add an `"other"` or `"unknown"` value to an enum, and why put a `reasoning` field before `answer`?
  **A:** The escape hatch stops the model being forced into a wrong choice, which is the schema version of the "not found" rule. Fields are generated in order, so a reasoning field first lets the model think before it commits to the answer.

## Quiz
1. Your app calls an LLM in JSON mode (`json_object`) and sometimes crashes with `KeyError: 'category'`. What's the best fix?
   - a) Add "ALWAYS include category" in capital letters to the prompt
   - b) Switch to schema-enforced structured output with `category` in `required`
   - c) Wrap the call in `try/except` and retry up to 10 times
   <details><summary>Answer</summary>b, because JSON mode only guarantees valid JSON, not that your fields exist. A schema with `category` required makes a missing field impossible, and no retry loop is needed. Option a is a prompt-only fix with no guarantee, and c wastes money.</details>
2. A schema says `"age": {"type": "integer", "minimum": 0, "maximum": 120}` and the model returns `"age": 250`. On a provider that doesn't support numeric limits (like Claude), what's the right response?
   - a) File a bug, because the schema was violated
   - b) Expect this and check the range yourself after parsing, for example with a Pydantic validator
   - c) Remove `age` from the schema
   <details><summary>Answer</summary>b, because numeric limits aren't among the enforced constraints on Claude, so the decoder can't stop 250. Shape is enforced and value rules are your job. Always validate business rules in code.</details>
3. You call a reasoning model with structured output and `max_tokens=300`. `json.loads` fails on the reply. What's the most likely cause?
   - a) The schema was too simple
   - b) Reasoning tokens used up the budget and the JSON was truncated
   - c) Structured outputs don't work with reasoning models
   <details><summary>Answer</summary>b, because reasoning tokens count toward the output cap, so a small cap can cut the JSON off. Check `stop_reason` or `status` before parsing, and raise the cap. Strict enforcement guarantees the shape of a finished reply, not that it finished.</details>

## Go deeper
- [Structured outputs, Claude Platform Docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) (Anthropic, accessed 2026-10-13)
- [Structured model outputs, OpenAI API guide](https://developers.openai.com/api/docs/guides/structured-outputs) (OpenAI, accessed 2026-10-13)
- [Introducing Structured Outputs in the API](https://openai.com/index/introducing-structured-outputs-in-the-api/) (OpenAI, 2024-08-06): the original announcement, including first-request latency and limitations
- [Get structured output from agents, Claude Agent SDK docs](https://platform.claude.com/docs/en/agent-sdk/structured-outputs) (Anthropic, accessed 2026-10-13)

---
⏭️ **Tomorrow:** 🛠️ Build It. We'll use today's schema idea to build a small support-ticket triager and score it against a labelled test set, so you can see how often "valid" and "correct" differ.
