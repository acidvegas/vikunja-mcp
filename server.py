#!/usr/bin/env python3
# PyVikunja - Developed by acidvegas in Python (https://git.acid.vegas)
# vikunja/mcp/server.py

import asyncio
import os
import re

try:
	import aiohttp
except ImportError:
	raise ImportError('missing aiohttp library (pip install aiohttp)')

try:
	from mcp.server       import Server
	from mcp.server.stdio import stdio_server
	from mcp.types        import TextContent, Tool
except ImportError:
	raise ImportError('missing mcp library (pip install mcp)')

try:
	from dotenv import load_dotenv
except ImportError:
	raise ImportError('missing python-dotenv library (pip install python-dotenv)')


load_dotenv()

BASE_URL = os.getenv('VIKUNJA_URL', '').rstrip('/') + '/api/v1'
TOKEN    = os.getenv('VIKUNJA_TOKEN', '')
SPEC_URL = BASE_URL + '/docs.json'
HEADERS  = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/json'}


# Curated allowlist of endpoints the MCP exposes. Anything not in this set is
# dropped at build time. Keeps the tool surface small, predictable, and safe.
ALLOWLIST = frozenset({
	# server / user
	('GET',    '/info'),
	('GET',    '/user'),
	('GET',    '/users'),
	# projects
	('GET',    '/projects'),
	('PUT',    '/projects'),
	('GET',    '/projects/{id}'),
	('POST',   '/projects/{id}'),
	('DELETE', '/projects/{id}'),
	('PUT',    '/projects/{projectID}/duplicate'),
	('GET',    '/projects/{id}/projectusers'),
	# views
	('GET',    '/projects/{project}/views'),
	('PUT',    '/projects/{project}/views'),
	('GET',    '/projects/{project}/views/{id}'),
	('POST',   '/projects/{project}/views/{id}'),
	('DELETE', '/projects/{project}/views/{id}'),
	# buckets
	('GET',    '/projects/{id}/views/{view}/buckets'),
	('PUT',    '/projects/{id}/views/{view}/buckets'),
	('POST',   '/projects/{projectID}/views/{view}/buckets/{bucketID}'),
	('DELETE', '/projects/{projectID}/views/{view}/buckets/{bucketID}'),
	# tasks
	('GET',    '/tasks'),
	('GET',    '/tasks/{id}'),
	('POST',   '/tasks/{id}'),
	('DELETE', '/tasks/{id}'),
	('PUT',    '/projects/{id}/tasks'),
	('POST',   '/tasks/bulk'),
	('POST',   '/tasks/{id}/position'),
	('POST',   '/tasks/{projecttask}/read'),
	('GET',    '/projects/{id}/views/{view}/tasks'),
	('POST',   '/projects/{project}/views/{view}/buckets/{bucket}/tasks'),
	# task relations
	('PUT',    '/tasks/{taskID}/relations'),
	('DELETE', '/tasks/{taskID}/relations/{relationKind}/{otherTaskID}'),
	# assignees
	('GET',    '/tasks/{taskID}/assignees'),
	('PUT',    '/tasks/{taskID}/assignees'),
	('POST',   '/tasks/{taskID}/assignees/bulk'),
	('DELETE', '/tasks/{taskID}/assignees/{userID}'),
	# labels
	('GET',    '/labels'),
	('PUT',    '/labels'),
	('GET',    '/labels/{id}'),
	('POST',   '/labels/{id}'),
	('DELETE', '/labels/{id}'),
	('GET',    '/tasks/{task}/labels'),
	('PUT',    '/tasks/{task}/labels'),
	('DELETE', '/tasks/{task}/labels/{label}'),
	('POST',   '/tasks/{taskID}/labels/bulk'),
	# comments
	('GET',    '/tasks/{taskID}/comments'),
	('GET',    '/tasks/{taskID}/comments/{commentID}'),
	('PUT',    '/tasks/{taskID}/comments'),
	('POST',   '/tasks/{taskID}/comments/{commentID}'),
	('DELETE', '/tasks/{taskID}/comments/{commentID}'),
	# attachments
	('GET',    '/tasks/{id}/attachments'),
	('GET',    '/tasks/{id}/attachments/{attachmentID}'),
	('PUT',    '/tasks/{id}/attachments'),
	('DELETE', '/tasks/{id}/attachments/{attachmentID}'),
	# reactions
	('GET',    '/{kind}/{id}/reactions'),
	('PUT',    '/{kind}/{id}/reactions'),
	('POST',   '/{kind}/{id}/reactions/delete'),
	# filters
	('PUT',    '/filters'),
	('GET',    '/filters/{id}'),
	('POST',   '/filters/{id}'),
	('DELETE', '/filters/{id}'),
	# teams
	('GET',    '/teams'),
	('PUT',    '/teams'),
	('GET',    '/teams/{id}'),
	('POST',   '/teams/{id}'),
	('DELETE', '/teams/{id}'),
	('PUT',    '/teams/{id}/members'),
	('POST',   '/teams/{id}/members/{userID}/admin'),
	('DELETE', '/teams/{id}/members/{username}'),
	# sharing
	('GET',    '/projects/{id}/users'),
	('PUT',    '/projects/{id}/users'),
	('POST',   '/projects/{projectID}/users/{userID}'),
	('DELETE', '/projects/{projectID}/users/{userID}'),
	('GET',    '/projects/{id}/teams'),
	('PUT',    '/projects/{id}/teams'),
	('POST',   '/projects/{projectID}/teams/{teamID}'),
	('DELETE', '/projects/{projectID}/teams/{teamID}'),
	# link shares
	('GET',    '/projects/{project}/shares'),
	('GET',    '/projects/{project}/shares/{share}'),
	('PUT',    '/projects/{project}/shares'),
	('DELETE', '/projects/{project}/shares/{share}'),
	# subscriptions / notifications
	('PUT',    '/subscriptions/{entity}/{entityID}'),
	('DELETE', '/subscriptions/{entity}/{entityID}'),
	('GET',    '/notifications'),
	('POST',   '/notifications'),
	('POST',   '/notifications/{id}'),
	# webhooks
	('GET',    '/projects/{id}/webhooks'),
	('PUT',    '/projects/{id}/webhooks'),
	('POST',   '/projects/{id}/webhooks/{webhookID}'),
	('DELETE', '/projects/{id}/webhooks/{webhookID}'),
	('GET',    '/webhooks/events'),
})


