# Common log locations on CVM (Linux)

Use this as a quick path cheat-sheet when triaging a Tencent Cloud CVM Linux instance. Paths vary by distro and by how services are configured.

## System / kernel

- **systemd journal**: `journalctl ...`
  - Persistent storage (if enabled): `/var/log/journal/`
- **Ubuntu/Debian syslog**: `/var/log/syslog`, `/var/log/kern.log`
- **RHEL/CentOS/Amazon Linux**: `/var/log/messages`
- **Kernel ring buffer**: `dmesg -T | tail`

## Auth / security

- **SSH/auth**:
  - Debian/Ubuntu: `/var/log/auth.log`
  - RHEL/CentOS: `/var/log/secure`
- **auditd**: `/var/log/audit/audit.log`
- **fail2ban**: `/var/log/fail2ban.log`
- **UFW**: `/var/log/ufw.log` (if UFW is enabled)

## Web server

- **nginx**: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`
- **apache (Debian/Ubuntu)**: `/var/log/apache2/access.log`, `/var/log/apache2/error.log`
- **apache (RHEL/CentOS)**: `/var/log/httpd/access_log`, `/var/log/httpd/error_log`

## Containers (docker)

- Prefer: `docker logs <container-name> --since 24h`
- Raw JSON logs: `/var/lib/docker/containers/<id>/<id>-json.log`
- Docker daemon: `journalctl -u docker -S "24 hours ago"` (or `/var/log/docker.log` on some distros)
- containerd: `journalctl -u containerd -S "24 hours ago"`

## Common services

- **MySQL**: `/var/log/mysql/error.log` or `/var/log/mysqld.log`
- **PostgreSQL**: `/var/log/postgresql/postgresql-*.log`
- **Redis**: `/var/log/redis/redis-server.log`
- **PHP-FPM**: `/var/log/php*-fpm.log`
- **PM2**: `~/.pm2/logs/`

## Discovery tips

- List candidates: `sudo ls -lah /var/log`
- Search filenames: `sudo find /var/log -maxdepth 2 -type f | head`
- If rotated: use `zcat` / `zgrep` for `*.gz`
