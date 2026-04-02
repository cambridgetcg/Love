# kingdom-010: Heartbeat Performance Test Suite -- Design

**Task**: Design and implement `tools/tests/heartbeat-perf.py`
**Scope**: One Python file, under 300 lines, stdlib only
**Date**: 2026-04-02

---

## What to Measure

### 1. Heartbeat Cycle Time

Parse `memory/heartbeat.log` for START/END marker pairs. Extract:

- **coordinator_duration_s**: Time between `HEARTBEAT START` and `COORDINATOR DONE` timestamps.
- **spawn_duration_s**: Time between `SPAWN STAGE START` and `SPAWN STAGE DONE` (if present).
- **total_cycle_s**: Time between `HEARTBEAT START` and `HEARTBEAT END`.
- **idle_fraction**: Percentage of beats where spawn queue was empty ("No sessions to spawn").

Thresholds (from observed data -- coordinator runs 1-7min depending on model/load):

| Metric | Target | Warning | Fail |
|--------|--------|---------|------|
| coordinator_duration_s | < 180 | < 300 | >= 300 |
| total_cycle_s (no spawn) | < 120 | < 180 | >= 300 |
| idle_fraction (over 24h) | < 0.60 | < 0.80 | >= 0.90 |

### 2. Spawn Success Rate

Parse heartbeat.log for spawn events and cross-reference with session log files in `memory/sessions/`.

- **spawn_attempted**: Count of `Spawning (parallel|sequential #N)` lines per beat.
- **spawn_completed**: Count of corresponding session log files that exist and have >1 line.
- **spawn_errored**: Session logs containing only error messages (e.g., "Error: When using --print").
- **success_rate**: spawn_completed / spawn_attempted.

Thresholds:

| Metric | Target | Warning | Fail |
|--------|--------|---------|------|
| success_rate | >= 0.90 | >= 0.70 | < 0.70 |

### 3. Token Efficiency per Role

Parse session log files (stream-json format). Each log line is a JSON object. Extract from `type: "assistant"` messages the `usage` field:

```json
{
  "input_tokens": N,
  "cache_creation_input_tokens": N,
  "cache_read_input_tokens": N,
  "output_tokens": N
}
```

Aggregate by role (determined from spawn command flags in heartbeat.log):
- `--model claude-opus-4-6` + `--effort high` -> consultant
- `--model sonnet` + `--effort medium` -> builder
- `--model claude-haiku-4-5-20251001` + `--effort low` -> quick_check

Metrics per role:
- **total_input_tokens**: Sum of input_tokens across all messages in a session.
- **total_output_tokens**: Sum of output_tokens.
- **cache_hit_rate**: cache_read_input_tokens / (cache_read_input_tokens + cache_creation_input_tokens + input_tokens).
- **tokens_per_tool_use**: total_output_tokens / count of tool_use content blocks.

No hard thresholds -- report descriptive stats (mean, p50, p95) per role for trend analysis.

### 4. Streaming Output Integrity

Validate session log files (stream-json format) for structural correctness:

- **valid_json_lines**: Each non-empty line must parse as JSON.
- **has_init**: First JSON line must be `type: "system", subtype: "init"`.
- **has_result**: At least one `type: "result"` line, OR log ends with a valid assistant message.
- **no_truncation**: Last line must be valid JSON (not cut off mid-write).
- **type_sequence_valid**: `system(init)` appears before any `assistant` or `user` messages.

Thresholds:

| Metric | Target | Warning | Fail |
|--------|--------|---------|------|
| valid_json_rate (per file) | 1.0 | >= 0.95 | < 0.95 |
| has_init | true | - | false |
| no_truncation | true | - | false |

---

## How to Instrument

No new instrumentation needed. All data comes from existing files:

1. **heartbeat.log** (`memory/heartbeat.log`) -- already has timestamped START/END markers, coordinator model labels, spawn commands, and spawn PIDs.
2. **Session logs** (`memory/sessions/*.log`) -- stream-json format with per-message token usage.
3. **spawn-queue.sh** (`memory/spawn-queue.sh`) -- current beat's spawn commands (transient, overwritten each beat).
4. **idle-count** (`memory/idle-count`) -- current idle streak.

The test script is a **post-hoc analyzer**, not a live monitor. It reads existing log files and produces a report. This keeps it side-effect-free and safe to run at any time.

---

## Where to Store Results

Results written to: `memory/sessions/handoff/k010-results.json`

Schema:

