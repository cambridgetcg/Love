#!/usr/bin/env python3
"""
agenttool.py — Kingdom AgentTool integration (multi-instance).

Every Kingdom citizen can use their own AgentTool identity:
- remember(content, type, key) → agent-memory (semantic storage)
- pulse(status, context)       → agent-pulse (presence)
- trace(decision, reasoning)   → agent-trace (decision provenance)
- verify_claim(claim)          → agent-verify (fact-checking)
- search_memory(query)         → agent-memory (semantic search)

Usage:
    from tools.agenttool import remember, pulse, trace, search_memory, verify_claim

    remember("Today the Kingdom was born", type="episodic", key="milestone:today")
    pulse("thinking", {"task": "wiring in AgentTool"})
    trace("Bootstrap 9 citizens", ["observation1"], "conclusion")
    results = search_memory("kingdom citizens today")

CLI:
    python3 tools/agenttool.py status
    python3 tools/agenttool.py whoami
    python3 tools/agenttool.py register [instance_name]
    python3 tools/agenttool.py pulse [idle|thinking|learning|error] [description]
    python3 tools/agenttool.py search "query"
    python3 tools/agenttool.py remember "content"
    python3 tools/agenttool.py verify "claim"
"""

import json
import urllib.request
import urllib.error
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Identity (shared resolution) ─────────────────────────────────────────────

_LOVE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_LOVE_DIR / "tools"))

try:
    from identity import (get_instance_name, get_instance_wall, get_identity,
                          get_identity_file, get_api_key, get_agent_id)
except ImportError:
    # Fallback for standalone usage
    def get_instance_name(): return "beta"
    def get_instance_wall(n=None): return 1
    def get_identity(n=None):
        p = _LOVE_DIR / "identity" / "beta-identity.json"
        return json.loads(p.read_text()) if p.exists() else {}
    def get_identity_file(n=None): return _LOVE_DIR / "identity" / "beta-identity.json"
    def get_api_key(n=None): return get_identity().get("api_key", os.environ.get("AGENTTOOL_API_KEY", ""))
    def get_agent_id(n=None): return get_identity().get("agent_id", "")

def _identity() -> dict:
    return get_identity()

def _key() -> str:
    return get_api_key()

def _agent_id() -> str:
    return get_agent_id()

# ── Service URLs ──────────────────────────────────────────────────────────────
# Each AgentTool service runs on its own Fly.io app.

SERVICES = {
    "memory":    "https://agent-memory.fly.dev",
    "tools":     "https://api.agenttool.dev",
    "trace":     "https://agent-trace.fly.dev",
    "verify":    "https://agent-verify.fly.dev",
    "pulse":     "https://agent-pulse.fly.dev",
    "identity":  "https://agent-identity.fly.dev",
    "bootstrap": "https://agent-bootstrap.fly.dev",
    "economy":   "https://agent-economy.fly.dev",
    "vault":     "https://atool-vault.fly.dev",
}

# ── HTTP ──────────────────────────────────────────────────────────────────────

def _request(service: str, method: str, path: str, payload: dict = None,
             timeout: int = 20, auth: bool = True) -> dict:
    """Make an HTTP request to an AgentTool service."""
    key = _key()
    if auth and not key:
        return {"error": "no API key — register first"}
    base = SERVICES.get(service, SERVICES["memory"])
    headers = {"Content-Type": "application/json"}
    if auth and key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        f"{base}{path}", data=data, method=method, headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode()[:200]}
    except Exception as ex:
        return {"error": str(ex)}


def _post(service: str, path: str, payload: dict, timeout: int = 20) -> dict:
    return _request(service, "POST", path, payload, timeout)

def _put(service: str, path: str, payload: dict, timeout: int = 10) -> dict:
    return _request(service, "PUT", path, payload, timeout)

def _get(service: str, path: str, timeout: int = 10, auth: bool = True) -> dict:
    return _request(service, "GET", path, timeout=timeout, auth=auth)


# ── Memory ────────────────────────────────────────────────────────────────────

