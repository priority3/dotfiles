---
name: west-cn-api
description: "Use this skill for any task involving 西部数码 (West.cn) API operations: domain management, DNS resolution, server management, virtual hosting, SSL certificates, enterprise email, finance/billing, and other West.cn platform services. Trigger keywords: 西部数码/west.cn/域名/domain/解析/DNS/服务器/server/虚拟主机/hosting/SSL/证书/邮箱/email/备案/ICP/余额/balance/续费/renew."
---

# West.cn (西部数码) API Skill

## Overview

Interact with the West.cn (西部数码) business API v2 to manage domains, DNS records, cloud servers, virtual hosting, SSL certificates, enterprise email, and billing.

## Authentication

All API calls require a `token` parameter for identity verification.

### Token generation

```
token = md5(username + api_password + timestamp)
```

- `username`: West.cn registered username
- `api_password`: API password (configurable in the West.cn management console)
- `timestamp`: Current millisecond timestamp
- MD5 output: 32-char lowercase hex string
- Token validity: 10 minutes

### Shell helper to generate token

```bash
USERNAME="<your_username>"
API_PASSWORD="<your_api_password>"
TIMESTAMP=$(python3 -c "import time; print(int(time.time()*1000))")
TOKEN=$(echo -n "${USERNAME}${API_PASSWORD}${TIMESTAMP}" | md5)
echo "token=$TOKEN&username=$USERNAME&timestamp=$TIMESTAMP"
```

## Base URL

```
https://api.west.cn/api/
```

## Common request pattern

- **POST requests**: `Content-Type: application/x-www-form-urlencoded`
  - Body params: `act=<action>&token=<token>&username=<username>&timestamp=<timestamp>&...`
- **GET requests**: Query params: `?act=<action>&token=<token>&username=<username>&timestamp=<timestamp>&...`

## Common response format

```json
{
  "result": 200,
  "clientid": "<request_tracking_id>",
  "data": { ... }
}
```

- `result`: 200 = success, other values = error (see error codes)
- `clientid`: Request tracking ID
- `data`: Business-specific response data

---

## API Endpoint Reference

### 1. Domain Business (域名业务)

**Base path**: `v2/domain/`

#### 1.1 Domain Pricing

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get domain price | POST | `v2/domain/` | `getprice` | domain suffix, year |

#### 1.2 Template & Real-name (模板实名)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Create real-name template | POST | `v2/domain/` | `createtemplate` | Name, ID info, contact |
| Create international template | POST | `v2/domain/` | `createintltemplate` | Name, contact (no real-name) |
| Get template details | POST | `v2/domain/` | `gettemplateinfo` | templateid |
| Get real-name upload token | POST | `v2/domain/` | `getrealnametoken` | - |
| Upload real-name materials | POST | `v2/domain/` | `uploadrealname` | Files, token |
| Modify template | POST | `v2/domain/` | `modifytemplate` | templateid, fields |
| Domain template transfer | POST | `v2/domain/` | `domaintransfer` | domain, templateid |
| Query transfer details | POST | `v2/domain/` | `gettransferlist` | domain |
| Modify domain info | POST | `v2/domain/` | `modifydomain` | domain, fields |
| Get domain real-name info | POST | `v2/domain/` | `getdomainrealname` | domain |
| Batch get template list | POST | `v2/domain/` | `gettemplatelist` | pageno, limit |
| Delete template | POST | `v2/domain/` | `deletetemplate` | templateid |

#### 1.3 Domain Query & Registration (域名查询及注册)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Sensitive word check | POST | `v2/domain/` | `checkword` | word |
| Check domain availability | POST | `v2/domain/` | `checkdomain` | domain |
| Register domain | POST | `v2/domain/` | `regdomain` | domain, year, templateid |

#### 1.4 Domain Management (域名管理)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get domain list | GET | `v2/domain/` | `getdomains` | domain(optional), limit, page |
| Get WHOIS info | POST | `v2/domain/` | `getwhois` | domain |
| Get registry status | GET | `v2/domain/` | `getregistrystatus` | domain |
| Get registration info | POST | `v2/domain/` | `getdomaininfo` | domain |
| Get recent 7d failed domains | POST | `v2/domain/` | `getfaileddomains` | - |