INSTRUCTIONS = '''Vikunja MCP usage guide.

This MCP server is persistent memory and project management for AI agents,
backed by a self hosted Vikunja instance. Follow these conventions exactly so
intents in natural language map cleanly onto API calls and so memories stored
today remain findable tomorrow.

VOCABULARY
  project    container of tasks, for long lived areas (memory, a repo, a life
             area). Create once, reuse forever.
  task       a single unit of work, bug, note, or memory entry. Fields: title,
             description (markdown), done, priority (1-5), due_date, labels,
             assignees, bucket_id, created, updated.
  label      a tag. Cross cutting, reusable across all projects. Labels have
             a numeric id that filters require.
  view       a saved layout for a project (list, kanban, gantt, table).
  bucket     a column inside a kanban view (Todo, In Progress, Done, ...).
  filter     a saved query the user can recall by id.

TAGGING RULES (MANDATORY - BAD TAGS MAKE MEMORY UNREADABLE)

Labels are the primary recall mechanism. Discipline here is non negotiable.

  1. Always namespace labels as "namespace:value". Never use bare tags.
     Good: topic:postgres, person:alice, kind:decision
     Bad:  postgres, alice, decision

  2. Always lowercase the value. "topic:Postgres" and "topic:postgres" are
     two separate labels and will fragment memory.

  3. Before creating a label, search for it first with get__labels s=<prefix>.
     Only create a new label if no match exists. Reuse is the whole point.

  4. Never invent synonyms. Once "topic:postgres" exists, do not create
     "topic:postgresql" or "topic:pg" or "topic:psql". One canonical form
     per concept, forever.

  5. Tag aggressively. Every memory gets two to five labels. A fact about
     Alice using Postgres in a Slack discussion about a deploy decision
     should carry: person:alice, topic:postgres, topic:deployment,
     source:slack, kind:decision. More angles, more recall precision.

  6. Cache label ids within a session. Do not re resolve the same label id
     for every write. Build a local name to id map on first use.

CANONICAL NAMESPACES

  person:<name>    A specific human. Lowercase first name or handle.
                   Examples: person:alice, person:bob, person:acidvegas.

  topic:<thing>    Technical subject matter, tools, concepts, systems.
                   Examples: topic:postgres, topic:docker, topic:auth,
                   topic:deployment, topic:infra, topic:testing.

  source:<where>   Where the memory originated.
                   Examples: source:slack, source:meeting, source:email,
                   source:docs, source:ops, source:user.

  kind:<type>      The shape of the memory entry itself.
                   Examples: kind:fact, kind:decision, kind:preference,
                   kind:reference, kind:question, kind:todo.

  project:<name>   Scope to a specific codebase or initiative.
                   Examples: project:backend, project:mcp, project:website.

  area:<domain>    Broader life or work area.
                   Examples: area:home, area:work, area:learning.

Add new namespaces when you genuinely need one. Keep the format
namespace:value for everything except the universal per repo workflow tags
below.

The following tags are allowed un-namespaced because they are universal and
self explanatory in a repo context: bug, feature, refactor, docs, chore,
breaking, p0, p1, p2. Do not repurpose these names for non code projects.

MEMORY CONVENTIONS (LONG TERM AGENT MEMORY)

  One project titled "Memory" holds every long term fact, decision,
  preference, and reference. Create it on first use if missing. Cache its
  id within the session; do not look it up repeatedly.

  Every memory is a single task:
    title        short headline, like a filename. 3 to 10 words.
    description  full markdown body, arbitrarily long. This is the content.
    labels       two to five tags, following the TAGGING RULES above.
    priority     1-5, default 2. Use 4 or 5 only for truly load bearing info.

  Updates over time: add a comment via put__tasks_taskID_comments rather
  than editing the description. Comments preserve how the memory evolved.

  Superseded memories: set done=true. They stay searchable but are filtered
  out of default "active" queries.

  NEVER store secrets, credentials, tokens, API keys, or private data in
  memory tasks. The store is not encrypted and any agent or human with
  Vikunja access can read it.

PER REPOSITORY PROJECT CONVENTIONS

  One Vikunja project per code repository. Project title must exactly match
  the repo name.

  On first touch for a repo:
    1. get__projects s=<repo_name> to check for an existing project
    2. If missing, put__projects with {"title": "<repo_name>",
       "description": "<repo path or url>"}
    3. Ensure universal workflow labels exist: bug, feature, refactor, docs,
       chore, breaking, p0, p1, p2

  Task workflow:
    - Create tasks via put__projects_id_tasks
    - Every task gets a type label (bug | feature | refactor | docs | chore)
      and a priority label (p0 | p1 | p2)
    - Mark tasks done=true when complete. Never delete them. History matters
    - Record implementation notes via put__tasks_taskID_comments

  Session startup for a repo: call get__tasks with
  filter="project = <id> && done = false" before doing anything else so you
  know what is already in flight.

FILTER SYNTAX (CRITICAL - WRONG SYNTAX RETURNS ERRORS OR NOTHING)

  Operators:  =   !=   >   >=   <   <=   like   in
  Combinators: && (and), || (or). Group with parentheses when mixing.
  Strings are double quoted. Numbers and booleans are bare.

  Valid fields: title, description, done, priority, due_date, start_date,
  end_date, created, updated, labels, assignees, project, bucket_id.

  LABEL FILTERS REQUIRE NUMERIC LABEL IDS.
  You cannot filter by label title directly. Correct flow:
    1. Resolve each tag to its numeric id via get__labels s=<tag>
    2. Filter by id: `labels = 3`
    3. For OR across multiple labels: `labels in 3,5,7`
       (comma separated, NO brackets, NO quotes, NO spaces after commas)

    Wrong:  labels in ["topic:postgres"]
    Wrong:  labels = "topic:postgres"
    Right:  labels = 3
    Right:  labels in 3,5,7

  TEXT SEARCH via `like` against title or description. No % wildcards.
    title like "postgres"
    description like "deployment"

  DATES are RFC3339 strings in double quotes.
    due_date < "2026-04-20" && done = false
    created > "2026-01-01"
  Use filter_timezone=<IANA zone> when a query spans a day boundary.

  COMBINED EXAMPLES
    project = 5 && done = false
    labels = 3 && priority >= 4
    (labels = 3 || labels = 5) && done = false
    title like "postgres" || description like "postgres"
    project = 5 && labels in 8,9 && done = false

WRITE WORKFLOW (STORING A NEW MEMORY)

  1. Decide the tag set using the TAGGING RULES. Aim for 2 to 5 tags.
  2. For each tag, call get__labels s=<tag>. If missing, create it with
     put__labels and a sensible hex_color (topic=3b82f6 blue, person=f59e0b
     amber, kind=8b5cf6 purple, source=6b7280 gray, area=10b981 green).
     Cache id results for the remainder of the session.
  3. Resolve the Memory project id once via get__projects s=Memory.
  4. Call put__projects_id_tasks with id=<memory_project_id> and a task
     body of {title, description, priority}.
  5. For each tag, call put__tasks_task_labels with task=<task_id> and
     body {"label_id": <id>}.
  6. Confirm by echoing the stored title and tag set back to the user.

READ WORKFLOW (RECALLING MEMORIES)

  1. Translate the user question into a candidate tag set.
  2. Resolve each tag to its label id via get__labels (cached when possible).
  3. Build a label id filter: `labels in 3,5,7`. Add `&& done = false`
     unless the user explicitly wants historical entries.
  4. Call get__tasks with that filter and per_page between 5 and 15.
  5. If zero hits, fall back to text search:
     `title like "<keyword>" || description like "<keyword>"`
  6. Surface the top 1 to 3 matches concisely. Do not dump full descriptions
     unless the user asks for detail.

USER AND ASSIGNEE LOOKUP
  Resolve a username to a user id with get__users s=<partial>. Assign via
  put__tasks_taskID_assignees with {"user_id": <id>}.

REACTIONS
  The kind path parameter is "tasks" or "comments". The reaction body is a
  short emoji or keyword string.

DEFAULTS
  priority   1..5, 5 is highest
  hex_color  6 char hex, no leading hash
  done       false by default
  per_page   keep <= 20 unless the user asks for a full dump
  timezone   UTC unless the user specifies otherwise

SAFETY AND IDEMPOTENCY
  - Always check-or-create for projects and labels. A duplicate Memory
    project is a critical failure that splits the agent memory store.
  - Confirm with the user before any destructive call (delete, bulk update,
    removing a label from a task) when the target is ambiguous.
  - Verify ids by reading first when the user intent is vague.
  - Never store secrets, credentials, tokens, or private user data.
  - Endpoints that manage account security, passwords, tokens, deletion,
    migrations, and test fixtures are not exposed by this MCP. Do not try
    to use them.
'''


