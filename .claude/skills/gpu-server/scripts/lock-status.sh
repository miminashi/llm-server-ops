#!/bin/bash
#
# GPU Server Lock Status - Show current lock status
#
# Usage: lock-status.sh [server]
#   server - Optional server name (mi25 or t120h-p100)
#            If omitted, shows status for all servers
#
# Exit codes:
#   0 - Success
#   2 - Invalid arguments
#

set -eu

LOCK_DIR="/tmp/gpu-server-locks"
VALID_SERVERS="mi25 t120h-p100 t120h-m10"

show_lock_status() {
    local server="$1"
    local lock_file="$LOCK_DIR/${server}.lock"

    if [ -L "$lock_file" ]; then
        local holder=$(readlink "$lock_file")
        local mtime=$(stat -c %Y "$lock_file" 2>/dev/null || stat -f %m "$lock_file" 2>/dev/null)
        local mtime_human=$(date -d "@$mtime" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || date -r "$mtime" "+%Y-%m-%d %H:%M:%S" 2>/dev/null)
        echo "$server: LOCKED"
        echo "  Holder: $holder"
        echo "  Since:  $mtime_human"
    elif [ -e "$lock_file" ]; then
        echo "$server: ERROR (lock file exists but is not a symlink)"
    else
        echo "$server: available"
    fi
}

# Parse arguments
if [ $# -ge 1 ]; then
    SERVER="$1"

    # Validate server name
    if ! echo "$VALID_SERVERS" | grep -qw "$SERVER"; then
        echo "Error: Invalid server '$SERVER'. Must be one of: $VALID_SERVERS" >&2
        exit 2
    fi

    show_lock_status "$SERVER"
else
    # Show all servers
    echo "=== GPU Server Lock Status ==="
    echo ""
    for server in $VALID_SERVERS; do
        show_lock_status "$server"
        echo ""
    done
fi
