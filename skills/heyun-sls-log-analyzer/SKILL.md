---
name: heyun-sls-log-analyzer
description: "Analyze heyun (禾云) SLS Linux server logs via SSH using password (account + password) authentication. Use for server-log triage and incident investigation: systemd/journalctl/syslog errors, nginx/apache access+error logs (4xx/5xx spikes like 502/504), SSH/auth logs (brute-force, suspicious IPs), Docker/container logs, and produce a concise report with likely causes + next actions. Credentials are loaded from ~/.ssh/server/heyun.json (ip/user/password/port). Two connection paths: direct password SSH, or via Cloudflare Tunnel (ssh heyun-cf) when the public IP/port is firewalled. Triggers: heyun/禾云/SLS/服务器日志/nginx access.log/error.log/journalctl/auth.log/secure/502/504/被攻击/爆量/cloudflare tunnel/heyun-cf."
---

# heyun SLS Log Analyzer

## Overview

Triage and analyze logs from a heyun SLS Linux server. Connect via SSH using
**account + password** authentication (no key file), collect a time-bounded,
mostly read-only slice of system/web/app/auth logs, summarize anomalies
(errors, spikes, suspicious IPs), and produce an actionable incident report.

## Default target (credentials)

Connection details are stored in `~/.ssh/server/heyun.json`:

```json
{ "ip": "...", "user": "...", "password": "...", "port": 22 }
```

- The file uses a loose JSON5 style (unquoted keys/values are tolerated).
- **Never paste the password into the chat, command line, or report.** The
  bundled helper feeds it to `ssh` via the `SSHPASS` env var so it never appears
  in the process list or shell history.

### Prerequisite: sshpass

Password-based SSH automation needs `sshpass`:

```bash
brew install hudochenkov/sshpass/sshpass   # macOS
# or: sudo apt-get install sshpass         # Debian/Ubuntu
```

### Connect via the bundled helper

```bash
cd <PATH_TO_SKILL_FOLDER>

# Open an interactive shell:
./scripts/heyun_ssh.sh

# Run a single read-only command:
./scripts/heyun_ssh.sh 'journalctl -p err -n 100 --no-pager'

# Pipe a command in (and pipe output to a local analyzer):
echo 'sudo tail -n 200000 /var/log/nginx/access.log' | ./scripts/heyun_ssh.sh -
```

> Manual equivalent (if you prefer not to use the helper):
> `sshpass -p '<password>' ssh -p <port> <user>@<ip>` — but prefer the helper so
> the password is not exposed on the command line.

### Alternative: connect via Cloudflare Tunnel (`ssh heyun-cf`)

If the public SSH port is firewalled/blocked (symptom: TCP 22 reachable but the
connection is dropped *before* the SSH banner —
`kex_exchange_identification: Connection closed by remote host`), use the
Cloudflare Tunnel path instead. A `heyun-ssh` tunnel exposes the server's
`localhost:22` as `heyun-ssh.razet.me`, reachable without the public IP.

```bash
# Direct alias (defined in ~/.ssh/config, uses cloudflared ProxyCommand):
ssh heyun-cf
# Equivalent:
ssh heyun-ssh.razet.me
```

The `~/.ssh/config` entry that makes this work:

```sshconfig
Host heyun-ssh.razet.me heyun-cf
    HostName heyun-ssh.razet.me
    User root
    ProxyCommand /opt/homebrew/bin/cloudflared access ssh --hostname %h
    StrictHostKeyChecking accept-new
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

To run a one-off read-only command over the tunnel with password auth (mirrors
the helper's no-leak pattern — password fed via `SSHPASS`):

```bash
PW="$(python3 -c "import re;raw=open('$HOME/.ssh/server/heyun.json').read();import sys;m=re.search(r'password\s*:\s*\"?([^\",}\s]+)\"?',raw);print(m.group(1))")"
SSHPASS="$PW" sshpass -e ssh heyun-cf 'journalctl -p err -n 100 --no-pager'
```

**Tunnel infrastructure (already provisioned):**
- Cloudflare account `razet.me`; API creds in `~/.ssh/cloudfare/cf.env`
  (`CF_API_TOKEN`/`ACCOUNT_ID`/`ZONE_ID`). Manage via the
  `cloudflare-tunnel-api` skill.
- Tunnel name `heyun-ssh`, ID `845f3953-0c92-4c57-9f48-b16403fa5ed4`
  (config_src=cloudflare, remote-managed).
- DNS `heyun-ssh.razet.me` CNAME → `<TUNNEL_ID>.cfargotunnel.com` (proxied);
  ingress `heyun-ssh.razet.me → ssh://localhost:22`.
- Server connector: `cloudflared` installed via RPM, running as systemd service
  `cloudflared` (enabled, token mode).
- **Do not touch the `runpaceflow` tunnel** — it carries the business domains
  `runpaceflow.razet.me` / `majiang-admin.razet.me`.

