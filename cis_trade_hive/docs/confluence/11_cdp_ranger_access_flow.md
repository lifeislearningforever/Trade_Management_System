# CDP Cluster Access Flow — CIS Application to Apache Ranger

> **Audience:** GIPS Team, Infrastructure, Security, SA, Developer
> **Read time:** ~12 minutes
> **Purpose:** Explains exactly how a CIS user's access flows from the CIS application all the way through the Cloudera CDP cluster, which Linux service accounts are used, and how Apache Ranger enforces data security at every layer.

---

## 1. Plain English Summary

When a business user logs into CIS and does something — reads a portfolio, runs a trade, exports a report — the system executes queries against the Cloudera CDP cluster on that user's behalf. This page explains:

1. How CIS knows what the user is allowed to do (CIS UAM/RBAC layer)
2. How the CIS application authenticates to CDP (two Linux service accounts)
3. How Ranger enforces the right access level on each CDP service

The key principle: **no end user ever gets direct access to CDP**. All cluster access goes through two shared Linux service IDs, and Ranger policies control exactly what each of those IDs can read or write.

---

## 2. The Two Linux Service Accounts

| Account | Pattern | Authentication | Access Level |
|---------|---------|---------------|-------------|
| **Write account** | `own*` (e.g. `own_cis_svc`) | Kerberos `kinit` with keytab | READ + WRITE on all CIS datasets |
| **Read account** | `un*` (e.g. `un_cis_svc`) | Kerberos `kinit` with keytab | READ ONLY on all CIS datasets |

- The **`own*` account** is used by CIS for all write operations: creating/updating trades, portfolios, positions, uploading market data.
- The **`un*` account** is used by CIS for all read-only query operations: report exports, query builder, dashboard data fetch.
- Both accounts use **Kerberos keytab** files — they never store plaintext passwords.
- Keytab files are stored securely on the CML application server, readable only by the CIS process user.

---

## 3. Access Flow — Step by Step

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          END-TO-END ACCESS FLOW                              │
│                                                                              │
│  Business User (Browser)                                                     │
│         │                                                                    │
│         │  1. Login with LDAP credentials                                    │
│         ▼                                                                    │
│  ┌─────────────────────────────────────┐                                     │
│  │          CIS APPLICATION            │                                     │
│  │  (Django on Cloudera CML)           │                                     │
│  │                                     │                                     │
│  │  ┌────────────────┐                 │                                     │
│  │  │  UAM / RBAC    │  2. Check LDAP  │                                     │
│  │  │  (CIS-side)    │◄───────────────►│◄── LDAP / Active Directory          │
│  │  │                │     group       │                                     │
│  │  │  Groups:       │  membership     │                                     │
│  │  │  CIS-TRADER    │                 │                                     │
│  │  │  CIS-CHECKER   │                 │                                     │
│  │  │  CIS-RISK      │                 │                                     │
│  │  │  CIS-SYSOPS    │                 │                                     │
│  │  └────────────────┘                 │                                     │
│  │         │                           │                                     │
│  │  3. Group → Permission mapping      │                                     │
│  │     (cis_group_permission_map)      │                                     │
│  │         │                           │                                     │
│  │  4. Select service account          │                                     │
│  │     READ → un_cis_svc              │                                     │
│  │     WRITE → own_cis_svc            │                                     │
│  └──────────────┬──────────────────────┘                                     │
│                 │                                                            │
│         5. kinit (Kerberos TGT obtained from KDC)                           │
│                 │                                                            │
│                 ▼                                                            │
│  ┌──────────────────────────────────────────────────────────┐               │
│  │                  CLOUDERA CDP CLUSTER                    │               │
│  │                                                          │               │
│  │  ┌──────────────────────────────────────────────────┐   │               │
│  │  │              APACHE RANGER                       │   │               │
│  │  │  6. Evaluate policies for Linux ID               │   │               │
│  │  │     own_cis_svc → READ + WRITE allowed           │   │               │
│  │  │     un_cis_svc  → READ ONLY                      │   │               │
│  │  └────────────────────┬─────────────────────────────┘   │               │
│  │                       │  7. Grant / Deny                 │               │
│  │            ┌──────────┼──────────┐                       │               │
│  │            ▼          ▼          ▼                       │               │
│  │       ┌────────┐ ┌────────┐ ┌────────┐                  │               │
│  │       │ Impala │ │  Kudu  │ │  Hive  │ ...more services │               │
│  │       └────────┘ └────────┘ └────────┘                  │               │
│  └──────────────────────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Step-by-step explanation

