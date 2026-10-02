const MAX_REQUEST = 512;
const LIMITS = { name: 40 };

export function greet(name, excited = false) {
  return `Hello, ${name}${excited ? '!' : ''}`;
}

export function shellQuote(value) {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function validateArgs(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Arguments must be a JSON object.');
  if (Object.keys(value).some((key) => !['name', 'excited'].includes(key))) throw new Error('Only name and excited arguments are allowed.');
  if (typeof value.name !== 'string' || !value.name.trim() || value.name.length > LIMITS.name) throw new Error('name must be a non-empty string of at most 40 characters.');
  if (value.excited !== undefined && typeof value.excited !== 'boolean') throw new Error('excited must be a boolean.');
  return { name: value.name, excited: value.excited ?? false };
}

function tokenizeShell(source) {
  const tokens = [];
  let token = '';
  let started = false;
  let quote = null;
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (quote === "'") {
      if (char === "'") quote = null;
      else token += char;
    } else if (quote === '"') {
      if (char === '"') quote = null;
      else if (char === '\\' && ['$', '`', '"', '\\', '\n'].includes(source[i + 1])) {
        const next = source[++i];
        if (next !== '\n') token += next;
      } else token += char;
    } else if (char === "'" || char === '"') { quote = char; started = true; }
    else if (char === '\\') {
      if (i + 1 === source.length) throw new Error('Trailing shell escape.');
      const next = source[++i];
      if (next !== '\n') { token += next; started = true; }
    } else if (/\s/.test(char)) {
      if (started) { tokens.push(token); token = ''; started = false; }
    } else { token += char; started = true; }
  }
  if (quote) throw new Error('Unclosed shell quote.');
  if (started) tokens.push(token);
  return tokens;
}

export function parseRequest(interfaceName, raw) {
  if (typeof raw !== 'string' || raw.length > MAX_REQUEST) throw new Error('Request must be at most 512 characters.');
  if (interfaceName === 'CLI') {
    const tokens = tokenizeShell(raw);
    if (tokens.shift() !== 'greet') throw new Error('Use the greet command.');
    const name = tokens.shift();
    let excited = false;
    while (tokens.length) {
      const token = tokens.shift();
      if (token === '--excited') excited = true;
      else if (token === '--no-excited') excited = false;
      else throw new Error(`Unsupported CLI argument: ${token}`);
    }
    if (name === undefined || name.startsWith('--')) throw new Error('Provide the required positional name argument.');
    return validateArgs({ name, excited });
  }
  let request;
  try { request = JSON.parse(raw); } catch { throw new Error('Enter valid JSON.'); }
  if (interfaceName === 'HTTP') {
    if (!request || request.method !== 'POST' || request.path !== '/greet') throw new Error('Only POST /greet is supported.');
    return validateArgs(request.body);
  }
  if (interfaceName === 'MCP') {
    if (!request || request.name !== 'greet') throw new Error('Only the greet MCP tool is supported.');
    return validateArgs(request.arguments);
  }
  throw new Error('Unknown interface.');
}

export function runRequest(interfaceName, raw) {
  const args = parseRequest(interfaceName, raw);
  const result = greet(args.name, args.excited);
  const response = interfaceName === 'HTTP' ? { status: 200, body: result } : interfaceName === 'MCP' ? { content: [{ type: 'text', text: result }], structuredContent: { result } } : result;
  return { args, result, response, trace: [`${interfaceName} request parsed`, `Typed arguments: name=${JSON.stringify(args.name)}, excited=${args.excited}`, 'Same function: greet(name, excited)'] };
}

export function defaultRequests(name = 'Ada', excited = false) {
  return {
    CLI: `greet ${shellQuote(name)}${excited ? ' --excited' : ''}`,
    HTTP: JSON.stringify({ method: 'POST', path: '/greet', body: { name, excited } }, null, 2),
    MCP: JSON.stringify({ name: 'greet', arguments: { name, excited } }, null, 2),
  };
}

export const functionDefinition = 'from intpot import App\n\napp = App("schema-example")\n\n@app.tool()\ndef greet(name: str, excited: bool = False) -> str:\n    message = f"Hello, {name}"\n    return f"{message}!" if excited else message';
export const requestLimit = MAX_REQUEST;
