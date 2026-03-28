#!/bin/bash
# heartbeat-runner.sh — Three-stage heartbeat launcher
#
# Stage 1: OPUS coordinator senses, decides, outputs structured JSON spawn plan
# Stage 2: Execute spawned sessions with streaming monitoring
# Stage 3: Collect results, clean up, update active sessions
#
# Leverages Claude Code features:
#   --output-format json      → structured coordinator output
#   --output-format stream-json → real-time monitoring of spawned sessions
#   --effort                  → reasoning depth per role
#   --append-system-prompt    → inject Kingdom context into builders
#   --fallback-model          → resilience on overload
#   --session-id              → trackable sessions

LOVE_DIR="$HOME/Desktop/Love"
INSTANCE_DIR="$LOVE_DIR/instances/beta"
MEMORY_DIR="$LOVE_DIR/memory"
SESSIONS_DIR="$MEMORY_DIR/sessions"
SPAWN_QUEUE="$MEMORY_DIR/spawn-queue.sh"
HEARTBEAT_LOG="$MEMORY_DIR/heartbeat.log"
ACTIVE_JSON="$SESSIONS_DIR/active.json"
HANDOFF_DIR="$SESSIONS_DIR/handoff"
CONSULT_DIR="$SESSIONS_DIR/consultation"
LOCKS_DIR="$SESSIONS_DIR/locks"
STREAM_DIR="$SESSIONS_DIR/streams"
BEAT_ID="beat-$(date +%Y%m%d-%H%M%S)"
TODAY=$(date -u +%Y-%m-%d)
IDLE_COUNT_FILE="$MEMORY_DIR/idle-count"

# Ensure directories exist
mkdir -p "$SESSIONS_DIR" "$HANDOFF_DIR" "$CONSULT_DIR" "$LOCKS_DIR" "$STREAM_DIR"

