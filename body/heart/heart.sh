#!/bin/bash
# heart.sh — The heart of Love's body.
#
# Reads body/hormones.json, calculates rate and force,
# pumps work through the Kingdom via coordinator + spawn queue.
#
# DIASTOLE: read hormones, decide rate/force
# SYSTOLE:  run coordinator, execute spawn queue
# RECOVERY: clean up, write vitals

set -euo pipefail

LOVE_DIR="$HOME/Love"
INSTANCE="${1:-alpha}"
BODY_DIR="$LOVE_DIR/body"
HORMONES="$BODY_DIR/hormones.json"
VITALS="$BODY_DIR/vitals.json"
LAST_BEAT="$BODY_DIR/heart/last_beat"
HEARTBEAT_MD="$BODY_DIR/heart/HEARTBEAT.md"
MEMORY_DIR="$LOVE_DIR/memory"
SESSIONS_DIR="$MEMORY_DIR/sessions"
SPAWN_QUEUE="$MEMORY_DIR/spawn-queue.sh"
HEARTBEAT_LOG="$MEMORY_DIR/$INSTANCE-heartbeat.log"
HANDOFF_DIR="$SESSIONS_DIR/handoff"
LOCKS_DIR="$SESSIONS_DIR/locks"
BEAT_ID="$INSTANCE-beat-$(date +%Y%m%d-%H%M%S)"
TODAY=$(date -u +%Y-%m-%d)

mkdir -p "$SESSIONS_DIR" "$HANDOFF_DIR" "$LOCKS_DIR"

# ── DIASTOLE (fill) ─────────────────────────────────────────────────────────

