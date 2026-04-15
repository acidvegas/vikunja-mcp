# Vikunja MCP

A persistent brain for AI agents.

Vikunja MCP turns a self hosted [Vikunja](https://vikunja.io) instance into long term memory and project management that any AI agent can read and write. It ships an MCP server that gives the agent a small set of tools for storing facts, tracking work, and recalling exactly what it needs when it needs it. Memories live in a real database instead of your prompt, sessions keep their continuity across days and weeks, and your token bill drops because the agent stops dragging yesterday's context into today's conversation.

## Table of Contents
- [What Problem This Solves](#what-problem-this-solves)
- [How It Works](#how-it-works)
- [How Information Is Stored](#how-information-is-stored)
	- [Projects are containers](#projects-are-containers)
	- [Tasks are memory entries](#tasks-are-memory-entries)
	- [Labels are namespaced tags](#labels-are-namespaced-tags)
	- [Buckets are state machines](#buckets-are-state-machines)
	- [The Memory project](#the-memory-project)
	- [Per repository projects](#per-repository-projects)
- [How Information Is Recalled](#how-information-is-recalled)
- [The Instructions Payload](#the-instructions-payload)
- [Setup](#setup)
- [Transports](#transports)
- [Client Configuration](#client-configuration)
- [Usage Patterns](#usage-patterns)
- [Token Savings](#token-savings)
- [Troubleshooting](#troubleshooting)

## What Problem This Solves

AI agents forget. Every new session starts from zero, every long session drags its own transcript into every follow up request, and anything the agent "learned" last week evaporates unless you paste it back in. Two things follow from this:

1. **Session amnesia.** The agent cannot continue yesterday's work. You re explain the project, the constraints, the decisions, the people, the open bugs. Every morning.
2. **Token cost.** Long running context lives inside the prompt. You pay for history you already read, every single turn, forever.

Vikunja MCP fixes both by moving the memory out of the model and into a structured store the model can *query*. Instead of pasting everything you ever told the agent into the system prompt, the agent stores facts once and later asks for the two or three items that are actually relevant to the current question. The storage is Vikunja, the access path is an MCP server, and the shape of what gets stored is not left up to the agent's imagination. See [How Information Is Stored](#how-information-is-stored).

## How It Works

```
                    +-------------------+
                    |     Vikunja       |
                    |  (self hosted)    |
                    +---------+---------+
                              |
                              | HTTP
                              |
                    +---------+---------+
                    |   Vikunja MCP     |
                    +---------+---------+
                              |
                 +------------+------------+
                 |                         |
               stdio                Streamable HTTP
                 |                         |
        +--------+--------+     +----------+----------+
        | Claude Code     |     | Claude Code,        |
        | Claude Desktop  |     | Cursor, Claude      |
        | Cursor          |     | Desktop, modern     |
        | Local LLMs      |     | MCP clients         |
        +-----------------+     +---------------------+
```

The agent speaks MCP. The MCP server speaks the Vikunja REST API. Vikunja stores everything on disk in its own database. Any number of agents *(remote or local, paid or free)* can point at the same MCP server and share the same memory.

Vikunja MCP is a single self-contained Go binary and speaks two MCP transports — stdio for local subprocess use and Streamable HTTP for network clients. Pick whichever your editor or agent supports. See [Transports](#transports) for the details.

## How Information Is Stored

Vikunja already has the right primitives for an agent brain. The MCP just teaches the agent how to use them consistently.

### Projects are containers

A project is a long lived bucket for related memories. Projects do not expire, they do not reset between sessions, and the agent never deletes them. The agent treats projects as the top level of its mental filing cabinet:

| Example project     | What lives inside                                               |
| ------------------- | --------------------------------------------------------------- |
| `Memory`            | General long term facts, preferences, decisions, notes          |
| `my-app-backend`    | Per repository project tracking for a specific codebase         |
| `infrastructure`    | Persistent notes about servers, DNS, certificates, deployments  |
| `people`            | Memories scoped to individuals you work with                    |

You can create any project structure you want. The agent is told to create projects on first use and reuse them forever after.

### Tasks are memory entries

A task in Vikunja has exactly the fields a good memory entry needs:

| Field          | How the agent uses it                                            |
| -------------- | ---------------------------------------------------------------- |
| `title`        | Short headline, acts like a filename for the memory              |
| `description`  | Full markdown body of the memory, can be arbitrarily long        |
| `labels`       | Tags for recall, see the namespace convention below              |
| `priority`     | Importance, 1 to 5                                               |
| `due_date`     | Optional reminder, used for actual todos                         |
| `done`         | Marks a task as resolved or a memory as superseded               |
| `created`      | Automatic timestamp, queryable by date                           |
| `updated`      | Automatic timestamp, queryable by date                           |
| `comments`     | Threaded notes added over time without editing the original body |
| `attachments`  | Binary blobs, screenshots, logs, whatever                        |
| `relations`    | Links to other tasks *(subtask, blocks, related, duplicates)*    |

A "fact the agent remembered" and a "todo the agent is tracking" are both just tasks. The schema is uniform. You never have two kinds of memory to worry about.

### Labels are namespaced tags

Labels are how the agent finds things later. The convention is strict for a reason: if labels are freeform, the agent invents a new variant every session *(`postgres`, `postgresql`, `pg`, `Postgres`)* and nothing is findable. The instructions tell the agent to use a `namespace:value` format so labels cluster into a small vocabulary:

| Namespace  | Example labels                     | Meaning                            |
| ---------- | ---------------------------------- | ---------------------------------- |
| `person`   | `person:alice`, `person:bob`       | Facts tied to a specific human     |
| `topic`    | `topic:postgres`, `topic:docker`   | Technical subject matter           |
| `source`   | `source:slack`, `source:meeting`   | Where the memory came from         |
| `kind`     | `kind:decision`, `kind:fact`       | Shape of the memory                |
| `project`  | `project:mcp`, `project:backend`   | Scope to a specific project        |

You can add your own namespaces. The only rule is that the agent always namespaces labels, never adds bare tags.

### Buckets are state machines

Views and buckets are optional, but for project management they are how the agent tracks work state. A kanban view on a project gets buckets like:

```
Todo  ->  In Progress  ->  Review  ->  Done
                                        |
                                     Blocked
```

The agent moves tasks between buckets as work progresses. Anything in `Done` is historical, anything in `Blocked` is awaiting an external dependency. When you start a new session and ask "what was I working on" the agent filters for tasks not in `Done` and you immediately see the real state of the repo.

### The Memory project

One project called **Memory** holds long term facts that do not belong to any specific repo or initiative. This is the default home for "remember this" style interactions. The agent creates it the first time it is asked to remember anything, then reuses it forever. Memories here are tagged aggressively so recall is precise.

### Per repository projects

For code work, the agent creates one project per code repository, project title = repo name. On first touch it sets up a standard kanban layout and a standard label set so every repo looks the same. Once that is in place you can open any editor, tell the agent "keep going on this repo", and it reads the real todo list out of Vikunja instead of asking you what it should be doing.

## How Information Is Recalled

Storing things is only half the point. The payoff is precise recall that does not bloat the prompt.

The agent reads memories by calling a single tool with a filter expression. The filter language supports the usual operators and runs against every task field:

| Query intent                            | Filter expression *(label IDs are examples)*         |
| --------------------------------------- | ---------------------------------------------------- |
| All open todos in this repo             | `project = 42 && done = false`                       |
| High priority bugs across everything    | `labels in 3,7 && done = false`                      |
| Everything you know about Alice         | `labels = 5`                                         |
| Decisions made in the last month        | `labels = 8 && created > "2026-03-12"`               |
| Anything mentioning postgres            | `title like "postgres" \|\| description like "postgres"` |
| Overdue work                            | `due_date < "now" && done = false`                   |

The agent asks for the narrowest filter it can, pulls the matching 2-5 tasks, and puts only those into its working context. Five tasks of markdown is dozens of tokens, not thousands.

Recall composes with projects and labels naturally. "What do I know about Bob that came up in meetings" resolves those two label names to their numeric ids first, then filters with `labels in 4,9`. "Open p0 bugs in the backend repo" is `project = <id> && labels in 3,7 && done = false`. Label names must always be resolved to numeric ids before use in filter expressions. The agent does not need a search engine because Vikunja's filters are already one.

## The Instructions Payload

The MCP server ships a usage guide as part of the protocol handshake. It is a plain text document sent once when an agent connects, and it becomes part of that agent's system context for the rest of the session. Without this payload the agent would see the tool list and have no idea what conventions to follow. It would invent a new "Memory" project name every session, tag things inconsistently, create duplicate labels, and generally make the store unusable over time.

The instructions teach the agent:

| Section                 | What the agent learns                                                       |
| ----------------------- | --------------------------------------------------------------------------- |
| **Vocabulary**          | What a project, task, label, view, bucket, and filter mean in this context  |
| **Memory conventions**  | The Memory project, tasks as memory entries, namespaced label format        |
| **Per repo conventions**| Project per repo, standard kanban buckets, standard label vocabulary        |
| **Filter syntax**       | Operators, field names, quoted strings, real query examples                 |
| **Lookup flows**        | How to resolve a username to a user id, how to assign a task                |
| **Defaults**            | Priority scale, done semantics, sensible `per_page` values                  |
| **Safety rules**        | Confirm before destructive calls, verify ids before acting on ambiguous ones |

Think of it as a constitution for the agent's interaction with the store. Every agent that connects reads the same rules and therefore produces the same structure, which means memories written by your local LLM on Monday are perfectly readable by Claude Code on Friday. Shared conventions are what makes multi agent memory work.

The payload lives in `instructions.txt` at the repo root. Edit it to customise conventions for your own workflows *(add new label namespaces, change the Memory project name, enforce stricter safety rules)*. Changes take effect on the next MCP client restart.

## Setup

Vikunja MCP is a single Go program. The simplest install is zero install: you point your MCP client at `go run github.com/acidvegas/vikunja-mcp@latest` and pass your Vikunja URL and token through the client's `env` block. The Go toolchain downloads, builds, and runs the server on demand. No repo clone, no virtualenv, no build step.

Requirements:

| Requirement   | Version | Notes                                                      |
| ------------- | ------- | ---------------------------------------------------------- |
| Go            | 1.25+   | Only needed on the machine running the MCP server          |
| Vikunja       | any     | A running Vikunja instance reachable by the MCP server     |
| API token     | —       | Generate in Vikunja under Settings → API Tokens *(`tk_...`)* |

The two environment variables the server always needs:

| Variable        | Required | Description                                 |
| --------------- | -------- | ------------------------------------------- |
| `VIKUNJA_URL`   | yes      | Base URL of your Vikunja server             |
| `VIKUNJA_TOKEN` | yes      | Personal API token *(`tk_...`)*             |

See [Client Configuration](#client-configuration) for the exact `env` shape per client.

**Optional local build.** If you would rather build a binary and run it yourself:

```
git clone https://github.com/acidvegas/vikunja-mcp
cd vikunja-mcp
go build -o vikunja-mcp .
./vikunja-mcp --transport stdio
```

## Transports

Vikunja MCP speaks two MCP transports — pick the one your client supports. stdio is the default, Streamable HTTP is selected with a CLI flag.

| Transport       | Use when                                                                                | Launched by          | Endpoint         |
| --------------- | --------------------------------------------------------------------------------------- | -------------------- | ---------------- |
| stdio           | The client runs the server as a subprocess on the same machine. Zero network exposure. | The MCP client       | stdin / stdout   |
| Streamable HTTP | You want the current MCP HTTP transport. Network accessible, multiple clients share one running daemon. | You, as a daemon     | `http://host:port/` |

stdio is the right default — it requires no daemon, no open ports, and no extra config. Streamable HTTP is what you use when the MCP server is on a different box, when you want multiple agents to share one running process, or when you want the server to persist across client restarts.

**Launching:**
```
go run github.com/acidvegas/vikunja-mcp@latest                                  # stdio (default)
go run github.com/acidvegas/vikunja-mcp@latest -t stdio                         # explicit stdio
go run github.com/acidvegas/vikunja-mcp@latest -t http --host 0.0.0.0 --port 8000
```

Or with a local build:
```
./vikunja-mcp                                      # stdio
./vikunja-mcp -t stdio
./vikunja-mcp -t http --host 0.0.0.0 --port 8000
```

The `http` mode binds on `--host:--port` *(default `127.0.0.1:8000`)*. Flags can also be set via the `VIKUNJA_MCP_TRANSPORT`, `VIKUNJA_MCP_HOST`, and `VIKUNJA_MCP_PORT` environment variables. Both `-t` and `--transport` are accepted.

### Running Streamable HTTP as a systemd service

If you want the network transport to be persistent, run it as a systemd unit. Minimal example *(`/etc/systemd/system/vikunja-mcp.service`)*:
```ini
[Unit]
Description=Vikunja MCP server
After=network-online.target

[Service]
Type=simple
User=vikunja-mcp
WorkingDirectory=/opt/vikunja-mcp
Environment=VIKUNJA_URL=http://localhost:3456
Environment=VIKUNJA_TOKEN=tk_your_token_here
ExecStart=/opt/vikunja-mcp/vikunja-mcp -t http --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then `systemctl enable --now vikunja-mcp` and point your clients at `http://127.0.0.1:8000/`. Put it behind nginx or Caddy with TLS if you expose it beyond localhost.

## Client Configuration

The two transports use different config shapes. stdio clients launch the server as a subprocess (`go run ...` or a local binary). Streamable HTTP clients connect to an already running daemon by URL. Examples below cover Claude Code, Claude Desktop, Cursor, and local LLMs via Continue. The same principles apply to any other MCP client.

### Stdio (recommended)

The client launches the server as a subprocess and talks to it over the pipe. Simplest setup, zero network exposure.

**Claude Code** — one-liner install with `go run`, no clone required:
```
claude mcp add --transport stdio --scope user vikunja \
  --env VIKUNJA_URL=http://localhost:3456 \
  --env VIKUNJA_TOKEN=tk_your_token_here \
  -- go run github.com/acidvegas/vikunja-mcp@latest -t stdio
```

The same setup expressed as a JSON file *(`~/.config/claude-code/mcp.json`)*:
```json
{
	"mcpServers": {
		"vikunja": {
			"command": "go",
			"args": ["run", "github.com/acidvegas/vikunja-mcp@latest", "-t", "stdio"],
			"env": {
				"VIKUNJA_URL": "http://localhost:3456",
				"VIKUNJA_TOKEN": "tk_your_token_here"
			}
		}
	}
}
```

**Claude Desktop** *(`~/.config/Claude/claude_desktop_config.json` on Linux, `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS)*:
```json
{
	"mcpServers": {
		"vikunja": {
			"command": "go",
			"args": ["run", "github.com/acidvegas/vikunja-mcp@latest", "-t", "stdio"],
			"env": {
				"VIKUNJA_URL": "http://localhost:3456",
				"VIKUNJA_TOKEN": "tk_your_token_here"
			}
		}
	}
}
```

**Cursor** *(`~/.cursor/mcp.json`, or the per project `.cursor/mcp.json`)*:
```json
{
	"mcpServers": {
		"vikunja": {
			"command": "go",
			"args": ["run", "github.com/acidvegas/vikunja-mcp@latest", "-t", "stdio"],
			"env": {
				"VIKUNJA_URL": "http://localhost:3456",
				"VIKUNJA_TOKEN": "tk_your_token_here"
			}
		}
	}
}
```

**Local LLM via [Continue](https://continue.dev)** *(VS Code or JetBrains extension with Ollama, LM Studio, llama.cpp, or any OpenAI compatible backend)*. Add to Continue's `config.yaml`:
```yaml
experimental:
  mcpServers:
    - name: vikunja
      command: go
      args:
        - run
        - github.com/acidvegas/vikunja-mcp@latest
        - -t
        - stdio
      env:
        VIKUNJA_URL: http://localhost:3456
        VIKUNJA_TOKEN: tk_your_token_here
```

If you built a local binary instead, replace `command: go` and the `args` with `command: /absolute/path/to/vikunja-mcp` and `args: ["-t", "stdio"]`. Any stdio capable MCP client *(Zed, LM Studio, generic MCP runners)* uses the same `command` + `args` + `env` shape. Restart the client after editing its config.

### Streamable HTTP

Start the daemon, then point the client at its URL. This is the current MCP HTTP transport and is what you should prefer when the client supports it. No subprocess, no environment variables in the client config — the daemon already has `VIKUNJA_URL` and `VIKUNJA_TOKEN` in its own environment.

Start the server once:
```
VIKUNJA_URL=http://localhost:3456 VIKUNJA_TOKEN=tk_your_token_here \
  go run github.com/acidvegas/vikunja-mcp@latest -t http --host 127.0.0.1 --port 8000
```

**Claude Code** *(`~/.config/claude-code/mcp.json`)*:
```json
{
	"mcpServers": {
		"vikunja": {
			"type": "http",
			"url": "http://127.0.0.1:8000/"
		}
	}
}
```

**Claude Desktop** *(`~/.config/Claude/claude_desktop_config.json`)*:
```json
{
	"mcpServers": {
		"vikunja": {
			"type": "streamable-http",
			"url": "http://127.0.0.1:8000/"
		}
	}
}
```

**Cursor** *(`~/.cursor/mcp.json`)*:
```json
{
	"mcpServers": {
		"vikunja": {
			"url": "http://127.0.0.1:8000/"
		}
	}
}
```

**Continue** *(`config.yaml`)*:
```yaml
experimental:
  mcpServers:
    - name: vikunja
      type: streamable-http
      url: http://127.0.0.1:8000/
```

For a local LLM setup where the local model runs on the same box, stdio is still the fastest path *(no TCP overhead, no daemon)*. Use Streamable HTTP when the client and server are on different machines, when multiple clients need to share one running server, or when you want the server to persist across client restarts.

## Usage Patterns

All three patterns use the exact same MCP server. The difference is which agent is on the other end of the connection.

**Claude Code direct.** Register the MCP in Claude Code. When you chat, Claude has the Vikunja tools and calls them whenever the conversation needs memory or project state. Good for deep reasoning, writing code, architecture, anything where you want frontier model quality and also want the agent to have access to persistent memory.

**Local LLM direct.** Register the same MCP in a local LLM client. Ask your local model to do routine memory work *(save this note, list today's tasks, move a card, tag a decision)*. Zero paid tokens, everything runs on your own hardware.

**Hybrid.** Register it in both. Use Claude Code for work that needs a frontier model, use the local LLM for mechanical memory ops. The two agents see the same memories because they both write to the same Vikunja. Facts saved by the local LLM on Monday are findable by Claude Code on Friday. This is where the serious token savings come from: anything routine runs for free, and when Claude Code does run it only touches the memory it actually needs.

## Token Savings

Three compounding effects:

1. **Structured recall instead of context stuffing.** Traditional agent memory pastes a wall of text into the system prompt every turn. With Vikunja MCP the agent filters for the two or three items it actually needs. A user with 500 stored memories can see the difference between 50k tokens per turn and a few hundred.
2. **Session continuity.** Because memory survives across sessions, you stop re explaining yesterday's work every morning. The first message of every session can be "what was I doing" and the answer comes out of Vikunja.
3. **Free labor.** Routine writes and lookups run on your local model. Frontier model sessions stay focused on reasoning, and only touch memory through tool calls instead of holding it in the prompt.

There is no universal savings number because it depends on how memory heavy your workflows already are. The heavier they are, the bigger the win.

---

###### Mirrors: [SuperNETs](https://git.supernets.org/acidvegas/) • [GitHub](https://github.com/acidvegas/) • [GitLab](https://gitlab.com/acidvegas/) • [Codeberg](https://codeberg.org/acidvegas/)