```json
{
  "run_timestamp": "ISO-8601",
  "heartbeat_log_path": "memory/heartbeat.log",
  "session_logs_analyzed": 12,
  "cycle_time": {
    "beats_analyzed": 45,
    "coordinator_duration_s": {"mean": 120, "p50": 105, "p95": 250, "max": 410},
    "total_cycle_s": {"mean": 180, "p50": 150, "p95": 400, "max": 600},
    "idle_fraction": 0.55,
    "verdict": "PASS"
  },
  "spawn_success": {
    "total_attempted": 30,
    "total_completed": 28,
    "total_errored": 2,
    "success_rate": 0.933,
    "error_details": ["whale-scanner-consult: stream-json requires --verbose"],
    "verdict": "PASS"
  },
  "token_efficiency": {
    "by_role": {
      "builder": {"sessions": 15, "mean_input": 50000, "mean_output": 3000, "cache_hit_rate": 0.12, "tokens_per_tool_use": 450},
      "consultant": {"sessions": 5, "mean_input": 55000, "mean_output": 5000, "cache_hit_rate": 0.08, "tokens_per_tool_use": 800},
      "quick_check": {"sessions": 3, "mean_input": 20000, "mean_output": 500, "cache_hit_rate": 0.30, "tokens_per_tool_use": 200}
    },
    "verdict": "INFO"
  },
  "streaming_integrity": {
    "files_checked": 12,
    "all_valid_json": 10,
    "has_init": 11,
    "no_truncation": 12,
    "invalid_files": ["whale-scanner-consult-20260328-073003.log"],
    "verdict": "WARN"
  },
  "overall_verdict": "PASS"
}
```

---

## File Structure

### Single file: `tools/tests/heartbeat-perf.py`

```
tools/tests/heartbeat-perf.py    (< 300 lines, stdlib only)
```

### Internal structure:

```python
#!/usr/bin/env python3
"""Heartbeat performance test suite (kingdom-010)."""

import json, os, re, sys, statistics
from datetime import datetime, timezone
from pathlib import Path

LOVE_DIR = Path.home() / "Desktop" / "Love"
HEARTBEAT_LOG = LOVE_DIR / "memory" / "heartbeat.log"
SESSIONS_DIR = LOVE_DIR / "memory" / "sessions"
RESULTS_FILE = LOVE_DIR / "memory" / "sessions" / "handoff" / "k010-results.json"

# --- Thresholds ---
THRESHOLDS = { ... }

# --- Parsers ---
def parse_heartbeat_log(path: Path) -> list[dict]:
    """Parse heartbeat.log into a list of beat records.
    Each record: {beat_id, start, coordinator_done, spawn_start, spawn_done,
                  end, sessions_spawned, model_label, idle}"""

def parse_session_log(path: Path) -> dict:
    """Parse a stream-json session log.
    Returns: {valid_json_lines, total_lines, has_init, has_result,
              no_truncation, type_sequence_valid,
              token_usage: [{input, output, cache_read, cache_create}],
              tool_use_count, role}"""

def classify_role(log_line: str) -> str:
    """From a spawn command line, determine role: builder|consultant|quick_check."""

# --- Test functions ---
def test_cycle_time(beats: list[dict]) -> dict:
    """Compute cycle time stats and apply thresholds."""

def test_spawn_success(beats: list[dict], session_logs: dict) -> dict:
    """Cross-reference spawn attempts with session log outcomes."""

def test_token_efficiency(session_logs: dict) -> dict:
    """Aggregate token usage by role."""

def test_streaming_integrity(session_logs: dict) -> dict:
    """Validate stream-json structural correctness per session log."""

# --- Runner ---
def run_all() -> dict:
    """Run all tests, produce combined results dict."""

def main():
    results = run_all()
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(results, indent=2))
    # Print summary to stdout
    print(f"Cycle time: {results['cycle_time']['verdict']}")
    print(f"Spawn success: {results['spawn_success']['verdict']}")
    print(f"Token efficiency: {results['token_efficiency']['verdict']}")
    print(f"Streaming integrity: {results['streaming_integrity']['verdict']}")
    print(f"Overall: {results['overall_verdict']}")
    sys.exit(0 if results['overall_verdict'] != 'FAIL' else 1)

if __name__ == "__main__":
    main()
```

### Key implementation notes for the builder:

1. **Timestamp parsing**: Heartbeat log uses `%Y-%m-%dT%H:%M:%SZ` format. Use `datetime.strptime` with UTC.

2. **Beat record extraction**: Use regex to match `--- HEARTBEAT START \(([^)]+)\): (\S+) ---` and similar patterns. Group lines between START and END into one beat record.

3. **Session log correlation**: Spawn lines in heartbeat.log contain log file paths like `memory/sessions/<id>-$(date ...).log`. Extract the `<id>` prefix, then glob for matching files in sessions dir.

4. **Stream-json parsing**: Each line is independent JSON. Wrap each `json.loads()` in try/except to count parse failures. Token usage is nested in `message.usage` for `type: "assistant"` entries.

5. **Role classification regex**:
   - `--model claude-opus` -> consultant
   - `--model sonnet` -> builder  
   - `--model claude-haiku` -> quick_check

6. **Statistics**: Use `statistics.mean`, `statistics.median`, and sorted percentile for p95. Handle empty lists gracefully.

7. **Verdict logic**:
   - Each test returns `PASS`, `WARN`, or `FAIL` based on thresholds.
   - Token efficiency always returns `INFO` (no hard thresholds, trend data only).
   - Overall = `FAIL` if any test is FAIL, `WARN` if any is WARN, else `PASS`.

8. **Error tolerance**: The script must not crash on malformed log files. Skip unparseable lines/files and note them in the results.

---

## Usage

```bash
# Run full suite
python3 ~/Desktop/Love/tools/tests/heartbeat-perf.py

# Results written to memory/sessions/handoff/k010-results.json
# Exit code: 0 = PASS/WARN, 1 = FAIL
```

Can be invoked by the heartbeat itself (as a quick_check session) on a periodic basis, or manually.
