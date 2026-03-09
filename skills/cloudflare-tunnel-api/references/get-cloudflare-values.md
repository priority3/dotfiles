# Get `CF_API_TOKEN`, `ACCOUNT_ID`, `ZONE_ID`

## 1) Get `CF_API_TOKEN`

### Dashboard path

1. Open Cloudflare dashboard.
2. Go to `My Profile` -> `API Tokens`.
3. Click `Create Token`.
4. Start from template or custom token:
   - `Zone DNS: Edit`
   - `Account Cloudflare Tunnel: Edit` (or equivalent tunnel write permission)
5. Scope:
   - Zone: include your target zone (for example `example.com`)
   - Account: your account
6. Create token and copy once.

Keep token secret; it is shown only once in full.

## 2) Get `ZONE_ID`

### Dashboard path

1. Open target zone (for example `example.com`).
2. On right sidebar (`API` section), copy `Zone ID`.

### API method

```bash
curl -sS "https://api.cloudflare.com/client/v4/zones?name=${DOMAIN}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq
```

Read `result[0].id`.

## 3) Get `ACCOUNT_ID`

### Dashboard path

1. Go to account home page.
2. On right sidebar (`API` section), copy `Account ID`.

### API method (from zone)

```bash
curl -sS "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq
```

Read `result.account.id`.

## 4) Verify quickly

```bash
curl -sS "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq
```

If `success: true`, token is valid.