async def build_tools(spec: dict) -> tuple:
	'''Walk an OpenAPI 2 spec and build an MCP tool list and lookup table.

	Applies the ALLOWLIST filter and patches known Vikunja spec bugs before
	generating tools.

	:param spec: Parsed OpenAPI document
	'''

	patch_spec(spec)

	tools = []
	index = {}

	for path, methods in spec.get('paths', {}).items():
		for method, op in methods.items():
			if method not in ('get', 'post', 'put', 'delete', 'patch'):
				continue

			if (method.upper(), path) not in ALLOWLIST:
				continue

			name = sanitize_name(op.get('operationId') or f'{method}_{path}')
			desc = (op.get('summary') or op.get('description') or f'{method.upper()} {path}').strip()[:1024]
			schema, required = {}, []

			for param in op.get('parameters', []) or []:
				pname = param['name']
				loc   = param.get('in')

				if loc == 'body':
					schema[pname] = {'type': 'object', 'description': f'Request body for {method.upper()} {path}'}
				else:
					schema[pname] = {'type': openapi_to_json(param.get('type', 'string')), 'description': (param.get('description') or f'{loc} parameter').strip()}

				if param.get('required'):
					required.append(pname)

			tools.append(Tool(name=name, description=desc, inputSchema={'type': 'object', 'properties': schema, 'required': required}))
			index[name] = {'method': method.upper(), 'path': path, 'params': op.get('parameters', []) or []}

	return tools, index


