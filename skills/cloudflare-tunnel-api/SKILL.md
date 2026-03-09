---
name: cloudflare-tunnel-api
description: "Use this skill for Cloudflare Tunnel and DNS automation via Cloudflare API. Use when users ask to create/manage cloudflared tunnels, bind a subdomain to a tunnel, fetch tunnel tokens, create proxied DNS records, or troubleshoot Cloudflare Tunnel routing/cert issues. Trigger keywords: Cloudflare/CF/cloudflared/Tunnel/Argo Tunnel/CF_API_TOKEN/ACCOUNT_ID/ZONE_ID."
---

# Cloudflare Tunnel API

## Overview

Use this skill to set up Cloudflare Tunnel quickly with API-first commands and reproducible checks.
Default objective: expose an origin service (for example `http://127.0.0.1:8317`) as `https://${HOST}.${DOMAIN}`.

This skill must stay sanitized for sharing:
- Do not hardcode real tokens, account IDs, zone IDs, domains, or tunnel names.
- Use placeholders and environment variables only.

## Required Inputs

- `CF_API_TOKEN`
- `ACCOUNT_ID`
- `ZONE_ID`
- `DOMAIN` (example: `example.com`)
- `HOST` (example: `api`)
- `ORIGIN_URL` (example: `http://127.0.0.1:8317`)
- `TUNNEL_NAME` (example: `demo-tunnel`)

If IDs are missing, read [references/get-cloudflare-values.md](references/get-cloudflare-values.md).

## Quick Verify

Verify token validity first:

```bash
curl -sS "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq
```

## API Workflow (Remote-managed Tunnel)

### 1) Create tunnel

```bash
curl -sS "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/cfd_tunnel" \
  -X POST \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{\"name\":\"${TUNNEL_NAME}\",\"config_src\":\"cloudflare\"}" | jq
```

Capture:
- `TUNNEL_ID` from `result.id`
- `TUNNEL_TOKEN` from `result.token`

### 2) Configure ingress (hostname -> origin)

```bash
curl -sS "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
  -X PUT \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{
    \"config\": {
      \"ingress\": [
        {\"hostname\": \"${HOST}.${DOMAIN}\", \"service\": \"${ORIGIN_URL}\", \"originRequest\": {}},
        {\"service\": \"http_status:404\"}
      ]
    }
  }" | jq
```

### 3) Create DNS record to tunnel

```bash
curl -sS "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" \
  -X POST \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{
    \"type\": \"CNAME\",
    \"name\": \"${HOST}.${DOMAIN}\",
    \"content\": \"${TUNNEL_ID}.cfargotunnel.com\",
    \"proxied\": true
  }" | jq
```

### 4) Run connector on server (Docker)

```bash
docker rm -f cloudflared-${HOST} 2>/dev/null || true
docker run -d \
  --name cloudflared-${HOST} \
  --restart unless-stopped \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run --token "${TUNNEL_TOKEN}"
```

## Validation Checklist

1. DNS check:

```bash
curl -s "https://dns.google/resolve?name=${HOST}.${DOMAIN}&type=CNAME"
```

2. Tunnel logs:

```bash
docker logs --tail 100 cloudflared-${HOST}
```

3. Application check:

```bash
curl -I "https://${HOST}.${DOMAIN}"
```

## Troubleshooting

- `403/blocked page` on custom domain:
  - Confirm hostname resolves to `<TUNNEL_ID>.cfargotunnel.com` (CNAME), not direct origin IP.
  - Confirm CNAME is proxied in Cloudflare (`proxied: true`).
- `token invalid`:
  - Recreate token and verify with `/user/tokens/verify`.
- `connection refused to origin`:
  - Check `ORIGIN_URL` locally on server.
  - Check firewall/security group and local bind address.
- `DNS record already exists`:
  - Use DNS record list endpoint, then PATCH/PUT record instead of POST create.

## Minimum Token Permissions

For this workflow, token should include:
- Account: `Cloudflare Tunnel` (Edit) or equivalent tunnel write permission
- Zone: `DNS` (Edit)

## References

- Setup guide: https://developers.cloudflare.com/tunnel/setup/
- Tunnel tokens: https://developers.cloudflare.com/tunnel/advanced/tunnel-tokens/
- Find IDs: https://developers.cloudflare.com/fundamentals/account/find-account-and-zone-ids/
- Create API token: https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