| Step | What happens | Where |
|------|-------------|-------|
| 1 | User enters username + password in CIS login screen | Browser → CIS Django app |
| 2 | CIS authenticates the user against **LDAP / Active Directory**, retrieves their LDAP group memberships | CIS `core/services/acl_service.py` |
| 3 | CIS maps LDAP groups to internal **CIS permissions** (`trade-create`, `portfolio-read`, etc.) via `cis_group_permission_map` in Kudu | CIS RBAC layer (v2) |
| 4 | For each cluster operation, CIS picks the correct Linux service account: `own_cis_svc` if writing, `un_cis_svc` if read-only | `core/repositories/impala_connection.py` |
| 5 | The selected service account performs `kinit` using its Kerberos keytab to obtain a TGT (Ticket Granting Ticket) from the KDC | OS-level Kerberos |
| 6 | The Kerberos ticket is passed to the CDP cluster. **Apache Ranger** checks its policies for the Linux ID (`own_cis_svc` or `un_cis_svc`) and the specific resource (database, table, HDFS path) | Apache Ranger on CDP |
| 7 | Ranger grants or denies the operation. If granted, the CDP service (Impala, Kudu, Hive, HDFS, etc.) executes it | CDP services |

---

## 4. LDAP Groups and CIS Roles

Users are members of LDAP groups. CIS reads these groups at login and maps them to internal roles:

| LDAP Group | CIS Role | Typical users |
|-----------|---------|--------------|
| `CIS-TRADER` | TRADER | Front-office traders, portfolio managers |
| `CIS-CHECKER` | CHECKER | Middle office, compliance, approvers |
| `CIS-RISK` | RISK | Risk managers (read-only) |
| `CIS-SYSOPS` | ADMIN / System operator | System operators, IT support |
| `CIS-READONLY` | VIEWER | GIPS, regulators, audit viewers |

Users can belong to multiple LDAP groups. A user in both `CIS-TRADER` and `CIS-CHECKER` gets the union of both permission sets.

---

## 5. Apache Ranger Policies

Ranger is the **single enforcement point** for all cluster data access. It does not matter which CDP tool is used — Impala, Hive, Spark, or HDFS — all requests pass through Ranger.

### 5.1 Policy Structure

Each Ranger policy defines:
- **Resource**: database name, table name, column name (for Impala/Hive), or HDFS path
- **Users/Groups**: which Linux users or Linux groups are allowed
- **Permissions**: SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALL
- **Conditions**: optional row-level or column-level masks

### 5.2 Ranger Policies for CIS Service Accounts

#### Impala / Kudu (database `gmp_cis`)

| Resource | `own_cis_svc` | `un_cis_svc` |
|----------|:---:|:---:|
| `gmp_cis.*` (all tables) | SELECT, INSERT, UPDATE, DELETE | SELECT |
| `gmp_cis.cis_audit_log` | SELECT, INSERT | SELECT |
| `gmp_cis.cis_trade` | SELECT, INSERT, UPDATE | SELECT |
| `gmp_cis.cis_portfolio` | SELECT, INSERT, UPDATE | SELECT |
| `gmp_cis.cis_security_kudu` | SELECT, INSERT, UPDATE | SELECT |
| `gmp_cis.cis_user` | SELECT, INSERT, UPDATE | SELECT |
| `gmp_cis.cis_group_permissions` | SELECT, INSERT, UPDATE | SELECT |

