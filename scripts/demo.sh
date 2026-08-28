#!/usr/bin/env bash
# ============================================================
# intpot full demo — run all conversions & scaffolding
#
# Usage:  bash scripts/demo.sh              (prints + saves to examples/conversions/)
#         bash scripts/demo.sh --no-save   (print only, don't write files)
# ============================================================

set -euo pipefail

# Ensure all extras (fastmcp, fastapi) are installed
uv sync --all-extras --quiet 2>/dev/null

SAVE=true
[[ "${1:-}" == "--no-save" ]] && SAVE=false

BLUE='\033[1;34m'
GREEN='\033[1;32m'
CYAN='\033[0;36m'
RESET='\033[0m'

OUTDIR="examples/conversions"
mkdir -p "$OUTDIR"

run() {
    local label="$1"
    local cmd="$2"
    local outfile="${3:-}"

    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${GREEN}  $label${RESET}"
    echo -e "${CYAN}  \$ $cmd${RESET}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

    if $SAVE && [[ -n "$outfile" ]]; then
        eval "$cmd" 2>/dev/null | tee "$outfile"
        echo -e "${CYAN}  → saved to $outfile${RESET}"
    else
        eval "$cmd" 2>/dev/null
    fi
}

expect_failure() {
    local label="$1"
    local cmd="$2"

    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${GREEN}  $label${RESET}"
    echo -e "${CYAN}  $ $cmd${RESET}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

    set +e
    local output
    output=$(eval "$cmd" 2>&1)
    local status=$?
    set -e
    printf '%s\n' "$output"
    if [[ $status -eq 0 ]] || [[ "$output" != *"Cannot convert FastAPI dependencies"* ]]; then
        echo "Expected an actionable FastAPI dependency rejection." >&2
        return 1
    fi
}

echo -e "${GREEN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║         intpot — full conversion demo        ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${RESET}"

# ============================================================
# 1. Basic examples (existing)
# ============================================================

run "MCP → CLI  (basic)" \
    "uv run intpot to cli examples/mcp_server.py" \
    "$OUTDIR/mcp_to_cli.py"

run "MCP → API  (basic)" \
    "uv run intpot to api examples/mcp_server.py" \
    "$OUTDIR/mcp_to_api.py"

run "CLI → MCP  (basic)" \
    "uv run intpot to mcp examples/cli_app.py" \
    "$OUTDIR/cli_to_mcp.py"

run "CLI → API  (basic)" \
    "uv run intpot to api examples/cli_app.py" \
    "$OUTDIR/cli_to_api.py"

run "API → CLI  (basic)" \
    "uv run intpot to cli examples/api_app.py" \
    "$OUTDIR/api_to_cli.py"

run "API → MCP  (basic)" \
    "uv run intpot to mcp examples/api_app.py" \
    "$OUTDIR/api_to_mcp.py"

# ============================================================
# 2. Advanced examples (realistic apps)
# ============================================================

run "Advanced CLI → MCP  (task manager with json, multiple commands)" \
    "uv run intpot to mcp examples/advanced_cli.py" \
    "$OUTDIR/advanced_cli_to_mcp.py"

run "Advanced CLI → API  (task manager)" \
    "uv run intpot to api examples/advanced_cli.py" \
    "$OUTDIR/advanced_cli_to_api.py"

run "Advanced MCP → CLI  (notes server with hashlib, datetime, async)" \
    "uv run intpot to cli examples/advanced_mcp.py" \
    "$OUTDIR/advanced_mcp_to_cli.py"

run "Advanced MCP → API  (notes server)" \
    "uv run intpot to api examples/advanced_mcp.py" \
    "$OUTDIR/advanced_mcp_to_api.py"

run "Advanced API → CLI  (user management)" \
    "uv run intpot to cli examples/advanced_api.py" \
    "$OUTDIR/advanced_api_to_cli.py"

run "Advanced API → MCP  (user management)" \
    "uv run intpot to mcp examples/advanced_api.py" \
    "$OUTDIR/advanced_api_to_mcp.py"

expect_failure "Dependency API → CLI  (Depends is rejected safely)" \
    "uv run intpot to cli examples/dependency_api.py"

expect_failure "Dependency API → MCP  (Depends is rejected safely)" \
    "uv run intpot to mcp examples/dependency_api.py"

run "Execute checked-in generated examples" \
    "uv run python scripts/verify_generated_examples.py"

# ============================================================
# 3. Scaffolding
# ============================================================

TMPDIR=$(mktemp -d)
PROJDIR="$(pwd)"
trap "rm -rf $TMPDIR" EXIT

run "Scaffold MCP project" \
    "cd $TMPDIR && uv run --project $PROJDIR intpot init my-mcp-server --type mcp && cat my-mcp-server/server.py"

run "Scaffold CLI project" \
    "cd $TMPDIR && uv run --project $PROJDIR intpot init my-cli-app --type cli && cat my-cli-app/main.py"

run "Scaffold API project" \
    "cd $TMPDIR && uv run --project $PROJDIR intpot init my-api --type api && cat my-api/main.py"

# ============================================================
# 4. Directory auto-discovery
# ============================================================

expect_failure "Directory scan → CLI  (fails atomically on dependency_api.py)" \
    "cd $PROJDIR && uv run intpot to cli examples/"

# ============================================================
# Done
# ============================================================

echo ""
echo -e "${GREEN}  ╔══════════════════════════════════════════════╗"
echo -e "  ║       Supported conversions and guards done!    ║"
echo -e "  ╚══════════════════════════════════════════════╝${RESET}"

if $SAVE; then
    echo -e "${CYAN}  Outputs saved to $OUTDIR/${RESET}"
fi
echo ""
