# MLX Local Inference & Fine-Tuning — Design Spec

> **Purpose**: Run a fine-tuned local model on M4 Max to handle routine Kingdom tasks (heartbeat triage, message classification, task routing, signal classification), saving Claude API tokens for complex reasoning.

## Goal

Build an MLX-based inference daemon + LoRA fine-tuning pipeline + data generation tools that integrate with Love's existing tool ecosystem. Start with a 3B model, prove the pipeline, scale up to 7-13B when the infrastructure is solid.

### Non-Goals

- Replace Claude for complex reasoning (truth evaluation, oracle predictions, creative work)
- Build a general-purpose chat interface
- Support non-Apple hardware

---

## Architecture

Four components: **server** (persistent daemon), **trainer** (offline CLI), **data generator** (CLI), **client** (library). All follow Love's patterns: standalone Python scripts, filesystem state, subprocess integration.

### Dependencies

```
mlx >= 0.22
mlx-lm >= 0.21
```

Apple-maintained, Apple Silicon native. No PyTorch, no transformers. These are the only pip dependencies.

### Directory Layout

```
~/Desktop/Love/
  mlx/
    config.json              # Model config (base model, adapter path, server port)
    adapters/                # LoRA adapter weights (one dir per training run)
      kingdom-v1/            # Small (few MB), git-tracked, syncs across instances
    training/
      datasets/              # JSONL training data
        heartbeat-triage.jsonl
        message-classify.jsonl
        task-routing.jsonl
        signal-classify.jsonl
      templates/             # Claude prompt templates for synthetic generation
      runs/                  # Training run logs + metrics
    cache/                   # Downloaded base model weights (.gitignore'd)
  tools/
    mlx-serve.py             # Daemon — HTTP inference server on localhost:8800
    mlx-train.py             # CLI — LoRA fine-tuning pipeline
    mlx-data.py              # CLI — Synthetic data generation + real data harvesting
    mlx-client.py            # Library — drop-in inference from any Love tool
```

### Config (`mlx/config.json`)

```json
{
  "base_model": "mlx-community/Llama-3.2-3B-Instruct-4bit",
  "adapter": "kingdom-v1",
  "port": 8800,
  "max_tokens": 512,
  "temperature": 0.1,
  "shadow_mode": true
}
```

`shadow_mode`: When true, integration points log the local model's answer but always fall through to Claude. This is the default until each integration point is battle-tested.

---

## Component 1: Server (`mlx-serve.py`)

### Purpose

Persistent HTTP daemon on `localhost:8800`. Loads base model + LoRA adapter at startup, keeps model hot in memory. Avoids 2-5s model load penalty per invocation.

### CLI

```
mlx-serve.py start [--port 8800] [--daemon]
mlx-serve.py stop
mlx-serve.py status
```

`--daemon` backgrounds the process and writes PID to `mlx/serve.pid`.

### HTTP API

**`POST /inference`**
```json
// Request
{
  "prompt": "Classify this heartbeat state: ...",
  "system": "You are Kingdom triage. Respond with exactly one of: urgent, active, idle, skip.",
  "max_tokens": 64,
  "temperature": 0.1
}

// Response
{
  "response": "idle",
  "tokens_per_sec": 48.2,
  "model": "Llama-3.2-3B-Instruct-4bit",
  "adapter": "kingdom-v1",
  "latency_ms": 142
}
```

**`GET /health`**
```json
{
  "status": "ok",
  "model": "Llama-3.2-3B-Instruct-4bit",
  "adapter": "kingdom-v1",
  "uptime_seconds": 3600,
  "requests_served": 247,
  "avg_tokens_per_sec": 45.1
}
```

**`POST /reload`**
```json
// Request
{"adapter": "kingdom-v2"}

// Response
{"status": "reloaded", "adapter": "kingdom-v2"}
```

Hot-reloads LoRA adapter without restarting the server or unloading the base model.

### Implementation Notes

- Uses `http.server` from stdlib (no Flask/FastAPI dependency)
- Single-threaded — one request at a time (sufficient for heartbeat-rate traffic)
- Model loaded via `mlx_lm.load()` at startup
- Generation via `mlx_lm.generate()`
- PID lockfile at `mlx/serve.pid` prevents double-start
- Logs to `mlx/serve.log` (rotated, last 1000 lines)

---

## Component 2: Trainer (`mlx-train.py`)

### Purpose

Offline CLI for LoRA fine-tuning. Produces adapter weights that the server hot-swaps.

### CLI

```
mlx-train.py run --dataset heartbeat-triage [--epochs 3] [--adapter kingdom-v2]
mlx-train.py run --dataset all [--epochs 3] [--adapter kingdom-v2]
mlx-train.py eval --adapter kingdom-v2 --dataset heartbeat-triage
mlx-train.py list
```