#### Hive (database `mrw_ima` — GMP external tables)

| Resource | `own_cis_svc` | `un_cis_svc` |
|----------|:---:|:---:|
| `mrw_ima.*` (all tables) | SELECT | SELECT |
| `mrw_ima.gmp_*` (GMP tables) | SELECT | SELECT |

> **Note:** CIS only reads from Hive external tables (GMP source data). No writes to Hive from CIS.

#### HDFS

| HDFS Path | `own_cis_svc` | `un_cis_svc` |
|-----------|:---:|:---:|
| `/user/cis/*` | READ, WRITE, EXECUTE | READ, EXECUTE |
| `/user/cis/uploads/*` | READ, WRITE | READ |
| `/user/cis/backups/*` | READ, WRITE | READ |
| `/warehouse/tablespace/managed/hive/mrw_ima.db/*` | READ | READ |

#### YARN

| Queue | `own_cis_svc` | `un_cis_svc` |
|-------|:---:|:---:|
| `root.cis` (CIS Spark queue) | SUBMIT, ADMIN | SUBMIT |

#### Spark (CML sessions)

| Resource | `own_cis_svc` | `un_cis_svc` |
|----------|:---:|:---:|
| Spark applications on YARN | SUBMIT | SUBMIT |
| HWC (Hive Warehouse Connector) reads | YES | YES |

#### CML (Cloudera Machine Learning)

| CML Resource | `own_cis_svc` | `un_cis_svc` |
|-------------|:---:|:---:|
| CIS project workspace | FULL | READ |
| Job scheduling (`process_settlements`, etc.) | YES | NO |
| CML model serving | YES | NO |

---

## 6. CIS UAM vs CDP Ranger — Responsibilities

It is important to understand that CIS and Ranger serve **different layers** of access control. Both are required.

```
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 1 — CIS Application UAM (RBAC)                           │
│                                                                  │
│  Controls: what a BUSINESS USER can do in CIS                   │
│  Examples: "Can this user create a trade?"                       │
│            "Can this user approve portfolios?"                   │
│            "Can this user see the audit log?"                    │
│                                                                  │
│  Enforced by: cis_group_permission_map (Kudu table)             │
│  Identity: CIS username / LDAP group                            │
│  Granularity: CIS action permissions (trade-create, etc.)       │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │  CIS app uses a shared Linux ID
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 2 — Apache Ranger (CDP Cluster)                          │
│                                                                  │
│  Controls: what the LINUX SERVICE ACCOUNT can do on CDP         │
│  Examples: "Can own_cis_svc write to gmp_cis.cis_trade?"        │
│            "Can un_cis_svc read mrw_ima.gmp_security?"          │
│            "Can own_cis_svc write to HDFS /user/cis/uploads?"   │
│                                                                  │
│  Enforced by: Apache Ranger policies on each CDP service        │
│  Identity: Linux ID (own_cis_svc or un_cis_svc)                 │
│  Granularity: Database / table / column / HDFS path             │
└──────────────────────────────────────────────────────────────────┘
```

**Key point:** Ranger does not know about individual CIS users. It only sees the Linux service account. CIS is responsible for ensuring the right account is used for the right operation. Ranger ensures the service accounts can only access what they need — nothing more.

---

## 7. Kerberos Authentication Flow

Both service accounts authenticate to CDP using Kerberos. This is required for all SIT, UAT, and PROD environments.

