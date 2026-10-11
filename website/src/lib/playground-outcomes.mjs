const PROJECTS = new Set(['dexpot', 'intpot', 'summonpot']);
const MODES = new Set(['crud', 'CLI', 'HTTP', 'MCP', 'bounded-operation']);
const RESULTS = new Set(['success', 'rejected', 'failed']);
const FAILURE_CLASSES = new Set(['validation', 'not_found', 'capacity', 'execution', 'cancelled']);
export function createOutcomeTracker(project, capture, createId = () => globalThis.crypto.randomUUID()) {
  if (!PROJECTS.has(project)) throw new TypeError('Invalid project');
  if (typeof capture !== 'function') throw new TypeError('capture must be a function');
  const active = new WeakSet();
  return {
    start(mode) {
      if (!MODES.has(mode)) throw new TypeError('Invalid mode');
      const attempt = Object.freeze({ id: createId(), mode }); active.add(attempt);
      capture('playground_preview_started', { project, mode, attempt_id: attempt.id }); return attempt;
    },
    complete(attempt, result, failureClass) {
      if (!attempt || !active.has(attempt)) return false;
      if (!RESULTS.has(result)) throw new TypeError('Invalid result');
      if ((result === 'success') !== (failureClass === undefined)) throw new TypeError('Invalid failure class for result');
      if (failureClass !== undefined && !FAILURE_CLASSES.has(failureClass)) throw new TypeError('Invalid failure class');
      active.delete(attempt);
      capture('playground_preview_completed', { project, mode: attempt.mode, attempt_id: attempt.id, result, ...(failureClass ? { failure_class: failureClass } : {}) }); return true;
    },
  };
}