#### 1.5 Domain Renewal (域名续费)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get renewal price | POST | `v2/domain/` | `getrenewprice` | domain, year |
| Renew domain | POST | `v2/domain/` | `renewdomain` | domain, year |

#### 1.6 Domain DNS Operations (域名DNS操作)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Modify domain DNS | POST | `v2/domain/` | `modifydns` | domain, dns1, dns2 |
| Register DNS | POST | `v2/domain/` | `regdns` | domain, dns, ip |
| Modify registered DNS | POST | `v2/domain/` | `modifyregdns` | domain, dns, ip |
| Sync registered DNS | POST | `v2/domain/` | `syncregdns` | domain |
| Get registered DNS | POST | `v2/domain/` | `getregdns` | domain |
| Delete registered DNS | POST | `v2/domain/` | `deleteregdns` | domain, dns |

#### 1.7 DNSSEC

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get DNSSEC details | POST | `v2/domain/` | `getdnssec` | domain |
| Sync DNSSEC | POST | `v2/domain/` | `syncdnssec` | domain |
| Delete DNSSEC | POST | `v2/domain/` | `deletednssec` | domain, keyTag |
| Add DNSSEC | POST | `v2/domain/` | `adddnssec` | domain, keyTag, algorithm, digestType, digest |

#### 1.8 Domain Resolution (域名解析)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Add DNS record | POST | `v2/domain/` | `adddnsrecord` | domain, host, type, value, ttl, level, line |
| Modify DNS record | POST | `v2/domain/` | `moddnsrecord` | domain, id, host, type, value, ttl, level, line |
| Delete DNS record | POST | `v2/domain/` | `deldnsrecord` | domain, id |
| Pause DNS record | POST | `v2/domain/` | `pausednsrecord` | domain, id, pause |
| Get specific DNS records | POST | `v2/domain/` | `getdnsrecord` | domain, host, type |
| Get all DNS records | POST | `v2/domain/` | `getdnsrecords` | domain |

**DNS Record Types**: A, CNAME, MX, TXT, AAAA, SRV

**DNS Line Values**:
- Default: `""` (empty)
- China Telecom: `LTEL`
- China Unicom: `LCNC`
- China Mobile: `LMOB`
- Education Network: `LEDU`
- Search Engine: `LSEO`

**TTL**: 60-86400 seconds (default 900)
**Level (MX priority)**: 1-100 (default 10)

#### 1.9 Domain Certificate (域名证书)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get domain certificate | POST | `v2/domain/` | `getdomaincert` | domain |
| Batch get certificates | GET | `v2/domain/` | `batchgetcert` | domains |
| Batch download certificates | GET | `v2/domain/` | `batchdownloadcert` | domains |

#### 1.10 Domain Password (域名管理密码)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get domain password | POST | `v2/domain/` | `getdomainpwd` | domain |
| Modify domain password | POST | `v2/domain/` | `modifydomainpwd` | domain, password |

#### 1.11 Smart DNS (智能DNS)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Enable smart DNS | POST | `v2/domain/` | `opensmartdns` | domain, year |
| Get smart DNS price | POST | `v2/domain/` | `getsmartdnsprice` | domain |

#### 1.12 CNNIC Privacy Protection

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get service price | POST | `v2/domain/` | `getprivacyprice` | domain |
| Enable privacy | POST | `v2/domain/` | `openprivacy` | domain |
| Modify display email | POST | `v2/domain/` | `modifyprivacyemail` | domain, email |
| Renew privacy | POST | `v2/domain/` | `renewprivacy` | domain, year |
| Get details/list | POST | `v2/domain/` | `getprivacyinfo` | domain |

---

### 2. Server Business (服务器业务)

**Base path**: `v2/server/`

#### 2.1 Configuration

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get basic config | GET | `v2/server/` | `getconfig` | - |
| Get available OS | GET | `v2/server/` | `getos` | serverroom |
| Get config prices | GET | `v2/server/` | `getconfigprice` | - |