```
┌──────────────┐     1. kinit --keytab      ┌──────────────────────┐
│  CIS App     │ ─────────────────────────► │  KDC (Key Distrib.   │
│  (CML server)│                            │  Center)             │
│              │ ◄───────────────────────── │                      │
└──────┬───────┘     2. TGT returned        └──────────────────────┘
       │
       │  3. Service ticket included in every
       │     Impala / HDFS / YARN request
       ▼
┌──────────────────┐
│  CDP Cluster     │
│  (each service   │ ── 4. Validates ticket with KDC ──► KDC
│  validates TGT)  │
│                  │ ── 5. Ranger policy check ──────────► Ranger
└──────────────────┘
```

| Item | Value |
|------|-------|
| Keytab location | `/etc/security/cis_svc.keytab` (on CML application server) |
| Write principal | `own_cis_svc@YOURDOMAIN.COM` |
| Read principal | `un_cis_svc@YOURDOMAIN.COM` |
| KRB5CCNAME | `/tmp/krb_ccache_cis_own` / `/tmp/krb_ccache_cis_un` |
| Ticket renewal | Automatic via `kinit -R` or short-lived ticket + periodic refresh |

Kerberos `kinit` is called on application startup (CML job start) and periodically refreshed. The application never prompts users for cluster credentials.

---

## 8. Data Flow: Trade Creation Example

This example traces a TRADER creating a new trade:

```
1. Trader clicks "New Trade" in CIS browser
   │
2. CIS checks: user has 'trade-create' permission?
   ├─ YES → continue
   └─ NO → HTTP 403, access denied, audit logged
   │
3. Trader fills in form, clicks Save
   │
4. CIS prepares UPSERT SQL for gmp_cis.cis_trade
   │
5. CIS uses connection pool entry authenticated as:
   own_cis_svc (Kerberos TGT from keytab)
   │
6. SQL sent to Impala coordinator over JDBC port 21050
   │
7. Impala authenticates the connection:
   Kerberos ticket → verified with KDC
   │
8. Apache Ranger intercepts the statement:
   Policy check: own_cis_svc + gmp_cis.cis_trade + INSERT
   ├─ ALLOW → Impala executes UPSERT in Kudu
   └─ DENY  → Ranger blocks, error returned to CIS
   │
9. Kudu stores the row
   │
10. CIS audit logger records the CREATE action
    (own_cis_svc writes one row to gmp_cis.cis_audit_log)
```

---

## 9. Data Flow: Report / Query Builder Export (Read-Only)

```
1. Risk Manager clicks "Export CSV" in Query Builder
   │
2. CIS checks: user has 'query-builder-run' permission?
   ├─ YES → continue
   └─ NO → HTTP 403
   │
3. CIS builds SELECT SQL
   │
4. CIS uses connection pool entry authenticated as:
   un_cis_svc (read-only Kerberos TGT)
   │
5. SQL sent to Impala over port 21050
   │
6. Ranger policy check: un_cis_svc + gmp_cis.cis_trade + SELECT
   ├─ ALLOW → results returned
   └─ DENY  → error
   │
7. Results streamed as CSV to user's browser
```

---

## 10. Connection Pool and Account Selection Logic

In `core/repositories/impala_connection.py`, the pool maintains two connection groups:

```
ImpalaConnectionManager
├── _pool_write   (10–35 connections as own_cis_svc)
│   Used by: trade create/update, portfolio create, market data upload,
│            position upsert, audit log write
│
└── _pool_read    (10–35 connections as un_cis_svc)
    Used by: list views, dashboard, query builder, export, report
```

The service layer calls `conn_manager.get_connection(write=True)` or `get_connection(write=False)`. The middleware never allows write-pool connections for GET requests.

---

## 11. What Ranger Does NOT Control

Ranger controls **cluster-level** data access only. The following are controlled exclusively by CIS UAM:

| What | Controlled by |
|------|--------------|
| Which CIS screens a user can see | CIS RBAC (sidebar permissions) |
| Whether a user can approve a trade | CIS RBAC (`trade-approve` permission) |
| Four-Eyes: cannot approve own trade | CIS business logic |
| Portfolio isolation (user sees own portfolios) | CIS query filters |
| Data masking in CIS UI | CIS application code |

