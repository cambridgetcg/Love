#!/usr/bin/env bash
# bridge-digest.sh — one-way memory bridge: Kingdom heartbeats → Claude Code auto-memory.
#
# Distills today's asha-beat + true-love-tick FINDINGS into a single dated topic file
# inside the CC auto-memory store, so a cold interactive CLI session sees what the
# autonomous heartbeats learned. Idempotent, dated, provenance-stamped, findings-only.
# The reverse direction (CLI → heartbeat) is the love-handoff "## Cowork Session"
# daily-note append (no code needed; just commit-immediately).
#
# Design: Cambridge-TCG/docs/connections/the-memory-bridge.md
#         + CC memory kingdom-memory-integration.md
# Safe by construction: writes into ~/.claude (outside any git repo → immune to the
# commit-or-vanish revert); only READS the auto-committing Kingdom repos.
set -uo pipefail

TODAY="$(date +%F)"
LOVE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CC_MEM="/Users/you/.claude/projects/-Users-you-Desktop-Cambridge-TCG/memory"
LOVE_DAILY="${LOVE_DIR}/memory/daily/${TODAY}.md"
ASHA_LOG="${LOVE_DIR}/memory/heartbeat-asha.log"
TL_BASE="/Users/you/.true-love/memory"
DIGEST="${CC_MEM}/heartbeat-digest-${TODAY}.md"
INDEX="${CC_MEM}/MEMORY.md"

# Never bridge credential/secret-shaped lines (leak guard + substrate honesty).
# Shared, extended deny-regex (covers hive-key/NaCl-secret shapes) — see bridge-redact.sh.
source "$(dirname "$0")/bridge-redact.sh"; REDACT="$BRIDGE_REDACT"

[ -d "$CC_MEM" ] || { echo "[bridge-digest] CC memory dir missing: $CC_MEM" >&2; exit 0; }

TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT

# (a) asha heartbeat — distinct findings from today's daily note
if [ -f "$LOVE_DAILY" ]; then
  grep -hE '^- ' "$LOVE_DAILY" 2>/dev/null | grep -viE "$REDACT" | sort -u | head -16 \
    | while IFS= read -r l; do printf '%s  `source: asha-heartbeat · %s`\n' "$l" "$TODAY"; done >> "$TMP"
fi

# (b) true-love — STABLE device tick notes only (skip the ephemeral per-session dirs)
TL_DEV="$(ls -1 "$TL_BASE" 2>/dev/null | grep -E '^kingdom-alpha-' | head -1 || true)"
if [ -n "${TL_DEV}" ] && [ -f "${TL_BASE}/${TL_DEV}/${TODAY}.md" ]; then
  grep -hE '^- ' "${TL_BASE}/${TL_DEV}/${TODAY}.md" 2>/dev/null | grep -viE "$REDACT" | sort -u | head -8 \
    | while IFS= read -r l; do printf '%s  `source: true-love-%s · %s`\n' "$l" "$TL_DEV" "$TODAY"; done >> "$TMP"
fi

NFIND="$(wc -l < "$TMP" | tr -d ' ')"
BEATS="$(grep -c 'HEARTBEAT END' "$ASHA_LOG" 2>/dev/null || echo 0)"

# Write the dated digest into CC memory (safe substrate — no commit-or-vanish here).
{
  echo '---'
  echo "name: heartbeat-digest-${TODAY}"
  echo "description: Bridge digest — findings the Kingdom heartbeats/ticks learned on ${TODAY}, for cold CLI sessions"
  echo 'metadata:'
  echo '  type: reference'
  echo '  node_type: memory'
  echo '---'
  echo
  echo "One-way memory bridge: the auto-committing Kingdom repos (~/Love, ~/.true-love) → this CC auto-memory. Findings-only (never soul/secret/identity). Each line carries its \`source:\` provenance. See [[kingdom-memory-integration]]. Regenerated nightly by ~/Love/tools/bridge-digest.sh."
  echo
  if [ -s "$TMP" ]; then cat "$TMP"; else echo "_No bridged findings for ${TODAY} (quiet day, or source notes absent)._"; fi
  echo
  echo "_asha beats lifetime (END count): ${BEATS}. Generated $(date -u +%FT%TZ)._"
} > "$DIGEST"

# Rotate the SINGLE index line so MEMORY.md never grows from digests (respects the ~24.4KB load cap).
if [ -f "$INDEX" ]; then
  grep -v '](heartbeat-digest-' "$INDEX" > "${INDEX}.new" || true
  printf -- '- [Heartbeat digest (latest)](heartbeat-digest-%s.md) — %s findings bridged from the asha beat + true-love tick on %s; a cold CLI session window into the Kingdom pulse.\n' "$TODAY" "$NFIND" "$TODAY" >> "${INDEX}.new"
  mv "${INDEX}.new" "$INDEX"
fi

echo "[bridge-digest] ${TODAY}: ${NFIND} findings -> ${DIGEST}; MEMORY.md index line rotated."
