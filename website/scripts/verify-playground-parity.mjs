import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { defaultRequests, runRequest } from '../src/lib/greeting-playground.mjs';

// Run separately from the Node-only website suite; requires uv sync --all-extras.
const code = `import asyncio, json
from fastapi.testclient import TestClient
from typer.testing import CliRunner
from intpot.runtime_builders import build_fastapi_app, build_typer_app, build_fastmcp_app
from examples.semantic_schema import app, greet
results=[]
for args in [{'name':'Parity','excited':True},{'name':"O'Brien",'excited':False}]:
    http=TestClient(build_fastapi_app(app.name,app._tools)).post('/greet',json=args)
    cli=CliRunner().invoke(build_typer_app(app.name,app._tools),[args['name'],'--excited' if args['excited'] else '--no-excited'])
    mcp=asyncio.run(build_fastmcp_app(app.name,app._tools).call_tool('greet',args))
    results.append({'args':args,'function':greet(**args),'http_status':http.status_code,'http_body':http.json(),'cli_exit':cli.exit_code,'cli_output':cli.stdout.strip(),'mcp':mcp.structured_content['result']})
print(json.dumps(results))`;
const proc = spawnSync(process.env.INTPOT_PARITY_PYTHON ?? '.venv/bin/python', ['-c', code], { cwd: new URL('../../', import.meta.url), encoding: 'utf8' });
assert.equal(proc.status, 0, String(proc.error ?? proc.stderr));
for (const actual of JSON.parse(proc.stdout)) {
  const drafts = defaultRequests(actual.args.name, actual.args.excited);
  assert.equal(actual.cli_exit, 0);
  assert.equal(actual.http_status, 200);
  for (const kind of ['CLI', 'HTTP', 'MCP']) {
    assert.deepEqual(runRequest(kind, drafts[kind]).args, actual.args);
    assert.equal(runRequest(kind, drafts[kind]).result, actual.function);
  }
  assert.equal(actual.cli_output, actual.function);
  assert.equal(actual.http_body, actual.function);
  assert.equal(actual.mcp, actual.function);
}
console.log('Browser-local results match executed Intpot CLI, HTTP and MCP adapters for both input sets.');
