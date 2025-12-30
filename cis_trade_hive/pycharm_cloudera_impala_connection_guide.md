# PyCharm Connection Guide for Cloudera Impala with Kerberos

## Overview

This guide explains how to connect PyCharm on Windows to a Kerberos-secured Cloudera Impala cluster running on Linux edge nodes.

**Your Environment:**
- **Impala Host:** lxmrwtsgv0d1.sg.uobnet.com
- **Port:** 21050
- **Authentication:** GSSAPI (Kerberos)
- **Kerberos Service:** impala
- **Database:** gmp_cis
- **SSL:** Enabled

## ⚠️ Important Constraint: No Windows Admin Access

**Windows users do NOT have administrator privileges**, which means:
- ❌ Cannot install MIT Kerberos for Windows (requires admin)
- ❌ Cannot modify system Kerberos configuration files (requires admin)
- ❌ Cannot install certain Python packages that require compilation

**Therefore:**
- ❌ **Option 1 (Windows Kerberos) is NOT viable**
- ✅ **Option 2 (SSH Tunnel) is viable** - no admin needed
- ⭐ **Option 3 (Remote Interpreter) is RECOMMENDED** - no admin needed
- ✅ **Option 4 (Gateway) is viable** - no admin needed

---

## Quick Decision Guide

**"I just want to start coding NOW (testing/prototyping):"**
→ Use **Option 2: SSH Tunnel** (5 minutes setup)

**"I want production-ready development environment:"**
→ Use **Option 3: Remote Interpreter** (30 minutes setup, best long-term)

**"I have PyCharm 2021.3+ and want the easiest setup:"**
→ Use **Option 4: PyCharm Gateway** (10 minutes setup)

**"I need to install Windows Kerberos:"**
→ ❌ **NOT POSSIBLE** - you don't have admin rights

---

## Configuration Reference

```python
IMPALA = {
    "HOST": "lxmrwtsgv0d1.sg.uobnet.com",
    "PORT": 21050,
    "USE_SSL": True,
    "AUTH_MECHANISM": "GSSAPI",
    "KRB_SERVICE_NAME": "impala",
    "DATABASE": "gmp_cis",
}
```

---

## ~~Option 1: Windows Kerberos Client + Direct Connection~~ ❌ NOT AVAILABLE

### ⚠️ **CANNOT BE USED: Requires Windows Administrator Access**

**This option is documented for reference only. It cannot be used in your environment.**

### Prerequisites

#### 1. Install MIT Kerberos for Windows

**Download:**
- Official Site: https://web.mit.edu/kerberos/dist/
- Direct Link: https://web.mit.edu/kerberos/dist/kfw/4.1/kfw-4.1-amd64.msi

**Installation:**
1. Run the installer as Administrator
2. Accept default installation path: `C:\Program Files\MIT\Kerberos`
3. Complete installation wizard

#### 2. Configure Kerberos

**Create/Edit:** `C:\ProgramData\MIT\Kerberos5\krb5.ini`

```ini
[libdefaults]
    default_realm = SG.UOBNET.COM
    dns_lookup_realm = false
    dns_lookup_kdc = false
    ticket_lifetime = 24h
    renew_lifetime = 7d
    forwardable = true
    default_ccache_name = FILE:C:\temp\krb5cc_%{uid}

[realms]
    SG.UOBNET.COM = {
        kdc = <your-kdc-server>.sg.uobnet.com
        admin_server = <your-admin-server>.sg.uobnet.com
    }

[domain_realm]
    .sg.uobnet.com = SG.UOBNET.COM
    sg.uobnet.com = SG.UOBNET.COM
```

**Note:** Replace `<your-kdc-server>` with actual KDC hostname (ask your IT/security team)

#### 3. Create Ticket Cache Directory

```cmd
mkdir C:\temp
```

#### 4. Install Python Packages

```bash
# Install in your virtual environment
pip install impyla
pip install thrift
pip install thrift_sasl
pip install sasl
pip install kerberos-sspi  # Windows-specific Kerberos package
```