To re-provision the tunnel from scratch (after a server rebuild), use the
`cloudflare-tunnel-api` skill: create tunnel → set ingress to
`ssh://localhost:22` → CNAME the hostname → install cloudflared on the server
with `cloudflared service install <TUNNEL_TOKEN>`.

## Quick start (ask for these)

- Time window (e.g. last 2h / last 24h) and server timezone
- Observed symptoms (e.g. 502 spikes, CPU 100%, login brute-force)
- Stack details: nginx/apache, docker, systemd service name, custom app log path
- (Connection IP/user/password/port come from `~/.ssh/server/heyun.json`.)

## Workflow decision tree

1. Connect: try the helper script (direct password SSH) first. If the public
   port is firewalled (banner dropped pre-auth), fall back to the Cloudflare
   Tunnel path (`ssh heyun-cf`).
2. If logs are enormous, avoid copying full logs; extract a sample (`tail`) or
   aggregate counts (`awk`/`grep`) on the server.
3. For nginx access logs, generate a sample on the server and analyze locally.

## Workflow: Collect → Analyze → Report

All commands below are meant to be run through `./scripts/heyun_ssh.sh '<cmd>'`.

### 1) Establish context (always)

```bash
date
timedatectl 2>/dev/null || true
uname -a
cat /etc/os-release 2>/dev/null || true
ps -p 1 -o comm=
```

Capture current health:

```bash
uptime
df -h
free -h 2>/dev/null || true
```

If you see OOM / reboots, check swap (enabling swap changes system state; ask before doing it):

```bash
swapon --show
ls -lah /swapfile 2>/dev/null || true
file /swapfile 2>/dev/null || true
```

If systemd is present, list failed units:

```bash
systemctl --failed --no-pager 2>/dev/null || true
```

### 2) System log triage

If systemd is present:

```bash
journalctl -p warning..emerg --since "24 hours ago" --no-pager | tail -n 200
```

Otherwise check syslog files (paths vary by distro; see `references/log-locations.md`):

```bash
sudo tail -n 200 /var/log/syslog 2>/dev/null || true
sudo tail -n 200 /var/log/messages 2>/dev/null || true
```

### 3) SSH / auth / security triage

Check for brute-force attempts and new logins (relevant since this host uses
password auth — worth watching for credential-stuffing):

```bash
sudo tail -n 200 /var/log/auth.log 2>/dev/null || sudo tail -n 200 /var/log/secure 2>/dev/null || true
sudo grep -E "Failed password|Invalid user|Accepted" /var/log/auth.log /var/log/secure 2>/dev/null | tail -n 200 || true
last -a | head -n 20
```

If worried about an attack, also list listening ports:

```bash
ss -tulpen 2>/dev/null || netstat -tulpen 2>/dev/null || true
```

### 4) Web server triage (nginx/apache)

Start with error logs:

```bash
sudo tail -n 200 /var/log/nginx/error.log 2>/dev/null || true
sudo tail -n 200 /var/log/apache2/error.log 2>/dev/null || true
```

For access logs, avoid pasting the full file. Create a small sample on the
server, then analyze locally:

```bash
./scripts/heyun_ssh.sh 'sudo tail -n 200000 /var/log/nginx/access.log' > /tmp/nginx-access.tail.log
python3 scripts/nginx_access_summary.py /tmp/nginx-access.tail.log
```

Or analyze via the ssh pipe directly:

```bash
./scripts/heyun_ssh.sh 'sudo tail -n 200000 /var/log/nginx/access.log' | python3 scripts/nginx_access_summary.py -
```

### 5) App/service logs (systemd or docker)

For a systemd service:

```bash
journalctl -u <service-name> --since "24 hours ago" --no-pager | tail -n 400
```

For a docker container:

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker logs --since 24h <container-name> 2>&1 | tail -n 400
```

## Output format (produce a report)

Write a Markdown report with:

- Time window + timezone
- Symptom summary (what broke, impact)
- Key findings (top errors, top endpoints, top suspicious IPs)
- Likely root causes (ranked)
- Next actions (commands to run, configs to check, mitigations)

## Safety rules

- Prefer read-only commands and time-bounded queries (`--since`, `tail`).
- Ask before running any command that changes state (restart services, rotate/truncate logs, firewall changes, package installs).
- **Never reveal the password** from `heyun.json` in output, logs, or the report.
- Redact secrets in shared logs (tokens, cookies, passwords, private URLs, internal IPs if needed).

## Resources

- `scripts/heyun_ssh.sh`: SSH wrapper that loads credentials from `~/.ssh/server/heyun.json` and connects via password auth (`sshpass`).
- `scripts/nginx_access_summary.py`: Summarize nginx access logs (status codes, IPs, endpoints, request rate).
- `references/log-locations.md`: Common log locations on Linux (systemd/nginx/docker/auth).
- `references/triage-commands.md`: Safe read-only commands for incident triage.
- Cloudflare Tunnel fallback: `ssh heyun-cf` (or `ssh heyun-ssh.razet.me`); tunnel managed via the `cloudflare-tunnel-api` skill, creds in `~/.ssh/cloudfare/cf.env`.
