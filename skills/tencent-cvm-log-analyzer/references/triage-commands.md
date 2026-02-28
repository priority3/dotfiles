# Read-only incident triage commands (Linux)

Copy/paste these on the CVM instance to collect *small, time-bounded* evidence. Prefer commands that do not change system state.

## Time + OS context

```bash
date
timedatectl 2>/dev/null || true
uname -a
cat /etc/os-release 2>/dev/null || true
ps -p 1 -o comm=
```

## Resource pressure (CPU / memory / disk)

```bash
uptime
df -h
free -h 2>/dev/null || true
top -b -n 1 | head -n 30
ps aux --sort=-%mem | head -n 15
ps aux --sort=-%cpu | head -n 15
```

## Networking

```bash
ip a 2>/dev/null || true
ip r 2>/dev/null || true
ss -tulpen 2>/dev/null || netstat -tulpen 2>/dev/null || true
```

## systemd / service status

```bash
systemctl --failed --no-pager 2>/dev/null || true
systemctl status <unit-name> --no-pager 2>/dev/null || true
journalctl -u <unit-name> --since "24 hours ago" --no-pager | tail -n 400
```

## System log sampling (avoid huge dumps)

```bash
journalctl -p warning..emerg --since "24 hours ago" --no-pager | tail -n 200
sudo tail -n 200 /var/log/syslog 2>/dev/null || true
sudo tail -n 200 /var/log/messages 2>/dev/null || true
```

## SSH/auth brute-force quick check

```bash
sudo grep -E "Failed password|Invalid user" /var/log/auth.log /var/log/secure 2>/dev/null | tail -n 200
sudo grep -E "Accepted" /var/log/auth.log /var/log/secure 2>/dev/null | tail -n 50
last -a | head -n 20
```

## nginx access log quick counts (combined/common formats)

Status code distribution:

```bash
sudo awk '{print $9}' /var/log/nginx/access.log | sort | uniq -c | sort -nr | head
```

Top client IPs:

```bash
sudo awk '{print $1}' /var/log/nginx/access.log | sort | uniq -c | sort -nr | head
```

Focus on 5xx:

```bash
sudo grep -E '\" [0-9]{3} ' /var/log/nginx/access.log | grep -E '\" 5[0-9]{2} ' | tail -n 200
```

## Docker logs

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker logs --since 24h <container-name> 2>&1 | tail -n 400
```