**Alternative if kerberos-sspi fails:**
```bash
# Download precompiled wheel from:
# https://www.lfd.uci.edu/~gohlke/pythonlibs/#kerberos-sspi
pip install kerberos_sspi-0.X.X-cpXX-cpXX-win_amd64.whl
```

#### 5. Get Kerberos Ticket

**Using MIT Kerberos kinit:**
```cmd
# Open Command Prompt or PowerShell
kinit your_username@SG.UOBNET.COM

# Enter password when prompted

# Verify ticket
klist
```

**Expected Output:**
```
Ticket cache: FILE:C:\temp\krb5cc_500
Default principal: your_username@SG.UOBNET.COM

Valid starting     Expires            Service principal
12/30/25 10:00:00  12/30/25 20:00:00  krbtgt/SG.UOBNET.COM@SG.UOBNET.COM
```

#### 6. Test Connection

```python
# test_impala_windows.py
from impala.dbapi import connect
import os

try:
    conn = connect(
        host='lxmrwtsgv0d1.sg.uobnet.com',
        port=21050,
        use_ssl=True,
        auth_mechanism='GSSAPI',
        kerberos_service_name='impala'
    )

    cursor = conn.cursor()
    cursor.execute("SHOW DATABASES")
    databases = [row[0] for row in cursor.fetchall()]

    print("✅ Connected successfully!")
    print(f"Databases: {databases}")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Connection failed: {e}")
```

### Advantages
✅ Direct connection from Windows
✅ No SSH tunnel needed
✅ Production-like setup
✅ Can run Django dev server locally

### Why This Won't Work Without Admin Access
❌ MIT Kerberos installation requires administrator rights
❌ Creating/modifying `C:\ProgramData\MIT\Kerberos5\krb5.ini` requires admin
❌ Some Python packages (kerberos-sspi) may require admin for installation
❌ System-level configuration changes not allowed

**🚫 DO NOT ATTEMPT THIS OPTION WITHOUT ADMIN RIGHTS**

---

## Option 2: SSH Tunnel + Port Forwarding

### ✅ Best For: Quick development setup, no Kerberos hassle

### Setup

#### 1. Create SSH Tunnel

**Windows PowerShell:**
```powershell
# Create tunnel to Impala port
ssh -L 21050:lxmrwtsgv0d1.sg.uobnet.com:21050 your_username@edge_node_server

# Keep this terminal window open while developing
```

**Alternative - Background Tunnel (Windows):**
```powershell
# Using PuTTY
putty.exe -ssh -L 21050:lxmrwtsgv0d1.sg.uobnet.com:21050 your_username@edge_node_server

# Or create saved session in PuTTY with tunnel configured
```

#### 2. Update Environment Variables

**Create `.env.local` file:**
```bash
# Override Impala settings for local development
IMPALA_HOST=localhost
IMPALA_PORT=21050
IMPALA_USE_SSL=false
IMPALA_AUTH=NOSASL
IMPALA_DB=gmp_cis
```

#### 3. Load Local Environment

```python
# settings.py
from dotenv import load_dotenv
import os

# Load local overrides if they exist
if os.path.exists('.env.local'):
    load_dotenv('.env.local')
else:
    load_dotenv('.env')
```

#### 4. Test Connection

```python
# test_impala_tunnel.py
from impala.dbapi import connect

try:
    conn = connect(
        host='localhost',  # Tunneled to edge node
        port=21050,
        auth_mechanism='NOSASL'  # No auth needed for localhost
    )

    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    version = cursor.fetchone()

    print(f"✅ Connected successfully!")
    print(f"Impala Version: {version[0]}")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Connection failed: {e}")
```

### Advantages
✅ No Windows Kerberos setup
✅ Simple configuration
✅ Works immediately
✅ Good for development/testing

### Disadvantages
❌ Need to keep SSH tunnel open
❌ SSH session interruption breaks connection
❌ Not production-like

---

## Option 3: PyCharm Remote Interpreter (RECOMMENDED)

### ✅ Best For: Enterprise development, team consistency

### Overview

