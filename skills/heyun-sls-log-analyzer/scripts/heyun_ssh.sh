#!/usr/bin/env bash
# heyun_ssh.sh — run a read-only command (or open a shell) on the heyun SLS server
# using password auth. Credentials come from ~/.ssh/server/heyun.json.
#
# Usage:
#   ./heyun_ssh.sh                       # open an interactive shell
#   ./heyun_ssh.sh 'journalctl -p err -n 100 --no-pager'   # run one command
#   echo 'uptime' | ./heyun_ssh.sh -     # read the command from stdin
#
# Reason: the password lives in a JSON5-ish file (unquoted keys/values), so we
# parse it with python instead of jq, and feed it to sshpass via an env var
# (SSHPASS) so the password never appears in the process list / shell history.

set -euo pipefail

CRED_FILE="${HEYUN_CRED_FILE:-$HOME/.ssh/server/heyun.json}"

if [[ ! -f "$CRED_FILE" ]]; then
  echo "credentials file not found: $CRED_FILE" >&2
  exit 1
fi

if ! command -v sshpass >/dev/null 2>&1; then
  echo "sshpass is required. Install it: brew install sshpass (or hudochenkov/sshpass/sshpass)" >&2
  exit 1
fi

# Parse the loose JSON (handles unquoted keys/values like {ip: 1.2.3.4, user: root}).
read -r HEYUN_IP HEYUN_USER HEYUN_PORT < <(python3 - "$CRED_FILE" <<'PY'
import re, sys
raw = open(sys.argv[1]).read()
def grab(key):
    m = re.search(r'%s\s*:\s*"?([^",}\s]+)"?' % key, raw)
    return m.group(1) if m else ""
print(grab("ip"), grab("user"), grab("port") or "22")
PY
)

# Password parsed separately so it is never echoed.
SSHPASS="$(python3 - "$CRED_FILE" <<'PY'
import re, sys
raw = open(sys.argv[1]).read()
m = re.search(r'password\s*:\s*"?([^",}\s]+)"?', raw)
print(m.group(1) if m else "")
PY
)"
export SSHPASS

if [[ -z "$HEYUN_IP" || -z "$HEYUN_USER" || -z "$SSHPASS" ]]; then
  echo "failed to parse ip/user/password from $CRED_FILE" >&2
  exit 1
fi

SSH_OPTS=(-p "$HEYUN_PORT" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)

if [[ $# -eq 0 ]]; then
  exec sshpass -e ssh "${SSH_OPTS[@]}" "$HEYUN_USER@$HEYUN_IP"
elif [[ "$1" == "-" ]]; then
  CMD="$(cat)"
  exec sshpass -e ssh "${SSH_OPTS[@]}" "$HEYUN_USER@$HEYUN_IP" "$CMD"
else
  exec sshpass -e ssh "${SSH_OPTS[@]}" "$HEYUN_USER@$HEYUN_IP" "$*"
fi