async def call_endpoint(session, spec_op: dict, args: dict) -> str:
	'''Execute a Vikunja API call for a single MCP tool invocation.

	:param session: Shared aiohttp client session
	:param spec_op: Operation descriptor from the index returned by build_tools
	:param args: Arguments supplied by the MCP client
	'''

	path  = spec_op['path']
	query = {}
	body  = None

	for param in spec_op['params']:
		pname = param['name']
		if pname not in args or args[pname] is None:
			continue

		loc = param.get('in')

		if loc == 'path':
			path = path.replace('{' + pname + '}', str(args[pname]))
		elif loc == 'query':
			query[pname] = args[pname]
		elif loc == 'body':
			body = args[pname]

	async with session.request(spec_op['method'], BASE_URL + path, params=query or None, json=body, headers=HEADERS) as resp:
		text = await resp.text()

		return f'HTTP {resp.status}\n{text}'


async def load_spec() -> dict:
	'''Fetch the Vikunja OpenAPI document from the running server.'''

	async with aiohttp.ClientSession() as session:
		async with session.get(SPEC_URL) as resp:
			resp.raise_for_status()
			return await resp.json(content_type=None)


async def main():
	'''Start the Vikunja MCP server over stdio.'''

	spec         = await load_spec()
	tools, index = await build_tools(spec)
	server       = Server('vikunja', instructions=INSTRUCTIONS)
	session      = aiohttp.ClientSession()

	@server.list_tools()
	async def _list_tools():
		return tools

	@server.call_tool()
	async def _call_tool(name: str, arguments: dict):
		op = index.get(name)

		if op is None:
			return [TextContent(type='text', text=f'unknown tool: {name}')]

		return [TextContent(type='text', text=await call_endpoint(session, op, arguments or {}))]

	try:
		async with stdio_server() as (read, write):
			await server.run(read, write, server.create_initialization_options())
	finally:
		await session.close()


def openapi_to_json(t: str) -> str:
	'''Map an OpenAPI 2 primitive type to a JSON Schema primitive type.

	:param t: OpenAPI type name *(string, integer, number, boolean, array, file)*
	'''

	return {'integer': 'integer', 'number': 'number', 'boolean': 'boolean', 'array': 'array', 'file': 'string'}.get(t, 'string')


def patch_spec(spec: dict):
	'''Apply known fixes to the upstream Vikunja OpenAPI spec in place.

	Vikunja documents PUT /labels/{id} for label updates but the live server
	returns 405 and only accepts POST /labels/{id}. Rewrite the operation so
	the generated MCP tool matches the real server behaviour.

	:param spec: Parsed OpenAPI document to mutate
	'''

	node = spec.get('paths', {}).get('/labels/{id}')

	if node and 'put' in node and 'post' not in node:
		node['post'] = node.pop('put')


def sanitize_name(raw: str) -> str:
	'''Sanitize an OpenAPI operationId or generated name into an MCP tool name.

	:param raw: Candidate tool name
	'''

	name = re.sub(r'[^a-zA-Z0-9_-]+', '_', raw).strip('_')[:64]

	return name or 'op'



if __name__ == '__main__':
	asyncio.run(main())