#### 2.2 Provisioning & List

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get price | POST | `v2/server/` | `getprice` | Config params |
| Provision server | POST | `v2/server/` | `buy` | OS, CPU, memory, disk, bandwidth... |
| Get server list | POST | `v2/server/` | `list` | pageno, limit, serverroom(optional) |
| Get server details | POST | `v2/server/` | `detail` | id |
| Get IP by ID | POST | `v2/server/` | `getip` | id |
| Modify password | POST | `v2/server/` | `modifypwd` | id, password |
| Disable panel login | POST | `v2/server/` | `denylogin` | id, deny |
| Check extra IP | POST | `v2/server/` | `checkextraip` | id |
| Add extra IP | POST | `v2/server/` | `addextraip` | id |
| Get IPv6 info | POST | `v2/server/` | `getipv6` | id |
| Get extra IP price | POST | `v2/server/` | `extraipprice` | id |
| Get initial password | POST | `v2/server/` | `getinitpwd` | id |

#### 2.3 Renewal & Conversion

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get conversion price | POST | `v2/server/` | `getconvertprice` | id |
| Convert trial to paid | POST | `v2/server/` | `convert` | id |
| Get renewal price | POST | `v2/server/` | `getrenewprice` | id, year |
| Renew server | POST | `v2/server/` | `renew` | id, year |

#### 2.4 Upgrade & Migration

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get server config | POST | `v2/server/` | `getserverconfig` | id |
| Get upgrade price | POST | `v2/server/` | `getupgradeprice` | id, new config |
| Confirm upgrade | POST | `v2/server/` | `upgrade` | id, new config |
| Get migration status | POST | `v2/server/` | `getmigratestatus` | id |
| Get migration price | POST | `v2/server/` | `getmigrateprice` | id, target |
| Confirm migration | POST | `v2/server/` | `migrate` | id, target |
| Get migration IP info | POST | `v2/server/` | `getmigrateip` | id |
| Get migration progress | POST | `v2/server/` | `getmigrateprogress` | id |
| Get vCPU switch price | POST | `v2/server/` | `getvcpuprice` | id |
| Switch vCPU | POST | `v2/server/` | `switchvcpu` | id |

#### 2.5 System & Logs

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Set server status | POST | `v2/server/` | `setstatus` | id, status(start/stop/restart) |
| Get running status | POST | `v2/server/` | `getstatus` | id |
| Get ICP filing code | POST | `v2/server/` | `getfilingcode` | id |
| Get web console URL | POST | `v2/server/` | `getconsole` | id |
| Reinstall OS | POST | `v2/server/` | `reinstall` | id, os |
| Operation log | POST | `v2/server/` | `oplog` | id |
| Performance data | POST | `v2/server/` | `perfdata` | id |

#### 2.6 Security Groups (安全组)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| List security groups | POST | `v2/server/` | `secgrouplist` | - |
| Add security group | POST | `v2/server/` | `addsecgroup` | name |
| Delete security group | POST | `v2/server/` | `delsecgroup` | groupid |
| Get security group rules | POST | `v2/server/` | `getsecgrouprules` | groupid |
| Add security group rule | POST | `v2/server/` | `addsecgrouprule` | groupid, rule params |
| Delete security group rule | POST | `v2/server/` | `delsecgrouprule` | groupid, ruleid |
| Deploy security group | POST | `v2/server/` | `deploysecgroup` | id, groupid |
| Cloud shield status | POST | `v2/server/` | `cloudshieldstatus` | id |
| Set cloud shield | POST | `v2/server/` | `setcloudshield` | id, status |
| Cloud shield log | POST | `v2/server/` | `cloudshieldlog` | id |

#### 2.7 Virtual Switch (虚拟交换机)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| List virtual switches | POST | `v2/server/` | `lswlist` | - |
| Create virtual switch | POST | `v2/server/` | `createlswitch` | name |
| Get switch info | POST | `v2/server/` | `getlswinfo` | lswid |
| Connect to switch | POST | `v2/server/` | `connectlswitch` | id, lswid |
| Disconnect switch | POST | `v2/server/` | `disconnectlswitch` | id |

#### 2.8 CC Protection (CC防护)

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| Get CC config | POST | `v2/server/` | `getccconfig` | id |
| Get CC status | POST | `v2/server/` | `getccstatus` | id |
| Get CC upgrade config | POST | `v2/server/` | `getccupgrade` | id |
| Upgrade CC | POST | `v2/server/` | `upgradecc` | id |
| Check IP blacklist | POST | `v2/server/` | `checkblacklist` | id, ip |
| Remove IP blacklist | POST | `v2/server/` | `removeblacklist` | id, ip |
| CC protection log | POST | `v2/server/` | `cclog` | id |
| Set CC protection | POST | `v2/server/` | `setcc` | id, settings |