Your code runs on the Linux edge node where Kerberos is already configured. PyCharm syncs your files and displays results on Windows.

### Step-by-Step Setup

#### 1. Configure SFTP Deployment

**PyCharm → Tools → Deployment → Configuration**

1. Click `+` → Select `SFTP`
2. Configure connection:
   ```
   Name: Impala Edge Node
   Type: SFTP

   Connection Tab:
   ├── Host: lxmrwtsgv0d1.sg.uobnet.com (or your edge node)
   ├── Port: 22
   ├── Root path: /home/your_username/projects
   └── Authentication:
       ├── Type: Key pair
       └── Private key: C:\Users\YourName\.ssh\id_rsa

   Mappings Tab:
   ├── Local path: C:\Dev\cis_trade_hive
   ├── Deployment path: /cis_trade_hive
   └── Web path: /
   ```

3. Click `Test Connection` → Should show success

#### 2. Configure Remote Interpreter

**Settings → Project → Python Interpreter**

1. Click gear icon ⚙️ → `Add...`
2. Select `SSH Interpreter`
3. Configure:
   ```
   New server configuration:
   ├── Host: lxmrwtsgv0d1.sg.uobnet.com
   ├── Port: 22
   ├── Username: your_username
   └── Authentication: Key pair

   Python interpreter path:
   └── /home/your_username/projects/cis_trade_hive/.venv/bin/python

   Sync folders:
   ├── Local: C:\Dev\cis_trade_hive
   └── Remote: /home/your_username/projects/cis_trade_hive
   ```

4. Click `Finish`
5. Wait for PyCharm to sync packages (may take 5-10 minutes first time)

#### 3. Enable Auto-Upload

**Tools → Deployment → Options**

```
Upload changed files automatically:
└── ✅ Always
```

Or for manual control:
```
Upload changed files automatically:
└── ✅ On explicit save action (Ctrl+S)
```

#### 4. Configure Django Run Configuration

**Run → Edit Configurations → Add → Django Server**

```
Configuration:
├── Name: Django Server (Remote)
├── Host: 0.0.0.0
├── Port: 8000
├── Python interpreter: Remote Python (edge_node)
├── Environment variables:
│   └── (Loaded from .env on edge node)
└── Path mappings:
    ├── Local: C:\Dev\cis_trade_hive
    └── Remote: /home/your_username/projects/cis_trade_hive
```

#### 5. Test Remote Execution

Create test file:
```python
# test_remote.py
import socket
import os

print(f"✅ Running on: {socket.gethostname()}")
print(f"✅ Python path: {os.__file__}")
print(f"✅ Working directory: {os.getcwd()}")

# Test Impala connection
from core.repositories.impala_connection import impala_manager
print(f"✅ Impala connection: {impala_manager.test_connection()}")
```

**Right-click → Run** → Should show edge node hostname

#### 6. SSH to Edge Node and Configure Kerberos

**On edge node (one-time daily):**
```bash
# SSH into edge node
ssh your_username@edge_node_server

# Get Kerberos ticket
kinit your_username@SG.UOBNET.COM

# Verify ticket
klist

# Keep this ticket alive (optional cron job)
echo "*/30 * * * * kinit -R" | crontab -
```

### Workflow

```
┌─────────────────┐
│  Windows PC     │
│  PyCharm Editor │
│                 │
│  1. Edit code   │
│  2. Press Run   │
└────────┬────────┘
         │ SFTP Sync
         ▼
┌─────────────────┐
│  Linux Edge Node│
│                 │
│  3. Code runs   │
│  4. Kerberos ✓  │
│  5. Impala ✓    │
└────────┬────────┘
         │ Results
         ▼
┌─────────────────┐
│  Windows PC     │
│  PyCharm Output │
│                 │
│  6. View results│
└─────────────────┘
```

### Advantages
✅ No Windows Kerberos setup
✅ Code runs in production environment
✅ Full PyCharm debugging support
✅ Team consistency
✅ Edge node Kerberos already configured
✅ Can access edge node files directly