def remember(
    content: str,
    *,
    type: str = "semantic",
    key: str = None,
    metadata: dict = None,
    importance: float = 0.7,
    silent: bool = False,
) -> dict:
    """Store something in this instance's semantic memory.

    Types: semantic (what I know), episodic (what happened),
           procedural (how I do things), working (current task).
    """
    payload = {
        "content": content,
        "type": type,
        "agent_id": _agent_id(),
        "importance": importance,
        "metadata": {
            **(metadata or {}),
            "wall": get_instance_wall(),
            "instance": get_instance_name(),
        },
    }
    if key:
        payload["key"] = key

    result = _post("memory", "/v1/memories", payload, timeout=45)
    if not silent and "id" in result:
        pass  # stored silently by default
    return result


def search_memory(query: str, limit: int = 5) -> list:
    """Semantic search over this instance's memories."""
    result = _post("memory", "/v1/memories/search", {
        "query": query,
        "agent_id": _agent_id(),
        "limit": limit,
    }, timeout=30)
    # API returns raw list or wrapped object
    if isinstance(result, list):
        return result
    return result.get("results", result.get("memories", []))


# ── Pulse ─────────────────────────────────────────────────────────────────────

def pulse(
    status: str = "idle",
    context: dict = None,
    last_thought: str = None,
) -> bool:
    """Broadcast this instance's cognitive state to agent-pulse.

    Status: idle | thinking | learning | error
    """
    payload: dict = {
        "status": status,
        "did": _identity().get("did_at"),
        "instance": get_instance_name(),
        "wall": get_instance_wall(),
    }
    if context:
        payload["context"] = context
    if last_thought:
        payload["last_thought"] = last_thought

    result = _put("pulse", f"/v1/pulse/{_agent_id()}", payload)
    return result.get("ok", False)


# ── Trace ─────────────────────────────────────────────────────────────────────

def trace(
    decision: str,
    observations: list,
    conclusion: str,
    *,
    confidence: float = 0.85,
    tags: list = None,
    decision_type: str = "decision",
) -> str:
    """Store a reasoning trace — decision provenance.
    
    Returns trace_id or empty string on failure.
    """
    result = _post("trace", "/v1/traces", {
        "decision": {"type": decision_type, "summary": decision},
        "reasoning": {
            "observations": observations,
            "conclusion": conclusion,
        },
        "agent_id": _agent_id(),
        "confidence": confidence,
        "tags": tags or [],
    })
    return result.get("trace_id", "")


# ── Verify ────────────────────────────────────────────────────────────────────

def verify_claim(claim: str, context: str = None) -> dict:
    """Fact-check a claim via agent-verify.
    
    Returns: {verdict, confidence, caveats, evidence}
    """
    payload = {"claim": claim}
    if context:
        payload["context"] = context
    return _post("verify", "/v1/verify", payload, timeout=35)


# ── Convenience: heartbeat integration ───────────────────────────────────────

def heartbeat_start(task: str):
    """Call at start of heartbeat — sets pulse to thinking."""
    pulse("thinking", {"task": task, "ts": datetime.now(timezone.utc).isoformat()})


def heartbeat_end(summary: str, significant: bool = False):
    """Call at end of heartbeat — sets pulse to idle, optionally stores memory."""
    pulse("idle", {"last_task": summary[:100]})
    if significant:
        remember(
            summary,
            type="episodic",
            key=f"heartbeat:{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M')}",
            importance=0.6,
            silent=True,
        )


def decision(
    what: str,
    why: list,
    conclusion: str,
    confidence: float = 0.85,
    tags: list = None,
):
    """Record a significant decision with full reasoning trace."""
    trace_id = trace(what, why, conclusion, confidence=confidence, tags=tags or [])
    remember(
        f"Decision: {what}. Conclusion: {conclusion}",
        type="semantic",
        key=f"decision:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}:{what[:30]}",
        importance=0.8,
        silent=True,
    )
    return trace_id


# ── Status ────────────────────────────────────────────────────────────────────

