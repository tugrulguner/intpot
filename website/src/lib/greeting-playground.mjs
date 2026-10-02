export function greet(name, excited = false) {
  return `Hello, ${name}${excited ? '!' : ''}`;
}

export function shellQuote(value) {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

export function buildRepresentations(name, excited) {
  return {
    definition: 'def greet(name: str, excited: bool = False) -> str:\n    message = f"Hello, {name}"\n    return f"{message}!" if excited else message',
    cli: `# Start the shipped app as a Typer CLI\nintpot serve examples/semantic_schema.py --cli\n# Generated tool command (illustrative):\ngreet --name ${shellQuote(name)}${excited ? ' --excited' : ''}`,
    http: JSON.stringify({ method: 'POST', path: '/greet', body: { name, excited } }, null, 2),
    mcp: JSON.stringify({ name: 'greet', arguments: { name, excited } }, null, 2),
    result: greet(name, excited),
  };
}