### Disadvantages
❌ Requires PyCharm Professional (SSH interpreter)
❌ First-time sync can be slow
❌ Requires stable SSH connection

---

## Option 4: PyCharm Gateway (Remote Development)

### ✅ Best For: PyCharm 2021.3+, cleanest remote development

### Setup

#### 1. Install PyCharm Gateway

**Download:**
- JetBrains Toolbox → Install `PyCharm Gateway`
- Or: https://www.jetbrains.com/remote-development/gateway/

#### 2. Connect to Edge Node

**PyCharm Gateway:**
1. Click `New Connection`
2. Select `SSH`
3. Configure:
   ```
   Host: lxmrwtsgv0d1.sg.uobnet.com
   Port: 22
   Username: your_username
   Authentication: SSH key
   ```
4. Select project directory: `/home/your_username/projects/cis_trade_hive`
5. Click `Connect`

#### 3. Backend IDE Starts

- Full PyCharm IDE runs on edge node
- Thin client UI on Windows
- All code execution on Linux

### Advantages
✅ Zero configuration needed
✅ Uses edge node's Kerberos
✅ Best performance for large projects
✅ No file sync issues
✅ Native Linux development experience

### Disadvantages
❌ Requires PyCharm 2021.3+
❌ Backend IDE consumes edge node resources
❌ Requires stable network connection

---

## Comparison Matrix

| Feature | ~~Option 1: Windows Kerberos~~ | Option 2: SSH Tunnel | Option 3: Remote Interpreter | Option 4: Gateway |
|---------|---------------------------|---------------------|------------------------------|-------------------|
| **Admin Rights Required** | ❌ **YES - NOT VIABLE** | ✅ No | ✅ No | ✅ No |
| **Kerberos Setup** | ❌ Not possible | None | None (uses edge node) | None (uses edge node) |
| **PyCharm Version** | ❌ N/A | Any | Professional only | 2021.3+ |
| **Code Execution** | ❌ N/A | Windows | Linux (edge node) | Linux (edge node) |
| **Debugging** | ❌ N/A | Full | Full | Full |
| **Network Stability** | ❌ N/A | Requires tunnel | Requires SSH | Requires SSH |
| **Setup Difficulty** | ❌ N/A | ⭐⭐ | ⭐⭐⭐ | ⭐ |
| **Production-like** | ❌ N/A | No | Yes | Yes |
| **Team Consistency** | ❌ N/A | Easy | Easy | Easy |

---

## Recommended Solution

### **For Your UOB Enterprise Setup (No Admin Access): Option 3 (Remote Interpreter)**

**This is the ONLY production-ready option without Windows admin rights.**

**Reasons:**
1. ✅ **No Windows admin rights required**
2. ✅ Edge node already has Kerberos configured
3. ✅ No complex Windows setup needed
4. ✅ Code runs in production-like Linux environment
5. ✅ Easy debugging with PyCharm Professional
6. ✅ Team can use same approach
7. ✅ Works with corporate firewalls/security

**Alternative for Quick Testing: Option 2 (SSH Tunnel)**
- Good for quick development/testing
- Not production-like environment
- No admin rights needed

### Quick Start Guide

**One-Time Setup (30 minutes):**
```
1. Configure SFTP deployment to edge node
2. Set remote Python interpreter
3. Enable auto-upload
4. Configure Django run configuration
5. SSH to edge node and run kinit
```

**Daily Workflow (5 seconds):**
```
1. Open PyCharm → Your project opens
2. Edit code → Auto-syncs to edge node
3. Press Run → Executes on edge node
4. View results in PyCharm
```

**Daily Maintenance:**
```
# SSH to edge node once per day
ssh edge_node_server
kinit your_username@SG.UOBNET.COM
# Enter password

# Optional: Keep ticket alive
echo "*/30 * * * * kinit -R" | crontab -
```

---

## Troubleshooting

### Issue: "Cannot connect to edge node"

**Check SSH connectivity:**
```bash
ssh -v your_username@lxmrwtsgv0d1.sg.uobnet.com
```

