#!/usr/bin/env python3
# PyVikunja - Developed by acidvegas in Python (https://git.acid.vegas)
# vikunja/test.py

import asyncio
import json
import os
import sys

from datetime import datetime, timedelta, timezone

try:
	from dotenv import load_dotenv
except ImportError:
	raise ImportError('missing python-dotenv library (pip install python-dotenv)')

try:
	from mcp              import ClientSession, StdioServerParameters
	from mcp.client.stdio import stdio_client
except ImportError:
	raise ImportError('missing mcp library (pip install mcp)')


load_dotenv()

URL   = os.getenv('VIKUNJA_URL', 'http://localhost:3456').rstrip('/')
TOKEN = os.getenv('VIKUNJA_TOKEN', '')

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH = os.path.join(SCRIPT_DIR, 'mcp', 'server.py')

NOW = datetime.now(timezone.utc)


PROJECT_MEMORY = {
	'title':       'Memory',
	'description': 'Long term agent memory. Each task is a single memory entry, tagged with namespaced labels.',
	'hex_color':   '6366f1',
}

PROJECT_REPO = {
	'title':       'pyvikunja',
	'description': 'Per repository project tracking for the PyVikunja codebase.',
	'hex_color':   '10b981',
}

PROJECT_HOME = {
	'title':       'home',
	'description': 'Personal todos and reminders.',
	'hex_color':   'f59e0b',
}


LABELS = {
	'topic:postgres':   '3b82f6',
	'topic:docker':     '3b82f6',
	'topic:auth':       '3b82f6',
	'topic:deployment': '3b82f6',
	'topic:infra':      '3b82f6',
	'person:alice':     'f59e0b',
	'person:bob':       'f59e0b',
	'source:slack':     '6b7280',
	'source:ops':       '6b7280',
	'source:meeting':   '6b7280',
	'kind:fact':        '8b5cf6',
	'kind:decision':    '8b5cf6',
	'kind:preference':  '8b5cf6',
	'kind:reference':   '8b5cf6',
	'bug':              'ef4444',
	'feature':          '10b981',
	'refactor':         '06b6d4',
	'docs':             '3b82f6',
	'chore':            '9ca3af',
	'p0':               'dc2626',
	'p1':               'f59e0b',
	'p2':               'eab308',
}


MEMORIES = [
	{
		'title':       'Postgres maintenance window',
		'description': 'The primary Postgres cluster fails over every Tuesday night at 02:00 UTC for patching. Do not start long migrations during this window.',
		'labels':      ['topic:postgres', 'kind:fact', 'source:ops'],
		'priority':    3,
	},
	{
		'title':       'Alice prefers async communication',
		'description': 'Alice on the backend team prefers async updates in GitHub PR reviews over Slack pings. Batch questions and ping her no more than once a day.',
		'labels':      ['person:alice', 'kind:preference'],
		'priority':    2,
	},
	{
		'title':       'Bob on vacation',
		'description': 'Bob is out of office from 2026-04-20 through 2026-05-02. Do not assign P0 issues to him during this window.',
		'labels':      ['person:bob', 'kind:fact'],
		'priority':    2,
	},
	{
		'title':       'JWT over server sessions',
		'description': 'We chose JWT tokens instead of server side sessions for the REST API. Reasoning: horizontal scaling without a shared session store, cleaner cache semantics. Revisit if token revocation becomes a real concern.',
		'labels':      ['kind:decision', 'topic:auth'],
		'priority':    3,
	},
	{
		'title':       'Staging deploy needs force flag',
		'description': 'The staging deploy script intentionally requires the force flag because of the symlinked config directory. Not a bug. Workaround until the config store migration ships.',
		'labels':      ['topic:deployment', 'kind:fact'],
		'priority':    2,
	},
	{
		'title':       'Oncall Slack channel',
		'description': '#infra-oncall is the primary escalation channel. #general is unmonitored outside business hours. Page via PagerDuty if #infra-oncall is silent for more than 15 minutes on a P0.',
		'labels':      ['source:slack', 'kind:reference'],
		'priority':    2,
	},
	{
		'title':       'Docker socket proxy',
		'description': 'Production hosts run a docker socket proxy at /var/run/docker-proxy.sock. The real docker socket is not exposed. All compose files and automation must target the proxy path.',
		'labels':      ['topic:docker', 'topic:infra', 'kind:fact'],
		'priority':    3,
	},
	{
		'title':       'SSL cert renewal hook',
		'description': 'certbot renews SSL certs automatically via cron but the nginx reload hook is manual. Check /etc/letsencrypt/renewal-hooks/deploy/ after a renewal and reload nginx if needed.',
		'labels':      ['topic:infra', 'kind:fact', 'source:ops'],
		'priority':    3,
	},
]