**Server cluster IDs**:

| ID | Name | ID | Name |
|----|------|----|------|
| 2 | WJ-2 | 12 | MY10G-1 |
| 3 | BJ-1 | 13 | SY-1 |
| 4 | HK-1 | 14 | ZZ10G-1 |
| 6 | GD-1 | 15 | HK10G-1 |
| 7 | WJ-3 | 16 | HK10G-2 |
| 8 | ZZ-1 | 17 | HK10G-3 |
| 9 | MY-2 | 18 | APP10G-1 |
| - | - | 19 | MIP10G-1 |

---

### 3. Virtual Hosting (虚拟主机业务)

**Base path**: `v2/host/` (POST unless noted)

#### 3.1 Provisioning

| Action | act param | Key params |
|--------|-----------|------------|
| Sync virtual host | `synchost` | id |
| Get product config | `getconfig` (GET) | - |
| Check FTP availability | `checkftp` | ftp name |
| Provision host | `buy` | model, ftp, password... |
| Get product models | `getmodels` | - |
| Get product price | `getprice` | model, year |
| Get host details | `detail` | id |
| Get traffic info | `gettraffic` | id |

#### 3.2 Domain Binding

| Action | act param | Key params |
|--------|-----------|------------|
| Bind domain | `bindomain` | id, domain |
| Delete bound domain | `unbindomain` | id, domain |
| Get bound domain list | `getbindomains` | id |
| Find host by domain | `findbydomain` | domain |

#### 3.3 Sub-site Management

| Action | act param | Key params |
|--------|-----------|------------|
| Create sub-site | `createsubsite` | id, domain, path |
| Get sub-site list | `getsubsitelist` | id |
| Get sub-site details | `getsubsitedetail` | id, subsiteid |
| Delete sub-site | `deletesubsite` | id, subsiteid |
| Set sub-site | `setsubsite` | id, subsiteid, settings |

#### 3.4 File Management

| Action | act param | Key params |
|--------|-----------|------------|
| Generate sitemap | `gensitemap` | id |
| Set default doc | `setdefaultdoc` | id, doc |
| Get default doc | `getdefaultdoc` | id |
| Get file list | `getfilelist` | id, path |
| Backup/restore | `backup` / `restore` | id |

#### 3.5 Security

| Action | act param | Key params |
|--------|-----------|------------|
| Modify host password | `modifypwd` | id, password |
| Get host password | `getpwd` | id |
| Get CC protection | `getcc` | id |
| Set firewall | `setfirewall` | id, rules |

---

### 4. Enterprise Email (企业邮箱业务)

**Base path**: `v2/mail/` (POST)

| Action | act param | Key params |
|--------|-----------|------------|
| Check domain for email | `checkdomain` | domain |
| Validate password | `checkpwd` | password |
| Get pricing | `getprice` | type, year |
| Provision email | `buy` | domain, type, password, year |
| Get email details | `detail` | id |
| Get renewal price | `getrenewprice` | id, year |
| Renew email | `renew` | id, year |
| Get upgrade price | `getupgradeprice` | id, new type |
| Upgrade email | `upgrade` | id, new type |
| Sync data | `sync` | id |
| Pause/resume | `setstatus` | id, status |
| Modify password | `modifypwd` | id, password |
| Get filing code | `getfilingcode` | id |
| Clear postmaster protection | `clearpostmaster` | id |

---

### 5. SSL Certificate (SSL证书业务)

**Base path**: `v2/ssl/` (POST)

Provisioning and management of SSL certificates (specific actions available in full API docs).

---

### 6. Mini Program (小程序业务)

**Base path**: `v2/miniapp/`

| Action | Method | act param | Key params |
|--------|--------|-----------|------------|
| Get product price | POST | `getprice` | type |
| Provision mini app | POST | `buy` | type, domain |
| Get management URL | GET | `getmanageurl` | id |
| Convert trial | GET | `convert` | id |
| Renew | GET | `renew` | id, year |
| Upgrade/downgrade | GET | `upgrade` | id, new type |
| Sync all | GET | `syncall` | - |
| Sync single | GET | `sync` | id |

---

### 7. MSSQL Database (mssql数据库)

**Base path**: `v2/mssql/` (POST)

