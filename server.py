#!/usr/bin/env python3
# Vikunja MCP - Developed by acidvegas in Python (https://git.acid.vegas)
# vikunja-mcp/server.py

import argparse
import asyncio
import contextlib
import logging
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

log = logging.getLogger('vikunja-mcp')

_vikunja_url = os.getenv('VIKUNJA_URL', '').rstrip('/')
if not _vikunja_url:
	raise SystemExit('VIKUNJA_URL is not set. Export it or add it to .env')

TOKEN = os.getenv('VIKUNJA_TOKEN', '')
if not TOKEN:
	raise SystemExit('VIKUNJA_TOKEN is not set. Export it or add it to .env')

BASE_URL = _vikunja_url + '/api/v1'
SPEC_URL = BASE_URL + '/docs.json'
HEADERS  = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/json'}

TRANSPORT_CHOICES = ('stdio', 'sse', 'http')
DEFAULT_TRANSPORT = os.getenv('VIKUNJA_MCP_TRANSPORT', 'stdio').lower()
DEFAULT_HOST      = os.getenv('VIKUNJA_MCP_HOST', '127.0.0.1')
DEFAULT_PORT      = int(os.getenv('VIKUNJA_MCP_PORT', '8000'))


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


_instructions_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instructions.txt')
try:
	with open(_instructions_path, 'r') as f:
		INSTRUCTIONS = f.read()
except FileNotFoundError:
	raise SystemExit(f'instructions file not found: {_instructions_path}')


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
				loc = param.get('in')

				if loc == 'body':
					body_schema = resolve_body_schema(param, spec)
					body_schema.setdefault('description', f'Request body for {method.upper()} {path}')
					schema[pname] = body_schema
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

	unresolved = re.findall(r'\{(\w+)\}', path)
	if unresolved:
		msg = f'error: missing required path parameters: {", ".join(unresolved)}'
		log.warning(msg)
		return msg

	async with session.request(spec_op['method'], BASE_URL + path, params=query or None, json=body, headers=HEADERS) as resp:
		text = await resp.text()

		if resp.status >= 400:
			log.warning('%s %s -> HTTP %d', spec_op['method'], path, resp.status)

		return f'HTTP {resp.status}\n{text}'


