---
name: aliyun-ecs-log-analyzer
description: "Analyze Alibaba Cloud (Aliyun) ECS Linux server logs via SSH or Aliyun Cloud Assistant. Use for server-log triage and incident investigation: systemd/journalctl/syslog errors, nginx/apache access+error logs (4xx/5xx spikes like 502/504), SSH/auth logs (brute-force, suspicious IPs), Docker/container logs, and producing a concise report with likely causes + next actions. Triggers: 阿里云/ECS/云服务器/服务器日志/nginx access.log/error.log/journalctl/auth.log/secure/502/504/被攻击/爆量."
---

# Aliyun ECS Log Analyzer

## Overview

Triage and analyze logs from an Aliyun ECS Linux instance. Collect a time-bounded, read-only slice of system/web/app/auth logs, summarize anomalies (errors, spikes, suspicious IPs), and produce an actionable incident report.

## Quick start (ask for these)

- ECS public IP / hostname (and SSH port if not 22)
- SSH user + private key path (preferred), or Cloud Assistant output (fallback)
- Time window (e.g. last 2h / last 24h) and server timezone
- Observed symptoms (e.g. 502 spikes, CPU 100%, login brute-force)
- Stack details: nginx/apache, docker, systemd service name, custom app log path

## Default target (local-only)

This skill intentionally does not hardcode a real server. Provide your current ECS target as:

- HostName: `<YOUR_ECS_PUBLIC_IP_OR_HOSTNAME>`
- Port: `22` (or your SSH port)
- User: `<YOUR_SSH_USER>` (often `root` / `ubuntu`)

Authentication:

- Prefer **SSH key-pair login** (recommended).
- Do **not** store passwords, private keys, or any secret tokens inside this skill.

Suggested `~/.ssh/config` entry:

```sshconfig
Host aliyun-ecs
  HostName <YOUR_ECS_PUBLIC_IP_OR_HOSTNAME>
  Port 22
  User <YOUR_SSH_USER>
  IdentityFile <PATH_TO_PRIVATE_KEY>
  IdentitiesOnly yes
```

Then test:

```bash
chmod 600 <PATH_TO_PRIVATE_KEY>
ssh aliyun-ecs 'echo ok'
```

## Workflow decision tree

1. Prefer SSH access if possible.
2. If SSH is blocked, use Aliyun ECS Cloud Assistant to run the same read-only commands and paste the outputs.
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

If you see OOM / reboots, ensure swap is enabled (read the output carefully; this changes system state):

```bash
swapon --show
ls -lah /swapfile 2>/dev/null || true
file /swapfile 2>/dev/null || true
```

If `/swapfile` exists and `file /swapfile` shows it is a swapfile, enable it:

```bash
swapon /swapfile
```

Persist across reboot:

```bash
grep -qE "^/swapfile\\s" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
```

If `/swapfile` does not exist, create one (example: 4G):

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -qE "^/swapfile\\s" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
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

For access logs, avoid pasting the full file. Create a small sample on the server, then analyze locally:

```bash
sudo tail -n 200000 /var/log/nginx/access.log > /tmp/nginx-access.tail.log
```

Copy the file (or paste a smaller excerpt) and run:

```bash
python3 scripts/nginx_access_summary.py /tmp/nginx-access.tail.log
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
- Symptom summary (what broke, how users are affected)
- Key findings (top errors, top endpoints, top suspicious IPs)
- Likely root causes (ranked)
- Next actions (commands to run, config to check, mitigations)

## Safety rules

- Prefer read-only commands and time-bounded queries (`--since`, `tail`).
- Ask before running any command that changes state (restart services, rotate/truncate logs, iptables changes, package installs).
- Redact secrets in shared logs (tokens, cookies, passwords, private URLs, internal IPs if needed).

## Resources

- `scripts/nginx_access_summary.py`: Summarize nginx access logs (status codes, IPs, endpoints, request rate).
- `references/log-locations.md`: Common log locations on Ubuntu/Debian/CentOS and for nginx/docker/systemd.
- `references/triage-commands.md`: Safe read-only commands for incident triage.

---

## Project ops: Update a systemd service on ECS (sanitized template)

Use this section as a template runbook. Keep it free of real IPs, usernames, repo paths, and key filenames.

On the server:

```bash
systemctl status <service-name> --no-pager
systemctl cat <service-name>.service
```

Common layout (verify on server):

- Working dir: `/opt/<service-name>/`
- Service: `/etc/systemd/system/<service-name>.service`
- Env file: `/etc/<service-name>.env` (**contains secrets; do not paste**)
- Port bind: `127.0.0.1:<port>` (typically behind nginx)

### Recommended update method (copy files + restart)

From local machine:

```bash
cd <PATH_TO_LOCAL_REPO>

scp -i <PATH_TO_PRIVATE_KEY> -P <SSH_PORT> \
  <FILES_TO_COPY> \
  <SSH_USER>@<YOUR_ECS_PUBLIC_IP_OR_HOSTNAME>:/opt/<service-name>/
```

Then restart + verify on ECS:

```bash
ssh -i <PATH_TO_PRIVATE_KEY> -p <SSH_PORT> <SSH_USER>@<YOUR_ECS_PUBLIC_IP_OR_HOSTNAME> \
  'systemctl restart <service-name> && systemctl status <service-name> --no-pager'

# Recent logs:
ssh -i <PATH_TO_PRIVATE_KEY> -p <SSH_PORT> <SSH_USER>@<YOUR_ECS_PUBLIC_IP_OR_HOSTNAME> \
  'journalctl -u <service-name> -n 80 --no-pager'
```

### Notes / gotchas

- Remote working dir may **not** be a git repo (files copied via scp).
- Any action that restarts services is state-changing; do it intentionally and verify logs.