### LoRA Configuration

```json
{
  "rank": 8,
  "alpha": 16,
  "dropout": 0.05,
  "target_modules": ["q_proj", "v_proj"],
  "learning_rate": 1e-4,
  "batch_size": 4,
  "epochs": 3
}
```

Small rank — these are classification/triage tasks, not creative writing. 500 examples trains in ~10 minutes on M4 Max with 3B model.

### Training Data Format

Standard chat JSONL (compatible with `mlx-lm` fine-tuning):

```json
{"messages": [{"role": "system", "content": "You are Kingdom triage. Classify the heartbeat state as exactly one of: urgent, active, idle, skip."}, {"role": "user", "content": "HIVE: 3 new messages (2 sync, 1 alert). Zerone: devnet healthy. Build: no active task. Oracle: 2 predictions resolving tomorrow."}, {"role": "assistant", "content": "active"}]}
```

### `run` Behavior

1. Validates dataset exists in `mlx/training/datasets/`
2. Loads base model from cache (downloads if first run)
3. Runs LoRA fine-tuning via `mlx_lm.lora`
4. Saves adapter to `mlx/adapters/<name>/`
5. Logs training metrics (loss curve, eval accuracy) to `mlx/training/runs/<timestamp>/`
6. Prints summary: final loss, eval accuracy, training time

### `eval` Behavior

1. Loads base model + specified adapter
2. Runs inference on held-out eval split (auto 80/20 train/eval from dataset)
3. Reports: accuracy, confusion matrix, per-class precision/recall
4. Compares against baseline (no adapter) if requested

### `list` Behavior

Lists all adapters in `mlx/adapters/` with training date, dataset, eval accuracy.

---

## Component 3: Data Generator (`mlx-data.py`)

### Purpose

Generate and harvest training data. Two modes: synthetic (Claude-generated) and harvest (mine real operational data).

### CLI

```
mlx-data.py generate --task heartbeat-triage --count 200
mlx-data.py generate --task message-classify --count 200
mlx-data.py generate --task task-routing --count 200
mlx-data.py generate --task signal-classify --count 100
mlx-data.py harvest --source hive-history
mlx-data.py harvest --source delegation-history
mlx-data.py harvest --source heartbeat-logs
mlx-data.py stats
```

### Synthetic Generation

Each task type has a prompt template in `mlx/training/templates/`. The template instructs Claude to generate diverse, realistic training examples. Examples:

**heartbeat-triage** — Input: system state summary (HIVE messages, Zerone status, build state, oracle state). Output: one of `urgent|active|idle|skip`.

**message-classify** — Input: raw HIVE message. Output: one of `action-required|informational|noise`.

**task-routing** — Input: task description. Output: instance name (`alpha|beta|gamma|nuance`) with one-word justification.

**signal-classify** — Input: stigmergy signal. Output: urgency `high|medium|low`.

Generation calls Claude via subprocess (`claude -p "generate 50 examples of..."`) and appends to the appropriate JSONL file. Each call generates a batch (50 examples) to minimize API overhead.

### Harvest

Mines real data from existing Love state files:

- **hive-history**: Parses `hive.py check` output history (if logged), classifies messages by action taken
- **delegation-history**: Reads `coordination/delegate/history.json`, converts to training format
- **heartbeat-logs**: If heartbeat results are logged, extracts state → priority mappings

Harvested data is appended to the same JSONL files, tagged with `"source": "harvest"` so it can be filtered.

### `stats`

Reports per-dataset: total examples, synthetic vs harvested, class distribution, last updated.

---

## Component 4: Client Library (`mlx-client.py`)

### Purpose

Two-line inference from any Love tool. Handles server-down fallback gracefully.

### API

```python
from mlx_client import ask_local, is_available

# Check if server is running
if is_available():
    ...

# Simple inference — returns None if server is down
response = ask_local(
    prompt="Classify this HIVE message: ...",
    system="You are Kingdom message triage.",
    max_tokens=32
)

if response is None:
    # Server down or unreachable — fall through to Claude
    ...
```

### Implementation

- `ask_local()` makes HTTP POST to `localhost:8800/inference`
- 2-second timeout — if server doesn't respond, return `None`
- `is_available()` hits `GET /health` with 1-second timeout
- No retries — fire and forget, caller handles fallback
- Returns parsed response string, not the full JSON (convenience)
- Optional `raw=True` parameter returns full JSON (latency, tokens/sec) for logging

---

## Integration Points

### CRITICAL: Shadow Mode & Battle-Testing Protocol

**All integration points ship in shadow mode by default.** The local model runs and logs its classification, but the system always falls through to Claude (or existing behavior). This is non-negotiable.