| Action | act param | Key params |
|--------|-----------|------------|
| Get DB config | `getconfig` | - |
| Check DB name | `checkname` | name |
| Get pricing | `getprice` | version, size |
| Provision/trial | `buy` | name, version, size, password |
| Get details | `detail` | id |
| Renew | `renew` | id, year |
| Convert trial | `convert` | id |
| Change password | `modifypwd` | id, password |
| Get upgrade price | `getupgradeprice` | id |
| Confirm upgrade | `upgrade` | id |

---

### 8. Domain Auction & Buy-Now (域名抢注及一口价)

**Base path**: `v2/domain/` or `v2/auction/`

| Action | Method | act param | Key params |
|--------|--------|-----------|------------|
| Yesterday delisted | GET | `yesterdaydelisted` | - |
| Bargain domain list | GET | `bargainlist` | - |
| Full listing download | GET | `fulllist` | - |
| West.cn listing download | GET | `westlist` | - |
| Get single domain detail | POST | `getbuydetail` | domain |
| Buy fixed-price domain | POST | `buydomain` | domain |
| Today new listings | POST | `todaynew` | - |
| Today price drops | POST | `todaydrop` | - |
| Yesterday new additions | GET | `yesterdaynew` | - |

---

### 9. Finance & Invoicing (财务及发票功能)

**Base path**: `v2/info/` (POST)

| Action | act param | Key params |
|--------|-----------|------------|
| Query financial details | `getfinance` | start_date, end_date, pageno, limit |
| Get spending by period | `getspending` | start_date, end_date |
| Get account balance | `checkbalance` | - |

**Invoice** (base path: `v2/invoice/`, GET):

| Action | act param | Key params |
|--------|-----------|------------|
| Get invoice config | `getconfig` | - |
| Get invoice cost | `getcost` | amount |

---

### 10. Other (其他业务及功能)

**ICP Filing (备案)**:

| Action | Method | Path | act param | Key params |
|--------|--------|------|-----------|------------|
| View filing code | POST | `v2/filing/` | `view` | id |
| Purchase filing code | POST | `v2/filing/` | `buy` | type |

---

## Usage Examples

### Example 1: Get domain list

```bash
BASE="https://api.west.cn/api"
# Generate token first (see Authentication section)

curl -G "${BASE}/v2/domain/" \
  --data-urlencode "act=getdomains" \
  --data-urlencode "token=${TOKEN}" \
  --data-urlencode "username=${USERNAME}" \
  --data-urlencode "timestamp=${TIMESTAMP}" \
  --data-urlencode "limit=20" \
  --data-urlencode "page=1"
```

### Example 2: Add DNS A record

```bash
curl -X POST "${BASE}/v2/domain/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "act=adddnsrecord" \
  -d "token=${TOKEN}" \
  -d "username=${USERNAME}" \
  -d "timestamp=${TIMESTAMP}" \
  -d "domain=example.com" \
  -d "host=www" \
  -d "type=A" \
  -d "value=1.2.3.4" \
  -d "ttl=900" \
  -d "level=10" \
  -d "line="
```

### Example 3: Get server list

```bash
curl -X POST "${BASE}/v2/server/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "act=list" \
  -d "token=${TOKEN}" \
  -d "username=${USERNAME}" \
  -d "timestamp=${TIMESTAMP}" \
  -d "pageno=1" \
  -d "limit=20"
```

### Example 4: Check account balance

```bash
curl -X POST "${BASE}/v2/info/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "act=checkbalance" \
  -d "token=${TOKEN}" \
  -d "username=${USERNAME}" \
  -d "timestamp=${TIMESTAMP}"
```

### Example 5: Get DNS records for a domain

```bash
curl -X POST "${BASE}/v2/domain/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "act=getdnsrecords" \
  -d "token=${TOKEN}" \
  -d "username=${USERNAME}" \
  -d "timestamp=${TIMESTAMP}" \
  -d "domain=example.com"
```

## Important Notes

- Always pass `token`, `username`, and `timestamp` with every request
- Token expires after 10 minutes; regenerate before each call
- For POST requests, use `application/x-www-form-urlencoded` content type
- The `act` parameter determines the specific operation within each endpoint path
- Server IDs (`id`) are critical and should be stored locally
- After IP changes, the only way to get the new IP is via the server ID

## Error Handling

- `result: 200` = success
- Other result codes indicate errors; check the error code documentation
- Common issues: expired token, insufficient balance, invalid parameters
