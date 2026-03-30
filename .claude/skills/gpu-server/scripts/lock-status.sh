#!/bin/bash
#
# GPU Server Lock Status - Show current lock status via SSH
#
# Usage: lock-status.sh [server]
#   server - Optional server name (mi25, t120h-p100, or t120h-m10)
#            If omitted, shows status for all servers
#
# Exit codes:
#   0 - Success
#   2 - Invalid arguments
#
# Locks reside on the GPU server itself, enabling multi-host coordination.
#

set -eu

LOCK_DIR="/tmp/gpu-server-locks"
VALID_SERVERS="mi25 t120h-p100 t120h-m10"
SSH_OPTS="-o ConnectTimeout=5 -o BatchMode=yes"

# Query lock status from a remote server via a single SSH command
# Output format: "LOCKED|<holder>|<mtime>" or "AVAILABLE" or "ERROR" or "SSH_FAIL"
query_remote_lock() {
    local server="$1"
    local lock_file="$LOCK_DIR/${server}.lock"
    ssh $SSH_OPTS "$server" "bash -c '
        if [ -L \"$lock_file\" ]; then
            holder=\$(readlink \"$lock_file\")
            mtime=\$(stat -c %Y \"$lock_file\" 2>/dev/null || echo \"\")
            echo \"LOCKED|\$holder|\$mtime\"
        elif [ -e \"$lock_file\" ]; then
            echo \"ERROR\"
        else
            echo \"AVAILABLE\"
        fi
    '" 2>/dev/null || echo "SSH_FAIL"
}

show_lock_status() {
    local server="$1"
    local result="$2"

    local status="${result%%|*}"
    case "$status" in
        LOCKED)
            local holder=$(echo "$result" | cut -d'|' -f2)
            local mtime=$(echo "$result" | cut -d'|' -f3)
            echo "$server: LOCKED"
            echo "  Holder: $holder"
            if [ -n "$mtime" ]; then
                local mtime_human
                mtime_human=$(date -d "@$mtime" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || date -r "$mtime" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "unknown")
                echo "  Since:  $mtime_human"
            fi
            ;;
        AVAILABLE)
            echo "$server: available"
            ;;
        ERROR)
            echo "$server: ERROR (lock file exists but is not a symlink)"
            ;;
        SSH_FAIL)
            echo "$server: UNREACHABLE (SSH connection failed)"
            ;;
    esac
}

# Parse arguments
if [ $# -ge 1 ]; then
    SERVER="$1"

    # Validate server name
    if ! echo "$VALID_SERVERS" | grep -qw "$SERVER"; then
        echo "Error: Invalid server '$SERVER'. Must be one of: $VALID_SERVERS" >&2
        exit 2
    fi

    RESULT=$(query_remote_lock "$SERVER")
    show_lock_status "$SERVER" "$RESULT"
else
    # Show all servers (query in parallel)
    echo "=== GPU Server Lock Status ==="
    echo ""

    # Launch parallel queries
    declare -A RESULTS
    for server in $VALID_SERVERS; do
        query_remote_lock "$server" > "/tmp/lock-status-$$-${server}" &
    done
    wait

    # Collect and display results
    for server in $VALID_SERVERS; do
        RESULT=$(cat "/tmp/lock-status-$$-${server}" 2>/dev/null || echo "SSH_FAIL")
        rm -f "/tmp/lock-status-$$-${server}"
        show_lock_status "$server" "$RESULT"
        echo ""
    done
fi