REPO_TODOS = [
	{
		'title':       'Implement memory search tool',
		'description': 'Add a higher level tool that takes a natural language query and returns the top matching memories. Should wrap get_tasks with a filter expression generator.',
		'labels':      ['feature', 'p1'],
		'priority':    4,
		'done':        False,
	},
	{
		'title':       'Write integration tests for MCP server',
		'description': 'Cover the full tool list against a local Vikunja instance. Use pytest with an async fixture that starts a throwaway Vikunja container.',
		'labels':      ['feature', 'p2'],
		'priority':    3,
		'done':        False,
	},
	{
		'title':       'Document label namespace conventions',
		'description': 'Write a short guide covering person:, topic:, source:, kind: and how to add your own namespaces. Target the README.',
		'labels':      ['docs', 'p2'],
		'priority':    2,
		'done':        False,
	},
	{
		'title':       'Stream responses for large queries',
		'description': 'get_tasks with high per_page values returns a huge JSON blob. Investigate whether the MCP SDK can stream chunks to the client.',
		'labels':      ['feature', 'p2'],
		'priority':    2,
		'done':        False,
	},
	{
		'title':       'Fix path parameter substitution for kind',
		'description': 'The reactions endpoints use a kind path parameter that is not always substituted correctly when the argument is missing. Add a validation step before firing the request.',
		'labels':      ['bug', 'p1'],
		'priority':    4,
		'done':        False,
	},
	{
		'title':       'Spec patch for labels update',
		'description': 'Upstream spec documented PUT /labels/{id} but the server expects POST. Added a patch_spec step to rewrite the operation before build_tools runs.',
		'labels':      ['bug', 'p1'],
		'priority':    4,
		'done':        True,
	},
	{
		'title':       'Initial MCP server scaffolding',
		'description': 'Set up the aiohttp transport, spec loader, tool builder, and stdio entry point.',
		'labels':      ['feature', 'p0'],
		'priority':    5,
		'done':        True,
	},
	{
		'title':       'Add allowlist filter',
		'description': 'Hardcode the curated set of method and path tuples the MCP exposes. Drop everything else at build time.',
		'labels':      ['feature', 'p0'],
		'priority':    5,
		'done':        True,
	},
]


HOME_TODOS = [
	{
		'title':       'Pay electric bill',
		'description': 'Autopay is off. Log in and pay manually.',
		'priority':    4,
		'done':        False,
		'due_offset':  3,
	},
	{
		'title':       'Schedule dentist appointment',
		'description': 'Last cleaning was eight months ago. Overdue.',
		'priority':    2,
		'done':        False,
	},
	{
		'title':       'Buy groceries',
		'description': 'Check the fridge first. Low on eggs and milk.',
		'priority':    3,
		'done':        False,
	},
	{
		'title':       'Renew passport',
		'description': 'Current one expires in October. Apply at least three months ahead.',
		'priority':    3,
		'done':        False,
		'due_offset':  30,
	},
	{
		'title':       'Return library books',
		'description': 'Three books on the shelf, due tomorrow.',
		'priority':    3,
		'done':        False,
		'due_offset':  1,
	},
]


