#!/bin/bash
# autospec executor
# usage: ./executor/run.sh
# runs forever, polling every 5 minutes. ctrl-c to stop.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MAX_SESSIONS=10
POLL_INTERVAL=300
LOCK_DIR="/tmp/autospec-executor-locks"
LOG_DIR="$REPO_ROOT/executor/logs"

mkdir -p "$LOCK_DIR" "$LOG_DIR"

spawn_session() {
  local TIMESTAMP
  TIMESTAMP=$(date +%Y%m%d-%H%M%S)
  LOG_FILE="$LOG_DIR/session-${TIMESTAMP}.log"

  (
    LOCK="$LOCK_DIR/$$"
    touch "$LOCK"
    trap "rm -f $LOCK" EXIT

    claude -p "You are the autospec executor. Follow the instructions in skills/poll-jobs/SKILL.md exactly. Working directory: $REPO_ROOT" \
      --dangerously-skip-permissions \
      > "$LOG_FILE" 2>&1
  ) &
}

echo "autospec executor started (max $MAX_SESSIONS parallel sessions, polling every ${POLL_INTERVAL}s)"

while true; do
  # clean stale locks from dead PIDs
  for f in "$LOCK_DIR"/*; do
    [ -f "$f" ] || continue
    pid=$(basename "$f")
    kill -0 "$pid" 2>/dev/null || rm -f "$f"
  done

  ACTIVE=$(find "$LOCK_DIR" -type f 2>/dev/null | wc -l)

  if [ "$ACTIVE" -lt "$MAX_SESSIONS" ]; then
    cd "$REPO_ROOT/techniques" || { sleep "$POLL_INTERVAL"; continue; }
    git pull --rebase 2>/dev/null || { sleep "$POLL_INTERVAL"; continue; }

    QUEUED=$(find jobs/queue -name '*.md' -type f 2>/dev/null | sort)
    SLOTS=$(( MAX_SESSIONS - ACTIVE ))

    for job in $QUEUED; do
      if [ "$SLOTS" -le 0 ]; then break; fi
      spawn_session
      SLOTS=$(( SLOTS - 1 ))
      sleep 1
    done
  fi

  sleep "$POLL_INTERVAL"
done
