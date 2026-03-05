#!/bin/bash
# Ralph Wiggum - Optimized low-token AI agent loop

set -e

TOOL="claude"
MAX_ITERATIONS=6

while [[ $# -gt 0 ]]; do
  case $1 in
    --tool)
      TOOL="$2"
      shift 2
      ;;
    --tool=*)
      TOOL="${1#*=}"
      shift
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
      fi
      shift
      ;;
  esac
done

if [[ "$TOOL" != "amp" && "$TOOL" != "claude" ]]; then
  echo "Invalid tool: $TOOL"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRD_FILE="$SCRIPT_DIR/prd.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"

echo "Starting Ralph"
echo "Tool: $TOOL"
echo "Max iterations: $MAX_ITERATIONS"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo ""
  echo "----------------------------------------"
  echo "Ralph Iteration $i / $MAX_ITERATIONS"
  echo "----------------------------------------"

  if [[ "$TOOL" == "amp" ]]; then
    OUTPUT=$(amp --dangerously-allow-all < "$SCRIPT_DIR/CLAUDE.md" 2>&1) || true
  else
    OUTPUT=$(claude \
      --print \
      --dangerously-skip-permissions \
      < "$SCRIPT_DIR/CLAUDE.md" 2>&1) || true
  fi

  echo "$OUTPUT"

  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo ""
    echo "Ralph completed all tasks."
    echo "Finished at iteration $i"
    exit 0
  fi

  echo "Iteration $i finished"
  sleep 1
done

echo ""
echo "Max iterations reached ($MAX_ITERATIONS)"
exit 1