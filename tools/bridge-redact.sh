# bridge-redact.sh — shared deny-regex for the memory bridge (sourced, not executed).
#
# Any digest line matching this is DROPPED before it can cross into the Claude Code
# auto-memory. Strictly conservative: only ever redacts MORE, never less. Covers
# generic credentials + the Kingdom HIVE secret shape (44-char base64 NaCl key,
# .hive-key references) + the known NATS host. Used by bridge-digest.sh + kosmem-digest.sh.
BRIDGE_REDACT='password|secret|sk-[A-Za-z0-9]{8}|gh[oprsu]_[A-Za-z0-9]|AKIA[0-9A-Z]{12}|PRIVATE KEY|api[_-]?key|token=|refresh_token|hive-key|[A-Za-z0-9+/]{43}=|135\.181\.28\.252'