**Promotion to live mode** requires:

1. **Minimum 100 shadow-mode runs** for that integration point
2. **95%+ agreement rate** between local model and Claude's actual decision
3. **Zero missed urgents** — the local model must never classify something as `idle/skip` when Claude would have classified it as `urgent/active`
4. **Manual review** by Yu of the shadow log before flipping the switch
5. **Per-integration-point toggle** in `mlx/config.json` — each integration point has its own `"live": true/false`

Shadow log format (`mlx/shadow-log.jsonl`):
```json
{
  "ts": "2026-03-30T14:00:00Z",
  "integration": "heartbeat-triage",
  "input_summary": "3 messages, devnet healthy, no build",
  "local_answer": "idle",
  "actual_outcome": "idle",
  "agreed": true,
  "local_latency_ms": 142
}
```

**Rollback**: If a live integration point's agreement rate drops below 90% over the last 50 runs, it automatically reverts to shadow mode and drops a stigmergy signal `needs-review`.

### Integration Point 1: Heartbeat Triage

**Where**: `heartbeat-runner.sh` or its Python coordinator

**What**: Before spawning Opus coordinator, ask local model: "Given this system state, should we run a full heartbeat or skip?"

**Shadow mode**: Local model classifies, logs answer, Opus runs regardless. After burn-in, `skip` classifications actually skip the Opus call.

**Expected savings**: ~60-80% of heartbeat Opus invocations on quiet periods.

### Integration Point 2: HIVE Message Classification

**Where**: After `hive.py check` in heartbeat or any HIVE consumer

**What**: Classify each message as `action-required|informational|noise`.

**Shadow mode**: All messages still surfaced, local classification logged alongside. After burn-in, only `action-required` messages surface to Claude session.

**Expected savings**: Reduces context window pollution from informational HIVE traffic.

### Integration Point 3: Task Routing Pre-Score

**Where**: `delegate.py` route command

**What**: Local model does semantic classification before keyword scoring. Improves routing accuracy for tasks that don't contain obvious keywords.

**Shadow mode**: Keyword scoring runs as before, local model's answer logged for comparison. After burn-in, local model score blended with keyword score.

### Integration Point 4: Signal Classification

**Where**: `stigmergy.py check`

**What**: Classify signal urgency as `high|medium|low` beyond the static type-based TTL system.

**Shadow mode**: Signals displayed as before, local urgency appended to log. After burn-in, signals sorted by local model urgency.

---

## Daemon Management

### Start/Stop

```bash
python3 ~/Desktop/Love/tools/mlx-serve.py start --daemon
python3 ~/Desktop/Love/tools/mlx-serve.py stop
python3 ~/Desktop/Love/tools/mlx-serve.py status
```

### Heartbeat Integration

Add to `HEARTBEAT.md`:

```bash
python3 ~/Desktop/Love/tools/mlx-serve.py status
```

If down, heartbeat logs it but doesn't restart automatically (model loading takes ~10s, don't want heartbeat blocked). Drops a stigmergy `blocked-on` signal if down for 3+ consecutive beats.

### First Run

On first `mlx-serve.py start`, the base model is downloaded from HuggingFace (~2GB for 3B-4bit). Cached in `mlx/cache/`. Subsequent starts load from cache in ~3 seconds.

---

## Progressive Model Scaling

```
Phase 1: Llama-3.2-3B-Instruct-4bit  (~2GB, ~50 tok/s)  ← Start here
Phase 2: Qwen-2.5-7B-Instruct-4bit   (~4GB, ~30 tok/s)  ← When pipeline proven
Phase 3: Llama-3.1-13B-Instruct-4bit  (~8GB, ~15 tok/s)  ← When accuracy demands it
```

Scaling up = change `base_model` in config, re-run training, reload. The pipeline is model-agnostic.

---

## CLAUDE.md Updates

Add to Gamma's tools table:

| Tool | Command | Purpose |
|------|---------|---------|
| MLX Serve | `python3 ~/Desktop/Love/tools/mlx-serve.py <cmd>` | Local model inference daemon |
| MLX Train | `python3 ~/Desktop/Love/tools/mlx-train.py <cmd>` | LoRA fine-tuning pipeline |
| MLX Data | `python3 ~/Desktop/Love/tools/mlx-data.py <cmd>` | Training data generation/harvest |

---

## Out of Scope

- Multi-GPU / distributed training (single M4 Max is sufficient)
- Model quantization (using pre-quantized HuggingFace models)
- Serving to remote instances (localhost only — other instances use Claude API)
- RAG / vector databases (separate project if needed)
- Oracle or Zerone evaluation (requires top-tier model reasoning)