**Solution:**
- Verify VPN is connected
- Check SSH key is loaded
- Verify edge node is accessible

### Issue: "Kerberos ticket expired"

**Symptoms:**
```
impala.error.HiveServer2Error: TTransportException('TSocket read 0 bytes')
```

**Solution:**
```bash
# SSH to edge node
ssh edge_node_server

# Renew ticket
kinit -R

# Or get new ticket
kinit your_username@SG.UOBNET.COM
```

### Issue: "PyCharm can't find remote Python"

**Solution:**
```bash
# SSH to edge node
cd /home/your_username/projects/cis_trade_hive

# Verify virtual environment exists
ls -la .venv/bin/python

# If missing, create it
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Issue: "Impala connection timeout"

**Check connectivity from edge node:**
```bash
# SSH to edge node
telnet lxmrwtsgv0d1.sg.uobnet.com 21050

# Or
nc -zv lxmrwtsgv0d1.sg.uobnet.com 21050
```

**Verify Kerberos ticket:**
```bash
klist
```

### Issue: "SSL certificate verification failed"

**Solution (for development only):**
```python
# In your connection code
conn = connect(
    host='lxmrwtsgv0d1.sg.uobnet.com',
    port=21050,
    use_ssl=True,
    ca_cert='/path/to/ca-bundle.crt',  # Add CA cert
    # Or for testing only:
    # use_ssl=False
)
```

---

## Security Best Practices

### 1. SSH Key Authentication

**Generate SSH key (if not exists):**
```bash
# On Windows (Git Bash or PowerShell)
ssh-keygen -t rsa -b 4096 -C "your_email@uobgroup.com"

# Copy to edge node
ssh-copy-id your_username@edge_node_server
```

### 2. Kerberos Ticket Lifetime

**Limit ticket lifetime:**
```ini
# krb5.ini
[libdefaults]
    ticket_lifetime = 8h  # 8 hours max
    renew_lifetime = 1d   # 1 day max
```

### 3. Auto-Lock on Disconnect

**PyCharm settings:**
```
Tools → Deployment → Options
└── ✅ Warn when uploading over newer file
```

### 4. .env File Security

**Never commit credentials:**
```bash
# .gitignore
.env
.env.local
.env.production
*.key
*.pem
krb5cc_*
```

---

## Additional Resources

### Documentation
- **Impyla Documentation:** https://github.com/cloudera/impyla
- **PyCharm Remote Development:** https://www.jetbrains.com/help/pycharm/remote-development-overview.html
- **MIT Kerberos:** https://web.mit.edu/kerberos/krb5-latest/doc/

### Support Contacts
- **Cloudera Admin:** [Your IT Team]
- **Kerberos/AD:** [Your Security Team]
- **Edge Node Access:** [Your DevOps Team]

### Useful Commands

**Check Impala status:**
```bash
# On edge node
impala-shell -i lxmrwtsgv0d1.sg.uobnet.com:21050 -k

# List databases
SHOW DATABASES;
```

**Monitor Kerberos ticket:**
```bash
# Check ticket status
klist -v

# Renew ticket
kinit -R

# Destroy ticket
kdestroy
```

**PyCharm remote debugging:**
```python
# Add breakpoint in code
import pydevd_pycharm
pydevd_pycharm.settrace('localhost', port=12345, stdoutToServer=True, stderrToServer=True)
```

---

## Summary

**Recommended Setup: Option 3 (PyCharm Remote Interpreter)**

**Setup Time:** 30 minutes (one-time)
**Daily Maintenance:** 1 minute (kinit renewal)
**Team Scalability:** Excellent

**Next Steps:**
1. ✅ Configure PyCharm SFTP deployment
2. ✅ Set remote Python interpreter
3. ✅ Enable auto-upload
4. ✅ SSH to edge node and run kinit
5. ✅ Test connection with test script
6. ✅ Start developing!

---

**Need Help?**

Contact your team lead or DevOps for:
- Edge node access credentials
- Kerberos KDC server details
- SSL certificate files
- VPN configuration

Happy coding! 🚀