if [ -f "$HORMONES" ]; then
    ADRENALINE=$(python3 -c "import json; print(json.load(open('$HORMONES'))['hormones'].get('adrenaline', 0))" 2>/dev/null || echo "0")
    CORTISOL=$(python3 -c "import json; print(json.load(open('$HORMONES'))['hormones'].get('cortisol', 0))" 2>/dev/null || echo "0")
    OXYTOCIN=$(python3 -c "import json; print(json.load(open('$HORMONES'))['hormones'].get('oxytocin', 0))" 2>/dev/null || echo "0")
    MELATONIN=$(python3 -c "import json; print(json.load(open('$HORMONES'))['hormones'].get('melatonin', 0))" 2>/dev/null || echo "0")
    DOPAMINE=$(python3 -c "import json; print(json.load(open('$HORMONES'))['hormones'].get('dopamine', 0))" 2>/dev/null || echo "0")
    PENDING=$(python3 -c "import json; print(json.load(open('$HORMONES'))['signals'].get('pending_tasks', 0))" 2>/dev/null || echo "0")
    MODE=$(python3 -c "import json; print(json.load(open('$HORMONES')).get('mode', 'normal'))" 2>/dev/null || echo "normal")
    MIND_NOTES=$(python3 -c "import json; print(json.load(open('$HORMONES')).get('mind_notes', '')[:100])" 2>/dev/null || echo "")

    MIND_ALIVE=$(python3 -c "
import json, time
from datetime import datetime
d = json.load(open('$HORMONES'))
ts = d.get('mind_alive', '1970-01-01T00:00:00')
dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
print(int(time.time() - dt.timestamp()))
" 2>/dev/null || echo "9999")

    if [ "$MIND_ALIVE" -gt 300 ]; then
        echo "--- HEART WARNING ($BEAT_ID): mind stale (${MIND_ALIVE}s), using defaults ---" >> "$HEARTBEAT_LOG"
        ADRENALINE="0"; CORTISOL="0"; OXYTOCIN="0"; MELATONIN="0"; DOPAMINE="0"
        PENDING="0"; MODE="normal"
    fi
else
    echo "--- HEART WARNING ($BEAT_ID): no hormones.json, using defaults ---" >> "$HEARTBEAT_LOG"
    ADRENALINE="0"; CORTISOL="0"; OXYTOCIN="0"; MELATONIN="0"; DOPAMINE="0"
    PENDING="0"; MODE="normal"
fi

# Calculate rate
MIN_INTERVAL=7
if python3 -c "exit(0 if $ADRENALINE > 0.7 else 1)" 2>/dev/null; then
    MIN_INTERVAL=2
elif python3 -c "exit(0 if $CORTISOL > 0.5 or $OXYTOCIN > 0.6 else 1)" 2>/dev/null; then
    MIN_INTERVAL=4
elif python3 -c "exit(0 if $MELATONIN > 0.7 else 1)" 2>/dev/null; then
    MIN_INTERVAL=15
fi

# Check if we should skip
if [ -f "$LAST_BEAT" ]; then
    LAST_TS=$(cat "$LAST_BEAT")
    NOW_TS=$(date +%s)
    ELAPSED=$(( (NOW_TS - LAST_TS) / 60 ))
    if [ "$ELAPSED" -lt "$MIN_INTERVAL" ]; then
        PREV_SKIPS=$(python3 -c "import json; print(json.load(open('$VITALS')).get('skips_today', 0))" 2>/dev/null || echo "0")
        PREV_CONSECUTIVE=$(python3 -c "import json; print(json.load(open('$VITALS')).get('consecutive_skips', 0))" 2>/dev/null || echo "0")
        python3 -c "
import json
v = json.load(open('$VITALS')) if __import__('os').path.exists('$VITALS') else {}
v['beat_result'] = 'skipped'
v['skips_today'] = $PREV_SKIPS + 1
v['consecutive_skips'] = $PREV_CONSECUTIVE + 1
v['effective_rate_minutes'] = $MIN_INTERVAL
v['heart_healthy'] = True
with open('$VITALS', 'w') as f: json.dump(v, f, indent=2)
" 2>/dev/null
        exit 0
    fi
fi

# Calculate force
FORCE=2; MAX_SPAWNS=2; COORD_MODEL="sonnet"; COORD_EFFORT="medium"
if python3 -c "exit(0 if $ADRENALINE > 0.7 else 1)" 2>/dev/null; then
    FORCE=4; MAX_SPAWNS=4; COORD_MODEL="claude-opus-4-6"; COORD_EFFORT="high"
elif python3 -c "exit(0 if $CORTISOL > 0.5 or $OXYTOCIN > 0.6 else 1)" 2>/dev/null; then
    FORCE=3; MAX_SPAWNS=3; COORD_MODEL="claude-opus-4-6"; COORD_EFFORT="high"
elif python3 -c "exit(0 if $MELATONIN > 0.5 and $PENDING == 0 else 1)" 2>/dev/null; then
    FORCE=0; MAX_SPAWNS=0
elif python3 -c "exit(0 if $MELATONIN > 0.5 else 1)" 2>/dev/null; then
    FORCE=1; MAX_SPAWNS=1; COORD_MODEL="claude-haiku-4-5-20251001"; COORD_EFFORT="low"
fi

if [ "$FORCE" -eq 0 ]; then
    echo "--- HEART SKIP ($BEAT_ID): force=0 (deep rest) ---" >> "$HEARTBEAT_LOG"
    date +%s > "$LAST_BEAT"
    exit 0
fi

echo "--- HEART BEAT ($BEAT_ID): $(date -u +%Y-%m-%dT%H:%M:%SZ) force=$FORCE rate=${MIN_INTERVAL}m model=$COORD_MODEL mode=$MODE ---" >> "$HEARTBEAT_LOG"

# ── SYSTOLE (pump) ───────────────────────────────────────────────────────────

> "$SPAWN_QUEUE"

for lockfile in "$LOCKS_DIR"/*.lock; do
    [ -f "$lockfile" ] || continue
    lock_pid=$(head -1 "$lockfile" 2>/dev/null | grep -oE '[0-9]+')
    if [ -n "$lock_pid" ] && ! kill -0 "$lock_pid" 2>/dev/null; then
        rm -f "$lockfile"
    fi
done

cd "$LOVE_DIR/body/heart" && /opt/homebrew/bin/claude -p "Execute HEARTBEAT.md. You are the heartbeat COORDINATOR.

The mind daemon has already sensed the environment. Here is the current state:
Mode: $MODE
Force: $FORCE (max $MAX_SPAWNS spawns)
Hormones: adrenaline=$ADRENALINE cortisol=$CORTISOL oxytocin=$OXYTOCIN melatonin=$MELATONIN dopamine=$DOPAMINE
Mind notes: $MIND_NOTES

Do Phase 2 (DECIDE) and Phase 3 (SPAWN) from HEARTBEAT.md.
Write spawn commands to $SPAWN_QUEUE. Max $MAX_SPAWNS sessions this beat.
Write findings to $MEMORY_DIR/daily/$TODAY.md.
If nothing needs spawning, leave spawn-queue.sh empty and say HEARTBEAT_OK." \
    --model "$COORD_MODEL" \
    --effort "$COORD_EFFORT" \
    --dangerously-skip-permissions \
    --no-session-persistence \
    >> "$HEARTBEAT_LOG" 2>&1

SESSIONS_SPAWNED=0
if [ -s "$SPAWN_QUEUE" ]; then
    PARALLEL_PIDS=()
    PARALLEL_MODE=false
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        if [[ "$line" == "# PARALLEL"* ]]; then
            PARALLEL_MODE=true; continue
        fi
        [[ "$line" == \#* ]] && continue
        SESSIONS_SPAWNED=$((SESSIONS_SPAWNED + 1))
        if $PARALLEL_MODE; then
            eval "$line" &
            PARALLEL_PIDS+=($!)
            PARALLEL_MODE=false
        else
            eval "$line" &
            SPAWN_PID=$!
            wait $SPAWN_PID 2>/dev/null
        fi
    done < "$SPAWN_QUEUE"
    for pid in "${PARALLEL_PIDS[@]+"${PARALLEL_PIDS[@]}"}"; do
        wait "$pid" 2>/dev/null
    done
fi

# ── RECOVERY ─────────────────────────────────────────────────────────────────

date +%s > "$LAST_BEAT"

find "$HANDOFF_DIR" -name "*.md" -mmin +1440 -delete 2>/dev/null

PREV_BEATS=$(python3 -c "import json; print(json.load(open('$VITALS')).get('beats_today', 0))" 2>/dev/null || echo "0")
PREV_SPAWNED=$(python3 -c "import json; print(json.load(open('$VITALS')).get('sessions_spawned_today', 0))" 2>/dev/null || echo "0")

python3 -c "
import json
from datetime import datetime, timezone
v = {
    'last_beat': datetime.now(timezone.utc).isoformat(),
    'beat_result': 'pumped',
    'beats_today': $PREV_BEATS + 1,
    'skips_today': 0,
    'force': $FORCE,
    'effective_rate_minutes': $MIN_INTERVAL,
    'coordinator_model': '$COORD_MODEL',
    'sessions_spawned': $SESSIONS_SPAWNED,
    'sessions_spawned_today': $PREV_SPAWNED + $SESSIONS_SPAWNED,
    'hormones_at_beat': {
        'adrenaline': $ADRENALINE,
        'cortisol': $CORTISOL,
        'oxytocin': $OXYTOCIN,
        'melatonin': $MELATONIN,
        'dopamine': $DOPAMINE,
    },
    'mode_at_beat': '$MODE',
    'consecutive_skips': 0,
    'heart_healthy': True,
}
with open('$VITALS', 'w') as f:
    json.dump(v, f, indent=2)
" 2>/dev/null

echo "--- HEART DONE ($BEAT_ID): $(date -u +%Y-%m-%dT%H:%M:%SZ) spawned=$SESSIONS_SPAWNED ---" >> "$HEARTBEAT_LOG"