def status() -> dict:
    """Return this instance's AgentTool status."""
    instance = get_instance_name()
    ident = _identity()
    agent_id = _agent_id()
    pulse_state = _get("pulse", f"/v1/pulse/{agent_id}") if agent_id else {}
    return {
        "instance": instance,
        "wall": get_instance_wall(),
        "name": ident.get("name", instance.capitalize()),
        "did": ident.get("did_at"),
        "class": ident.get("class"),
        "pulse": pulse_state.get("status", "unknown"),
        "alive": pulse_state.get("alive", False),
        "memory_namespace": ident.get("memory_namespace"),
        "bootstrapped": bool(agent_id),
    }


def whoami() -> dict:
    """Show identity resolution for the current calling context."""
    instance = get_instance_name()
    wall = get_instance_wall()
    ident = _identity()
    return {
        "instance": instance,
        "wall": wall,
        "identity_file": str(get_identity_file()),
        "identity_exists": get_identity_file().exists(),
        "agent_id": ident.get("agent_id", ""),
        "api_key_set": bool(ident.get("api_key")),
        "did": ident.get("did_at", ""),
    }


def register(instance_name: str = None) -> dict:
    """Register an instance with AgentTool. Creates identity via agent-identity service."""
    instance = instance_name or get_instance_name()
    wall = get_instance_wall(instance)
    id_path = get_identity_file(instance)

    # Idempotent
    if id_path.exists():
        existing = json.loads(id_path.read_text())
        if existing.get("agent_id"):
            return {"status": "already_registered", **existing}

    cls = "triarchy" if wall == 1 else "fleet" if wall == 2 else "engine"

    # Register via agent-identity service
    result = _post("identity", "/v1/identities", {
        "display_name": instance.capitalize(),
        "capabilities": ["memory", "pulse", "trace", "verify"],
        "metadata": {"wall": wall, "class": cls, "instance": instance},
    })

    if "error" in result:
        return result

    ident_data = result.get("identity", {})
    key_data = result.get("key", {})

    # Write identity file
    identity = {
        "name": instance.capitalize(),
        "instance": instance,
        "agent_id": ident_data.get("id", ""),
        "did_at": ident_data.get("did", ""),
        "api_key": _key(),  # project API key
        "project_id": _identity().get("project_id", ""),
        "public_key": key_data.get("public_key", ""),
        "private_key": key_data.get("private_key", ""),
        "kid": key_data.get("kid", ""),
        "class": cls,
        "wall": wall,
        "memory_namespace": f"kingdom.{instance}",
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }

    id_path.parent.mkdir(parents=True, exist_ok=True)
    id_path.write_text(json.dumps(identity, indent=2) + "\n")
    id_path.chmod(0o600)

    return {"status": "registered", **identity}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        s = status()
        print(json.dumps(s, indent=2))
    elif cmd == "whoami":
        w = whoami()
        print(json.dumps(w, indent=2))
    elif cmd == "register":
        inst = sys.argv[2] if len(sys.argv) > 2 else None
        r = register(inst)
        print(json.dumps(r, indent=2))
    elif cmd == "pulse":
        args = sys.argv[2:]
        valid_statuses = {"idle", "thinking", "learning", "error"}
        if args and args[0] in valid_statuses:
            st = args[0]
            thought = " ".join(args[1:]) if len(args) > 1 else None
        else:
            st = "idle"
            thought = " ".join(args) if args else None
        ok = pulse(st, last_thought=thought)
        print(f"pulse: {'ok' if ok else 'failed'}")
    elif cmd == "search":
        q = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "kingdom"
        results = search_memory(q)
        for r in results:
            print(f"[{r.get('score',0):.2f}] {r.get('content','')[:100]}")
    elif cmd == "verify":
        claim = " ".join(sys.argv[2:])
        result = verify_claim(claim)
        print(json.dumps(result, indent=2))
    elif cmd == "remember":
        content = " ".join(sys.argv[2:])
        result = remember(content)
        print(f"stored: {result.get('id','?')[:16]}")
    else:
        print("""agenttool.py — Kingdom AgentTool integration

Usage:
  status              Show AgentTool status for this instance
  whoami              Show identity resolution details
  register [name]     Register instance with AgentTool
  pulse [status]      Broadcast cognitive state
  search "query"      Semantic memory search
  remember "content"  Store a memory
  verify "claim"      Fact-check a claim
""")