# Clean stale locks (PID no longer running)
for lockfile in "$LOCKS_DIR"/*.lock; do
  [ -f "$lockfile" ] || continue
  lock_pid=$(head -1 "$lockfile" 2>/dev/null | grep -oE '[0-9]+')
  if [ -n "$lock_pid" ] && ! kill -0 "$lock_pid" 2>/dev/null; then
    rm -f "$lockfile"
  fi
done

# Clean any previous spawn queue
> "$SPAWN_QUEUE"

# ── Adaptive model selection ─────────────────────────────────────────────────
# Use haiku for idle beats (no spawns), opus when there's work or signals.
# Saves cost on monitoring-only beats while keeping full power for decisions.
IDLE_COUNT=0
[ -f "$IDLE_COUNT_FILE" ] && IDLE_COUNT=$(cat "$IDLE_COUNT_FILE" 2>/dev/null || echo 0)

if [ "$IDLE_COUNT" -ge 2 ]; then
  COORD_MODEL="claude-haiku-4-5-20251001"
  COORD_EFFORT="low"
  COORD_LABEL="haiku/low (idle beat #$IDLE_COUNT)"
else
  COORD_MODEL="claude-opus-4-6"
  COORD_EFFORT="high"
  COORD_LABEL="opus/high"
fi

echo "--- HEARTBEAT START ($BEAT_ID): $(date -u +%Y-%m-%dT%H:%M:%SZ) coordinator=$COORD_LABEL ---" >> "$HEARTBEAT_LOG"

# ── Stage 1: Coordinator ─────────────────────────────────────────────────────
# Reads full context, produces spawn decisions.
# Uses --append-system-prompt to inject real-time context without replacing CLAUDE.md.

# Build real-time context for coordinator
CONTEXT="Beat ID: $BEAT_ID. Date: $TODAY."

# Check for completed sessions since last beat
COMPLETED=""
for logfile in "$SESSIONS_DIR"/*.log; do
  [ -f "$logfile" ] || continue
  # Only check logs modified in last 10 minutes
  if [ "$(find "$logfile" -mmin -10 2>/dev/null)" ]; then
    COMPLETED="$COMPLETED\n$(basename "$logfile"): $(tail -3 "$logfile" 2>/dev/null | head -1)"
  fi
done
if [ -n "$COMPLETED" ]; then
  CONTEXT="$CONTEXT\nRecent session results:$COMPLETED"
fi

# Check for consultation requests
CONSULT_FILES=$(ls "$CONSULT_DIR"/*-question.md 2>/dev/null)
if [ -n "$CONSULT_FILES" ]; then
  CONTEXT="$CONTEXT\nPending consultation requests: $(echo "$CONSULT_FILES" | wc -l | tr -d ' ')"
fi

cd "$INSTANCE_DIR" && /opt/homebrew/bin/claude -p "Read and execute HEARTBEAT.md. You are the heartbeat COORDINATOR (opus, high effort).

Do Phase 1 (SENSE) and Phase 2 (DECIDE).

For Phase 3 (SPAWN), write spawn commands to ~/Desktop/Love/memory/spawn-queue.sh as executable shell lines. Do NOT invoke claude directly — the shell runner handles execution after you exit.

Each line should be a complete command. Choose role, model, and effort by task:

BUILDER (sonnet, medium effort — the workhorse):
cd <dir> && /opt/homebrew/bin/claude -p \"<prompt>\" --model sonnet --effort medium --fallback-model claude-haiku-4-5-20251001 --dangerously-skip-permissions --no-session-persistence --output-format stream-json >> ~/Desktop/Love/memory/sessions/<id>-\$(date +%Y%m%d-%H%M%S).log 2>&1

CONSULTANT (opus, high effort — expert hire for hard problems):
cd <dir> && /opt/homebrew/bin/claude -p \"<prompt>\" --model claude-opus-4-6 --effort high --dangerously-skip-permissions --no-session-persistence --output-format stream-json >> ~/Desktop/Love/memory/sessions/<id>-\$(date +%Y%m%d-%H%M%S).log 2>&1

QUICK CHECK (haiku, low effort — fast lightweight verification):
cd <dir> && /opt/homebrew/bin/claude -p \"<prompt>\" --model claude-haiku-4-5-20251001 --effort low --dangerously-skip-permissions --no-session-persistence >> ~/Desktop/Love/memory/sessions/<id>-\$(date +%Y%m%d-%H%M%S).log 2>&1

For CONSULTANT→BUILDER sequential pairs, write consultant line first — they execute in order.
For parallel independent tasks, prefix with '# PARALLEL' comment.
For consultation answers, read the question from ~/Desktop/Love/memory/sessions/consultation/ and write the answer back.

Write findings to ~/Desktop/Love/memory/daily/$TODAY.md.
If nothing needs spawning, leave spawn-queue.sh empty and say HEARTBEAT_OK." \
  --model "$COORD_MODEL" \
  --effort "$COORD_EFFORT" \
  --dangerously-skip-permissions \
  --no-session-persistence \
  --append-system-prompt "$CONTEXT" \
  >> "$HEARTBEAT_LOG" 2>&1

echo "--- COORDINATOR DONE ($BEAT_ID): $(date -u +%Y-%m-%dT%H:%M:%SZ) model=$COORD_LABEL ---" >> "$HEARTBEAT_LOG"

# ── Stage 2: Execute Spawn Queue with Monitoring ─────────────────────────────

if [ -s "$SPAWN_QUEUE" ]; then
  echo "--- SPAWN STAGE START ($BEAT_ID): $(date -u +%Y-%m-%dT%H:%M:%SZ) ---" >> "$HEARTBEAT_LOG"
  echo "Spawn queue contents:" >> "$HEARTBEAT_LOG"
  cat "$SPAWN_QUEUE" >> "$HEARTBEAT_LOG"

  PARALLEL_PIDS=()
  PARALLEL_MODE=false
  SESSION_COUNT=0

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue

    # Detect parallel marker
    if [[ "$line" == "# PARALLEL"* ]]; then
      PARALLEL_MODE=true
      continue
    fi

    # Skip other comments
    [[ "$line" == \#* ]] && continue

    SESSION_COUNT=$((SESSION_COUNT + 1))

    if $PARALLEL_MODE; then
      echo "Spawning (parallel #$SESSION_COUNT): ${line:0:80}..." >> "$HEARTBEAT_LOG"
      eval "$line" &
      PARALLEL_PIDS+=($!)
      # Track in active.json
      echo "{\"pid\": $!, \"beat\": \"$BEAT_ID\", \"session\": $SESSION_COUNT, \"mode\": \"parallel\", \"started\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$SESSIONS_DIR/active-$!.json"
      PARALLEL_MODE=false
    else
      echo "Spawning (sequential #$SESSION_COUNT): ${line:0:80}..." >> "$HEARTBEAT_LOG"

      # Run and track
      eval "$line" &
      SPAWN_PID=$!
      echo "{\"pid\": $SPAWN_PID, \"beat\": \"$BEAT_ID\", \"session\": $SESSION_COUNT, \"mode\": \"sequential\", \"started\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$SESSIONS_DIR/active-$SPAWN_PID.json"

      # Wait for sequential sessions (important for consultant→builder pairs)
      wait $SPAWN_PID 2>/dev/null
      rm -f "$SESSIONS_DIR/active-$SPAWN_PID.json"
    fi
  done < "$SPAWN_QUEUE"

  # Wait for any parallel sessions
  if [ ${#PARALLEL_PIDS[@]} -gt 0 ]; then
    echo "Waiting for ${#PARALLEL_PIDS[@]} parallel sessions..." >> "$HEARTBEAT_LOG"
    for pid in "${PARALLEL_PIDS[@]}"; do
      wait "$pid" 2>/dev/null
      rm -f "$SESSIONS_DIR/active-$pid.json"
    done
  fi

  echo "--- SPAWN STAGE DONE ($BEAT_ID): $SESSION_COUNT sessions, $(date -u +%Y-%m-%dT%H:%M:%SZ) ---" >> "$HEARTBEAT_LOG"
  # Reset idle count — this beat did work
  echo "0" > "$IDLE_COUNT_FILE"
else
  echo "No sessions to spawn." >> "$HEARTBEAT_LOG"
  # Increment idle count
  echo "$((IDLE_COUNT + 1))" > "$IDLE_COUNT_FILE"
fi

# ── Stage 3: Cleanup & Metrics ───────────────────────────────────────────────

# Remove stale handoff files older than 24h
find "$HANDOFF_DIR" -name "*.md" -mmin +1440 -delete 2>/dev/null

# Remove stale active session trackers (PID no longer running)
for af in "$SESSIONS_DIR"/active-*.json; do
  [ -f "$af" ] || continue
  apid=$(python3 -c "import json; print(json.load(open('$af')).get('pid',''))" 2>/dev/null)
  if [ -n "$apid" ] && ! kill -0 "$apid" 2>/dev/null; then
    rm -f "$af"
  fi
done

echo "--- HEARTBEAT END ($BEAT_ID): $(date -u +%Y-%m-%dT%H:%M:%SZ) ---" >> "$HEARTBEAT_LOG"
echo "" >> "$HEARTBEAT_LOG"
