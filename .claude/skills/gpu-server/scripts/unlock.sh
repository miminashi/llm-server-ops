#!/bin/bash
#
# GPU Server Unlock - Release exclusive lock via SSH on the GPU server
#
# Usage: unlock.sh <server> [session_id]
#   server     - Server name (mi25, t120h-p100, or t120h-m10)
#   session_id - Optional session identifier (validates ownership before release)
#
# Exit codes:
#   0 - Lock released successfully
#   1 - Lock not held or held by different session
#   2 - Invalid arguments
#   3 - SSH connection failed
#
# If session_id is provided, the lock will only be released if it matches.
# If session_id is omitted, the lock will be released regardless of owner.
# Locks reside on the GPU server itself, enabling multi-host coordination.
#

set -eu

LOCK_DIR="/tmp/gpu-server-locks"
VALID_SERVERS="mi25 t120h-p100 t120h-m10"
SSH_OPTS="-o ConnectTimeout=5 -o BatchMode=yes"

# Parse arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <server> [session_id]" >&2
    echo "  server: mi25, t120h-p100, or t120h-m10" >&2
    exit 2
fi

SERVER="$1"
SESSION_ID="${2:-}"

# Validate server name
if ! echo "$VALID_SERVERS" | grep -qw "$SERVER"; then
    echo "Error: Invalid server '$SERVER'. Must be one of: $VALID_SERVERS" >&2
    exit 2
fi

LOCK_FILE="$LOCK_DIR/${SERVER}.lock"

# Check if lock exists on the remote server
LOCK_EXISTS=$(ssh $SSH_OPTS "$SERVER" "test -L '$LOCK_FILE' && echo yes || echo no" 2>/dev/null) || {
    echo "Error: SSH connection to $SERVER failed" >&2
    exit 3
}

if [ "$LOCK_EXISTS" != "yes" ]; then
    echo "No lock exists for $SERVER"
    exit 0
fi

# If session_id is provided, validate ownership
if [ -n "$SESSION_ID" ]; then
    HOLDER=$(ssh $SSH_OPTS "$SERVER" "readlink '$LOCK_FILE'" 2>/dev/null) || {
        echo "Error: SSH connection to $SERVER failed" >&2
        exit 3
    }
    if [ "$HOLDER" != "$SESSION_ID" ]; then
        echo "Error: Lock is held by different session: $HOLDER" >&2
        echo "Your session: $SESSION_ID" >&2
        exit 1
    fi
fi

# Release the lock
HOLDER=$(ssh $SSH_OPTS "$SERVER" "readlink '$LOCK_FILE'" 2>/dev/null || true)
if ssh $SSH_OPTS "$SERVER" "rm '$LOCK_FILE'" 2>/dev/null; then
    echo "Lock released: $SERVER (was held by: $HOLDER)"
    exit 0
else
    echo "Error: Failed to release lock for $SERVER" >&2
    exit 1
fi
