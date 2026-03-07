#!/bin/bash
#
# GPU Server Lock - Acquire exclusive lock using symbolic link
#
# Usage: lock.sh <server> [session_id]
#   server     - Server name (mi25 or t120h-p100)
#   session_id - Optional session identifier (default: hostname-pid-timestamp)
#
# Exit codes:
#   0 - Lock acquired successfully
#   1 - Lock already held by another session
#   2 - Invalid arguments
#
# The lock uses symbolic link atomicity:
#   ln -s fails if target exists, making lock acquisition atomic
#

set -eu

LOCK_DIR="/tmp/gpu-server-locks"
VALID_SERVERS="mi25 t120h-p100 t120h-m10"

# Parse arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <server> [session_id]" >&2
    echo "  server: mi25 or t120h-p100" >&2
    exit 2
fi

SERVER="$1"
SESSION_ID="${2:-$(hostname)-$$-$(date +%Y%m%d_%H%M%S)}"

# Validate server name
if ! echo "$VALID_SERVERS" | grep -qw "$SERVER"; then
    echo "Error: Invalid server '$SERVER'. Must be one of: $VALID_SERVERS" >&2
    exit 2
fi

# Create lock directory if it doesn't exist
mkdir -p "$LOCK_DIR"

LOCK_FILE="$LOCK_DIR/${SERVER}.lock"

# Attempt to acquire lock using atomic symlink creation
# ln -s will fail if the symlink already exists
if ln -s "$SESSION_ID" "$LOCK_FILE" 2>/dev/null; then
    echo "Lock acquired: $SERVER (session: $SESSION_ID)"
    exit 0
else
    # Lock already exists - show who holds it
    if [ -L "$LOCK_FILE" ]; then
        HOLDER=$(readlink "$LOCK_FILE")
        echo "Lock held by: $HOLDER" >&2
        echo "Error: Failed to acquire lock for $SERVER" >&2
    else
        echo "Error: Lock file exists but is not a symlink: $LOCK_FILE" >&2
    fi
    exit 1
fi
