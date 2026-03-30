#!/bin/bash
#
# GPU Server Lock - Acquire exclusive lock via SSH on the GPU server
#
# Usage: lock.sh <server> [session_id]
#   server     - Server name (mi25, t120h-p100, or t120h-m10)
#   session_id - Optional session identifier (default: hostname-pid-timestamp)
#
# Exit codes:
#   0 - Lock acquired successfully
#   1 - Lock already held by another session
#   2 - Invalid arguments
#   3 - SSH connection failed
#
# The lock uses symbolic link atomicity on the remote server:
#   ln -s fails if target exists, making lock acquisition atomic
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
SESSION_ID="${2:-$(hostname)-$$-$(date +%Y%m%d_%H%M%S)}"

# Validate server name
if ! echo "$VALID_SERVERS" | grep -qw "$SERVER"; then
    echo "Error: Invalid server '$SERVER'. Must be one of: $VALID_SERVERS" >&2
    exit 2
fi

LOCK_FILE="$LOCK_DIR/${SERVER}.lock"

# Attempt to acquire lock using atomic symlink creation on the remote server
if ssh $SSH_OPTS "$SERVER" "mkdir -p '$LOCK_DIR' && ln -s '$SESSION_ID' '$LOCK_FILE'" 2>/dev/null; then
    echo "Lock acquired: $SERVER (session: $SESSION_ID)"
    exit 0
else
    # Check if it's an SSH failure or a lock contention
    HOLDER=$(ssh $SSH_OPTS "$SERVER" "readlink '$LOCK_FILE' 2>/dev/null" 2>/dev/null || true)
    if [ -n "$HOLDER" ]; then
        echo "Lock held by: $HOLDER" >&2
        echo "Error: Failed to acquire lock for $SERVER" >&2
        exit 1
    else
        echo "Error: SSH connection to $SERVER failed or unexpected error" >&2
        exit 3
    fi
fi
