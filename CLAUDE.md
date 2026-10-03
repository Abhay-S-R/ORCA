## The founding principle — read this first

> **Talk like a chatbot, stay accurate like an instrument.**

ORCA's `/ask` chatbot is the product; everything else exists to serve it.

- **Talk like a chatbot.** A language model *reads* every prompt and *writes*
  every reply, the way a general LLM assistant would. That means it handles typos,
  plurals, shortenings, slang and mixed-language text, and follows context changes
  across turns using the message history. It answers small talk, the clock and
  off-topic messages naturally, in the user's language. A hand-written word list
  is only a fast path or the offline fallback. It never refuses, misroutes or
  silently reinterprets a prompt. A miss is never fixed by adding the missing word
  to a list.
- **Stay accurate like an instrument.** Facts, numbers and the go/no-go safety
  verdict come from the agents, the data and deterministic code, never from the
  model. The model may not invent a place, a date or a value, or change a verdict.
  What the model extracts from a prompt is validated against real data (the
  gazetteer, the forecast horizon, the routing rows) before anything acts on it.

Any defect in how the chatbot reads or answers a prompt is critical and comes
before every other feature fix. The current plan is
`docs/plans/ORCA_Prompt_Routing_Revamp.md`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## The agent account

Agents sign in to the local ORCA app with **one shared account, and only this one**:

```
email:    agent@orca.test
password: orca-agent-local-dev
```

Use it whenever you need to be logged in — verifying a change through `/ask`,
`/map`, `/watches` or any other authenticated surface. **Do not register a new
account**, even a throwaway one: agent signups were accumulating in the `users`
table until 512 rows had to be wiped on 2026-09-22, and the rows are hard to
tell apart afterwards. Devs use throwaway emails and that is fine; agents use
this account so anything an agent leaves behind is attributable and removable
in one statement.

If the login fails because the database was reset, recreate it through the real
endpoint rather than inserting a row directly, so the password hash and the
session rows match what a real signup produces:

```bash
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"identifier":"agent@orca.test","password":"orca-agent-local-dev","display_name":"ORCA Agent","language":"en"}'
```

This credential is deliberately in the repo. It is worth nothing: it only
authenticates against a developer's local Postgres, it holds no data anyone
cares about, and it has the ordinary `user` role. Never reuse this password
anywhere else, and if ORCA is ever deployed somewhere reachable, this account
must not exist there.