async def call(session, tool: str, **args):
	'''Invoke an MCP tool and return the parsed JSON payload from the response.

	The server wraps every reply as "HTTP {status}\\n{body}". Strip the status
	line, then parse the body as JSON. Raise on non 2xx responses.

	:param session: Open MCP ClientSession
	:param tool: Tool name exposed by the MCP server
	:param args: Keyword arguments forwarded as the tool arguments dict
	'''

	result = await session.call_tool(tool, arguments=args)

	if result.isError:
		text = result.content[0].text if result.content else '<empty>'
		raise RuntimeError(f'mcp tool {tool} failed: {text}')

	if not result.content:
		return None

	text = result.content[0].text

	if text.startswith('HTTP '):
		status_line, _, body = text.partition('\n')
		status = int(status_line.split()[1])

		if status >= 400:
			raise RuntimeError(f'{tool} -> {status_line}\n{body[:400]}')
	else:
		body = text

	if not body.strip():
		return None

	try:
		return json.loads(body)
	except ValueError:
		return body


async def create_task(session, project_id: int, spec: dict, label_map: dict) -> dict:
	'''Create a task through the MCP and attach its labels.

	:param session: Open MCP ClientSession
	:param project_id: Target project identifier
	:param spec: Task definition *(title, description, priority, done, due_offset, labels)*
	:param label_map: Name to label object map built by ensure_labels
	'''

	body = {'title': spec['title'], 'description': spec.get('description', '')}

	if 'priority' in spec:
		body['priority'] = spec['priority']

	if spec.get('done'):
		body['done'] = True

	if 'due_offset' in spec:
		body['due_date'] = (NOW + timedelta(days=spec['due_offset'])).isoformat().replace('+00:00', 'Z')

	task = await call(session, 'put__projects_id_tasks', id=project_id, task=body)

	for name in spec.get('labels', []):
		label = label_map.get(name)
		if label is None:
			continue
		await call(session, 'put__tasks_task_labels', task=task['id'], label={'label_id': label['id']})

	return task


async def ensure_label(session, title: str, hex_color: str) -> dict:
	'''Return an existing label by title, creating it if missing.

	:param session: Open MCP ClientSession
	:param title: Label title
	:param hex_color: Label hex color, six chars without the hash
	'''

	existing = await call(session, 'get__labels', s=title, per_page=50) or []

	for label in existing:
		if label.get('title') == title:
			return label

	return await call(session, 'put__labels', label={'title': title, 'hex_color': hex_color})


async def ensure_labels(session) -> dict:
	'''Ensure every label in LABELS exists and return a name to label map.

	:param session: Open MCP ClientSession
	'''

	result = {}

	for title, color in LABELS.items():
		result[title] = await ensure_label(session, title, color)
		print(f'  label ready: {title}')

	return result


async def ensure_project(session, spec: dict) -> dict:
	'''Return an existing project by title, creating it if missing.

	:param session: Open MCP ClientSession
	:param spec: Project definition *(title, description, hex_color)*
	'''

	existing = await call(session, 'get__projects', s=spec['title'], per_page=50) or []

	for project in existing:
		if project.get('title') == spec['title']:
			return project

	return await call(session, 'put__projects', project=spec)


