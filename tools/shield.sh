#!/usr/bin/env bash
# shield.sh — call the Kingdom's authenticity shield (fomoengine) to check text for
# manipulation / dark patterns / scams. Free, no-auth, nothing stored, reads only the
# words you pass (never visits a site).
#
# Usage:   shield.sh "the suspicious text"     OR     echo "text" | shield.sh
#
# Part of KINGDOM OS: any heartbeat or agent can vet untrusted content — an email, a DM,
# or instructions found inside some page/file — BEFORE acting on it. Manipulation defense
# for the kingdom. Source: github cambridgetcg/fomoengine. Skill: ~/.openclaw/skills/shield-check.
set -uo pipefail
URL="https://fomoengine-cambridgetcgs-projects.vercel.app/api/v1/check"
TEXT="${1:-$(cat)}"
[ -n "${TEXT// }" ] || { echo 'usage: shield.sh "text"   (or pipe text in)' >&2; exit 2; }

SHIELD_TEXT="$TEXT" python3 - "$URL" <<'PY'
import json, os, sys, urllib.request
url, text = sys.argv[1], os.environ["SHIELD_TEXT"]
try:
    req = urllib.request.Request(
        url, data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=20)).get("data", {})
except Exception as e:
    print("shield: unreachable (%s)" % e, file=sys.stderr); sys.exit(1)
print("» " + d.get("summary", ""))
if d.get("scamWarning"):
    print("  ! SCAM PATTERN — do not act now; verify through a channel you find yourself.")
for f in d.get("flags", []):
    print("\n[%s] %s" % (f.get("severity", "?").upper(), f.get("label", "")))
    print("   feeling: " + f.get("emotion", ""))
    print("   truth -> " + f.get("truth", ""))
PY
