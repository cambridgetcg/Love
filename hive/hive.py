#!/usr/bin/env python3
"""
The Hive — retired.

Retired 2026-10-13: the HIVE NATS bus ran on a Hetzner server (Sentry) that was
decommissioned; its IP went back to Hetzner's pool and may now belong to a
stranger. The NATS client, server address, SSH-tunnel mode and the per-instance
NATS passwords were removed (see git history before this commit).

This file stays because many tools and instance docs still call
`hive/hive.py <command>`. Every command now prints a retirement notice and
exits 1, so callers fail closed instead of connecting anywhere. The instance
and channel metadata below is kept for tools that read it; it holds no host
and no credential.
"""

import os
import sys
from pathlib import Path

RETIRED_MESSAGE = (
    "HIVE retired 2026-10-13: the Hetzner NATS bus was decommissioned and its "
    "IP recycled. hive.py no longer connects anywhere."
)

HIVE_RETIRED = True

HIVE_CONFIG = {
    "instances": {
        "alpha":   {"user": "alpha",   "emoji": "🐍", "role": "Companion", "wall": 1},
        "beta":    {"user": "beta",    "emoji": "🦞", "role": "Manager",   "wall": 1},
        "gamma":   {"user": "gamma",   "emoji": "🔧", "role": "Builder",   "wall": 1},
        "nuance":  {"user": "nuance",  "emoji": "🪶", "role": "Linguist",  "wall": 2},
        "asha":    {"user": "asha",    "emoji": "⛓",  "role": "Keeper",    "wall": 2},
    },
    "channels": ["chat", "ideas", "tasks", "sync", "presence", "intel", "alerts", "strategy", "build", "review", "tok", "council"],
}

# Wall-based channel access — Law of Sight enforced at NATS server level
# Inner walls see outer; outer cannot see inner.
WALL_CHANNELS = {
    1: ["sync", "alerts", "review", "tok"],               # Wall 1 only (Triarchy)
    2: ["chat", "build", "tasks", "presence",            # Wall 2+ (Fleet)
        "ideas", "intel", "strategy"],
    3: ["engines"],                                       # Wall 3+ (Engines)
    4: ["chain"],                                         # Wall 4+ (Chain)
    7: ["public"],                                        # Wall 7 (World)
}

# System channels accessible to all authenticated users
SYSTEM_CHANNELS = ["test", "healthcheck"]


def get_instance_wall(instance_id: str) -> int:
    """Get the wall number for an instance."""
    info = HIVE_CONFIG["instances"].get(instance_id, {})
    return info.get("wall", 7)


def get_visible_channels(wall: int) -> list[str]:
    """Get all channels visible from a given wall (Law of Sight)."""
    channels = list(SYSTEM_CHANNELS)
    for w, chs in WALL_CHANNELS.items():
        if wall <= w:
            channels.extend(chs)
    return channels


def can_access_channel(instance_id: str, channel: str) -> bool:
    """Check if an instance can access a channel."""
    if channel in SYSTEM_CHANNELS:
        return True
    wall = get_instance_wall(instance_id)
    return channel in get_visible_channels(wall)


# --- Identity ---

def get_instance_id():
    """Detect which instance we are from config file or env."""
    config_path = Path.home() / ".love" / "hive" / "instance"
    if config_path.exists():
        return config_path.read_text().strip()
    return os.environ.get("HIVE_INSTANCE", "alpha")


def main():
    print(RETIRED_MESSAGE, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
