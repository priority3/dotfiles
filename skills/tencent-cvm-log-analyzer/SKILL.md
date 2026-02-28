---
name: tencent-cvm-log-analyzer
description: "Analyze Tencent Cloud (腾讯云) CVM Linux server logs via SSH (key-pair) or Tencent Cloud Automation Tools (TAT/云助手) output. Use for server-log triage and incident investigation: systemd/journalctl/syslog errors, nginx/apache access+error logs (4xx/5xx spikes like 502/504), SSH/auth logs (brute-force, suspicious IPs), Docker/container logs, and produce a concise report with likely causes + next actions. Triggers: 腾讯云/CVM/云服务器/轻量应用服务器/服务器日志/nginx access.log/error.log/journalctl/auth.log/secure/502/504/被攻击/爆量."
---

# Tencent Cloud CVM Log Analyzer

## Overview

Triage and analyze logs from a Tencent Cloud CVM (Linux) instance. Collect a time-bounded, mostly read-only slice of system/web/app/auth logs, summarize anomalies (errors, spikes, suspicious IPs), and produce an actionable incident report.

## Quick start (ask for these)

- CVM public IP / hostname (and SSH port if not 22)
- SSH user (depends on image: `ubuntu` / `root` / `centos`) + private key path (preferred), or TAT output (fallback)
- Time window (e.g. last 2h / last 24h) and server timezone
- Observed symptoms (e.g. 502 spikes, CPU 100%, login brute-force)
- Stack details: nginx/apache, docker, systemd service name, custom app log path

## Authentication (local-only)

Default key path (do not commit/copy the key into this skill):

- Private key: `<PATH_TO_PRIVATE_KEY>`

Ensure key permissions are strict:

```bash
chmod 600 <PATH_TO_PRIVATE_KEY>
```

## Default target (local-only)

This skill assumes your current CVM target is:

- HostName: `<YOUR_CVM_PUBLIC_IP_OR_HOSTNAME>`
- Port: `22` (or your SSH port)
- User: `<YOUR_SSH_USER>` (often `root` / `ubuntu`)

Suggested `~/.ssh/config` entry:

```sshconfig
Host tencent-cvm
  HostName <YOUR_CVM_PUBLIC_IP_OR_HOSTNAME>
  Port 22
  User <YOUR_SSH_USER>
  IdentityFile <PATH_TO_PRIVATE_KEY>
  IdentitiesOnly yes
```

Then test:

```bash
ssh tencent-cvm 'echo ok'
```

One-off SSH example:

```bash
ssh -i <PATH_TO_PRIVATE_KEY> -p 22 <YOUR_SSH_USER>@<YOUR_CVM_PUBLIC_IP_OR_HOSTNAME> 'echo ok'
```

## Workflow decision tree

1. Prefer SSH access if possible.
2. If SSH is blocked, use Tencent Cloud Automation Tools (TAT/云助手) to run the same read-only commands and paste the outputs.
3. If logs are enormous, avoid copying full logs; extract a sample (`tail`) or aggregate counts (`awk`/`grep`).

## Workflow: Collect → Analyze → Report

### 1) Establish context (always)

Run on the server (read-only):

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

Check for brute-force attempts and new logins:

```bash
sudo tail -n 200 /var/log/auth.log 2>/dev/null || sudo tail -n 200 /var/log/secure 2>/dev/null || true
sudo grep -E "Failed password|Invalid user|Accepted" /var/log/auth.log /var/log/secure 2>/dev/null | tail -n 200 || true
last -a | head -n 20
```

If the user is worried about an attack, also list listening ports:

```bash
ss -tulpen 2>/dev/null || netstat -tulpen 2>/dev/null || true
```

### 4) Web server triage (nginx/apache)

Start with error logs:

```bash
sudo tail -n 200 /var/log/nginx/error.log 2>/dev/null || true
sudo tail -n 200 /var/log/apache2/error.log 2>/dev/null || true
```

For access logs, avoid pasting the full file. Create a small sample on the server:

```bash
sudo tail -n 200000 /var/log/nginx/access.log > /tmp/nginx-access.tail.log
```

On your local machine, run the bundled analyzer from this skill folder:

```bash
cd <PATH_TO_SKILL_FOLDER>
```

Then analyze locally (option A: scp):

```bash
## Using ~/.ssh/config alias (recommended)
scp tencent-cvm:/tmp/nginx-access.tail.log /tmp/nginx-access.tail.log
python3 scripts/nginx_access_summary.py /tmp/nginx-access.tail.log

## One-off (no ssh config)
scp -i <PATH_TO_PRIVATE_KEY> <SSH_USER>@<YOUR_CVM_PUBLIC_IP_OR_HOSTNAME>:/tmp/nginx-access.tail.log /tmp/nginx-access.tail.log
python3 scripts/nginx_access_summary.py /tmp/nginx-access.tail.log
```

Or analyze via ssh pipe (option B):

```bash
## Using ~/.ssh/config alias (recommended)
ssh tencent-cvm 'sudo tail -n 200000 /var/log/nginx/access.log' | python3 scripts/nginx_access_summary.py -

## One-off (no ssh config)
ssh -i <PATH_TO_PRIVATE_KEY> <SSH_USER>@<YOUR_CVM_PUBLIC_IP_OR_HOSTNAME> 'sudo tail -n 200000 /var/log/nginx/access.log' | python3 scripts/nginx_access_summary.py -
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
- Redact secrets in shared logs (tokens, cookies, passwords, private URLs, internal IPs if needed).

## Resources

- `scripts/nginx_access_summary.py`: Summarize nginx access logs (status codes, IPs, endpoints, request rate).
- `references/log-locations.md`: Common log locations on Linux (systemd/nginx/docker/auth).
- `references/triage-commands.md`: Safe read-only commands for incident triage.