Ranger does not know about portfolios, individual trades, or CIS business rules. It only enforces at the database/table/path level.

---

## 12. Summary Table — Who Controls What

| Access Decision | Controlled by | Enforcement point |
|-----------------|--------------|------------------|
| User can log in | LDAP / Active Directory | CIS login + LDAP bind |
| User can view Trade module | CIS RBAC (`trade-read`) | CIS middleware |
| User can create a trade | CIS RBAC (`trade-create`) | CIS view layer |
| CIS app can write to `cis_trade` | Apache Ranger (Impala policy) | Ranger on Impala/Kudu |
| CIS app can read `mrw_ima` Hive tables | Apache Ranger (Hive policy) | Ranger on Hive |
| CIS backup job can write to HDFS | Apache Ranger (HDFS policy) | Ranger on HDFS |
| CIS Spark job runs on YARN queue | Apache Ranger (YARN policy) | Ranger on YARN |
| CIS keytab file is readable | OS file permissions | Linux OS (not Ranger) |

---

## 13. Ranger Audit — What Gets Logged

Apache Ranger logs every access decision (allow and deny) to its own audit store. This is separate from the CIS application audit log.

| Log store | What it captures |
|-----------|----------------|
| **Ranger audit** | Every Impala query, HDFS read/write, YARN submission by `own_cis_svc` / `un_cis_svc`. Includes: timestamp, Linux ID, resource, action, allow/deny |
| **CIS audit log** (`cis_audit_log`) | Every CIS business action: who (CIS username), what (trade created, approved, etc.), before/after values, IP address |

Both logs are independent and complement each other:
- Ranger audit answers: "What did the service account do at the cluster level?"
- CIS audit answers: "Which business user triggered the action, and what was changed?"

---

## 14. Checklist for GIPS Approval

The following should be verified and signed off by the infrastructure and security teams:

```
□ Ranger policy created for own_cis_svc on gmp_cis (Impala): SELECT, INSERT, UPDATE, DELETE
□ Ranger policy created for un_cis_svc on gmp_cis (Impala): SELECT only
□ Ranger policy created for own_cis_svc / un_cis_svc on mrw_ima (Hive): SELECT only
□ Ranger policy created for own_cis_svc on HDFS /user/cis/*: READ, WRITE
□ Ranger policy created for un_cis_svc on HDFS /user/cis/*: READ only
□ Ranger policy created for both accounts on YARN queue root.cis: SUBMIT
□ Keytab files for own_cis_svc and un_cis_svc deployed on CML application server
□ Keytab file permissions: -r-------- owned by cis_app OS user
□ KDC principal created for both Linux IDs
□ kinit tested manually: kinit -kt /etc/security/cis_svc.keytab own_cis_svc@DOMAIN
□ impala-shell connection test: impala-shell -i <host>:21050 --kerberos -q "SHOW DATABASES"
□ CIS application test_hive management command passes on SIT
□ LDAP groups (CIS-TRADER, CIS-CHECKER, etc.) created in Active Directory
□ Test user added to CIS-TRADER, login confirmed in CIS
□ Test trade create → Ranger audit shows INSERT allowed for own_cis_svc
□ Test report export → Ranger audit shows SELECT allowed for un_cis_svc
□ Confirm un_cis_svc cannot INSERT: attempt INSERT in impala-shell → Ranger deny logged
```

---

## 15. Related Confluence Pages

| Page | What it covers |
|------|---------------|
| [05i — Users, Roles & Permissions](05i_rbac.md) | CIS RBAC internals: groups, permissions, cis_group_permission_map |
| [08 — Environments & Configuration](08_environments.md) | Kerberos env variables, Impala connection settings per environment |
| [02 — System Architecture](02_architecture.md) | High-level CIS component diagram |
| [07 — Audit Logging](07_audit_logging.md) | CIS audit log structure and query examples |