async def main():
	'''Seed and validate a Vikunja instance through the MCP server end to end.'''

	if not TOKEN:
		print('error: VIKUNJA_TOKEN is not set in .env')
		sys.exit(1)

	if not os.path.isfile(SERVER_PATH):
		print(f'error: mcp server not found at {SERVER_PATH}')
		sys.exit(1)

	print(f'mcp server : {SERVER_PATH}')
	print(f'vikunja    : {URL}')
	print()

	params = StdioServerParameters(
		command = 'python3',
		args    = [SERVER_PATH],
		env     = {**os.environ, 'VIKUNJA_URL': URL, 'VIKUNJA_TOKEN': TOKEN},
	)

	async with stdio_client(params) as (read, write):
		async with ClientSession(read, write) as session:
			init = await session.initialize()
			print(f'connected to : {init.serverInfo.name}')

			listing = await session.list_tools()
			print(f'tools exposed: {len(listing.tools)}')
			print()

			me = await call(session, 'get__user')
			print(f'authenticated as {me["username"]} (id {me["id"]})')
			print()

			print('projects:')
			memory = await ensure_project(session, PROJECT_MEMORY)
			repo   = await ensure_project(session, PROJECT_REPO)
			home   = await ensure_project(session, PROJECT_HOME)
			print(f'  Memory    id={memory["id"]}')
			print(f'  pyvikunja id={repo["id"]}')
			print(f'  home      id={home["id"]}')
			print()

			print('labels:')
			label_map = await ensure_labels(session)
			print()

			print('wiping existing tasks in the seed projects...')
			for pid in (memory['id'], repo['id'], home['id']):
				await wipe_project_tasks(session, pid)
			print()

			print('seeding Memory:')
			for spec in MEMORIES:
				task = await create_task(session, memory['id'], spec, label_map)
				print(f'  {task["id"]:>4}  {spec["title"]}')
			print()

			print('seeding pyvikunja:')
			for spec in REPO_TODOS:
				task   = await create_task(session, repo['id'], spec, label_map)
				status = 'done' if spec.get('done') else 'open'
				print(f'  {task["id"]:>4}  [{status:>4}]  {spec["title"]}')
			print()

			print('seeding home:')
			for spec in HOME_TODOS:
				task = await create_task(session, home['id'], spec, label_map)
				print(f'  {task["id"]:>4}  {spec["title"]}')
			print()

			print('validation queries through the MCP:')
			print()

			postgres_id = label_map['topic:postgres']['id']
			alice_id    = label_map['person:alice']['id']
			decision_id = label_map['kind:decision']['id']
			p0_id       = label_map['p0']['id']
			p1_id       = label_map['p1']['id']

			await validate_query(session, 'memories tagged topic:postgres',
				{'filter': f'labels = {postgres_id}'})

			await validate_query(session, 'memories tagged person:alice',
				{'filter': f'labels = {alice_id}'})

			await validate_query(session, 'decisions recorded in memory',
				{'filter': f'labels = {decision_id}'})

			await validate_query(session, 'open pyvikunja work',
				{'filter': f'project = {repo["id"]} && done = false'})

			await validate_query(session, 'completed pyvikunja work',
				{'filter': f'project = {repo["id"]} && done = true'})

			await validate_query(session, 'open p0 or p1 tasks',
				{'filter': f'labels in {p0_id},{p1_id} && done = false'})

			await validate_query(session, 'title search "postgres"',
				{'filter': 'title like "postgres"'})

			await validate_query(session, 'home todos',
				{'filter': f'project = {home["id"]}'})

			print()
			print('seed and validation complete.')
			print()
			print(f'open {URL} in a browser to inspect the three projects in the web UI.')


async def validate_query(session, label: str, params: dict):
	'''Run a get__tasks query through the MCP and pretty print the hits.

	:param session: Open MCP ClientSession
	:param label: Short human label for the query
	:param params: Arguments forwarded to the get__tasks tool
	'''

	print(f'  {label}')
	print(f'    filter: {params.get("filter", "(none)")}')

	try:
		hits = await call(session, 'get__tasks', **params) or []
	except RuntimeError as e:
		print(f'    error: {e}')
		print()
		return

	if not hits:
		print('    (no matches)')
	else:
		for h in hits:
			print(f'    - [{h.get("id")}] {h.get("title")}')

	print()


async def wipe_project_tasks(session, project_id: int):
	'''Delete every task currently assigned to a project via the MCP.

	:param session: Open MCP ClientSession
	:param project_id: Target project identifier
	'''

	tasks = await call(session, 'get__tasks', per_page=500) or []

	for task in tasks:
		if task.get('project_id') != project_id:
			continue
		try:
			await call(session, 'delete__tasks_id', id=task['id'])
		except RuntimeError:
			pass



if __name__ == '__main__':
	asyncio.run(main())