async def load_spec() -> dict:
	'''Fetch the Vikunja OpenAPI document from the running server.

	Retries up to three times with exponential backoff when the server is
	temporarily unreachable.
	'''

	for attempt in range(3):
		try:
			async with aiohttp.ClientSession() as session:
				async with session.get(SPEC_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
					resp.raise_for_status()
					return await resp.json(content_type=None)
		except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
			if attempt == 2:
				raise
			delay = 2 ** (attempt + 1)
			log.warning('spec load attempt %d failed (%s), retrying in %ds', attempt + 1, exc, delay)
			await asyncio.sleep(delay)


async def build_server() -> tuple:
	'''Build a configured MCP Server instance and its backing aiohttp session.

	Returns a (server, aiohttp_session) tuple. The caller is responsible for
	closing the aiohttp session when the server shuts down.
	'''

	spec         = await load_spec()
	tools, index = await build_tools(spec)
	log.info('loaded %d tools from vikunja spec', len(tools))
	server       = Server('vikunja', instructions=INSTRUCTIONS)
	session      = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

	@server.list_tools()
	async def _list_tools():
		return tools

	@server.call_tool()
	async def _call_tool(name: str, arguments: dict):
		op = index.get(name)

		if op is None:
			log.warning('unknown tool requested: %s', name)
			return [TextContent(type='text', text=f'unknown tool: {name}')]

		log.info('tool call: %s -> %s %s', name, op['method'], op['path'])
		result = await call_endpoint(session, op, arguments or {})
		return [TextContent(type='text', text=result)]

	return server, session


async def run_stdio():
	'''Serve the MCP protocol over stdio.'''

	server, session = await build_server()

	try:
		async with stdio_server() as (read, write):
			await server.run(read, write, server.create_initialization_options())
	finally:
		await session.close()


def run_sse(host: str, port: int):
	'''Serve the MCP protocol over the legacy SSE HTTP transport.

	Exposes two endpoints:
	  GET  /sse       - long-lived Server-Sent Events stream
	  POST /messages/ - client -> server JSON-RPC messages

	:param host: Interface to bind the HTTP server to
	:param port: TCP port to listen on
	'''

	try:
		import uvicorn
		from mcp.server.sse         import SseServerTransport
		from starlette.applications import Starlette
		from starlette.responses    import Response
		from starlette.routing      import Mount, Route
	except ImportError:
		raise ImportError('missing starlette/uvicorn (pip install starlette uvicorn)')

	sse   = SseServerTransport('/messages/')
	state = {}

	class SSEApp:
		async def __call__(self, scope, receive, send):
			server = state['server']
			async with sse.connect_sse(scope, receive, send) as (read, write):
				await server.run(read, write, server.create_initialization_options())

	async def handle_health(_request):
		return Response('ok', media_type='text/plain')

	@contextlib.asynccontextmanager
	async def lifespan(_app):
		server, aio_session = await build_server()
		state['server']     = server
		state['session']    = aio_session
		try:
			yield
		finally:
			await aio_session.close()

	app = Starlette(
		debug=False,
		routes=[
			Route('/sse', endpoint=SSEApp()),
			Route('/health', endpoint=handle_health, methods=['GET']),
			Mount('/messages/', app=sse.handle_post_message),
		],
		lifespan=lifespan,
	)

	uvicorn.run(app, host=host, port=port, log_level='info')


def run_http(host: str, port: int):
	'''Serve the MCP protocol over the Streamable HTTP transport.

	Exposes a single endpoint at /mcp that handles both GET (SSE stream for
	server -> client messages) and POST (client -> server JSON-RPC messages)
	per the current MCP Streamable HTTP spec.

	:param host: Interface to bind the HTTP server to
	:param port: TCP port to listen on
	'''

	try:
		import uvicorn
		from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
		from starlette.applications             import Starlette
		from starlette.responses                import Response
		from starlette.routing                  import Route
	except ImportError:
		raise ImportError('missing starlette/uvicorn (pip install starlette uvicorn)')

	state = {}

	class MCPApp:
		'''ASGI wrapper so Starlette treats this as a mounted app rather than a request handler.'''

		async def __call__(self, scope, receive, send):
			await state['manager'].handle_request(scope, receive, send)

	async def handle_health(_request):
		return Response('ok', media_type='text/plain')

	@contextlib.asynccontextmanager
	async def lifespan(_app):
		server, aio_session = await build_server()
		manager             = StreamableHTTPSessionManager(app=server, event_store=None, json_response=False, stateless=False)
		state['manager']    = manager
		state['session']    = aio_session
		async with manager.run():
			try:
				yield
			finally:
				await aio_session.close()

	app = Starlette(
		debug=False,
		routes=[
			Route('/mcp', endpoint=MCPApp()),
			Route('/health', endpoint=handle_health, methods=['GET']),
		],
		lifespan=lifespan,
	)

	uvicorn.run(app, host=host, port=port, log_level='info')


def parse_args():
	'''Parse CLI arguments for transport selection.'''

	parser = argparse.ArgumentParser(description='Vikunja MCP server', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument('--transport', choices=TRANSPORT_CHOICES, default=DEFAULT_TRANSPORT, help='Transport to expose the MCP server over')
	parser.add_argument('--host',      default=DEFAULT_HOST, help='Host interface for sse and http transports')
	parser.add_argument('--port',      default=DEFAULT_PORT, type=int, help='TCP port for sse and http transports')

	return parser.parse_args()


def main():
	'''Entry point. Dispatch to the selected transport.'''

	logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
	args = parse_args()

	if args.transport == 'stdio':
		asyncio.run(run_stdio())
	elif args.transport == 'sse':
		run_sse(args.host, args.port)
	elif args.transport == 'http':
		run_http(args.host, args.port)


def openapi_to_json(t: str) -> str:
	'''Map an OpenAPI 2 primitive type to a JSON Schema primitive type.

	:param t: OpenAPI type name *(string, integer, number, boolean, array, file)*
	'''

	return {'integer': 'integer', 'number': 'number', 'boolean': 'boolean', 'array': 'array', 'file': 'string'}.get(t, 'string')


def resolve_ref(spec: dict, ref: str) -> dict:
	'''Follow a JSON Reference pointer inside an OpenAPI spec.

	:param spec: Full OpenAPI document
	:param ref: Reference string, e.g. "#/definitions/models.Task"
	'''

	node = spec
	for part in ref.lstrip('#/').split('/'):
		node = node.get(part, {})
	return node


def resolve_body_schema(param: dict, spec: dict) -> dict:
	'''Build a JSON Schema dict for a body parameter, resolving $ref when present.

	Extracts top-level property names and types from the referenced definition
	so the LLM knows what fields to include in the request body.

	:param param: OpenAPI body parameter object
	:param spec: Full OpenAPI document for $ref resolution
	'''

	schema = param.get('schema', {})
	if '$ref' in schema:
		schema = resolve_ref(spec, schema['$ref'])

	if schema.get('type') != 'object' or 'properties' not in schema:
		return {'type': 'object'}

	props = {}
	for name, prop in schema.get('properties', {}).items():
		entry = {'type': openapi_to_json(prop.get('type', 'string'))}
		if 'description' in prop:
			entry['description'] = prop['description'].strip()
		if prop.get('type') == 'array' and 'items' in prop:
			items = prop['items']
			if '$ref' in items:
				items = resolve_ref(spec, items['$ref'])
			entry['items'] = {'type': openapi_to_json(items.get('type', 'string'))}
		props[name] = entry

	return {'type': 'object', 'properties': props}


SPEC_PATCHES = [
	('/labels/{id}', 'put', 'post'),
]


def patch_spec(spec: dict):
	'''Apply known fixes to the upstream Vikunja OpenAPI spec in place.

	Each entry in SPEC_PATCHES is a (path, wrong_method, correct_method) tuple.
	The operation is moved from the wrong method to the correct one only when
	the correct method is not already present.

	:param spec: Parsed OpenAPI document to mutate
	'''

	paths = spec.get('paths', {})
	for path, wrong, correct in SPEC_PATCHES:
		node = paths.get(path)
		if node and wrong in node and correct not in node:
			node[correct] = node.pop(wrong)
			log.info('spec patch: %s %s -> %s', path, wrong.upper(), correct.upper())


def sanitize_name(raw: str) -> str:
	'''Sanitize an OpenAPI operationId or generated name into an MCP tool name.

	:param raw: Candidate tool name
	'''

	name = re.sub(r'[^a-zA-Z0-9_-]+', '_', raw).strip('_')[:64]

	return name or 'op'



if __name__ == '__main__':
	main()
