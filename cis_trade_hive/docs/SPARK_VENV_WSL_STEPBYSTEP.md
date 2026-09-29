# How to Use WSL to Build Python 3.11 venv on Windows

## What is WSL?

WSL (Windows Subsystem for Linux) lets you run a real Linux terminal inside
Windows. You use it exactly like a Linux server — but files on your Windows
`C:\` drive are accessible at `/mnt/c/` inside WSL.

---

## Step 1 — Open WSL

**Option A — Start Menu**
```
Start → search "Ubuntu" → click to open
```

**Option B — From any terminal**
```powershell
# In PowerShell or CMD:
wsl
```

A Linux terminal opens. You will see a prompt like:
```
venh7u@DESKTOP-XXXXX:~$
```

You are now on Linux inside Windows.

---

## Step 2 — Check Python 3.11 is Available in WSL

```bash
python3.11 --version
```

If you get `Python 3.11.x` → proceed to Step 3.

If you get `command not found`:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
python3.11 --version    # now works
```

---

## Step 3 — Navigate to Your Windows Folder Inside WSL

Your Windows path `C:\Users\venh7u\CIS\cis\` is accessible in WSL at
`/mnt/c/Users/venh7u/CIS/cis/`

```bash
cd /mnt/c/Users/venh7u/CIS/cis/

# Confirm you are in the right place
pwd
# /mnt/c/Users/venh7u/CIS/cis

ls
# you should see your project files here
```

---

## Step 4 — Delete the Old Windows-Built venv

The `gmp_cis` venv you built in Windows CMD will not work. Delete it:

```bash
rm -rf gmp_cis
```

---

## Step 5 — Create a Fresh venv Using WSL Python 3.11

```bash
python3.11 -m venv gmp_cis

# Activate it
source gmp_cis/bin/activate

# Confirm — prompt changes to (gmp_cis)
which python
# /mnt/c/Users/venh7u/CIS/cis/gmp_cis/bin/python

python --version
# Python 3.11.x
```

---

## Step 6 — Install All Required Packages

```bash
pip install --upgrade pip

pip install \
    PyHive==0.7.0 \
    thrift==0.16.0 \
    thrift-sasl==0.4.3 \
    pyarrow>=14.0.0 \
    openpyxl>=3.1.0 \
    chardet>=5.0.0 \
    python-dotenv==1.0.1 \
    impyla

# Check for broken dependencies
pip check

# List what is installed
pip list
```

---

## Step 7 — Install venv-pack and Pack the venv

```bash
# Install venv-pack (must be inside the activated venv)
pip install venv-pack

# Deactivate BEFORE packing
deactivate

# Pack — this runs on Linux so it works correctly
venv-pack -p gmp_cis -o gmp_cis.tar.gz

# Check the output
ls -lh gmp_cis.tar.gz
# -rw-r--r-- 1 venh7u ... 180M gmp_cis.tar.gz   (size varies)
```

The file `gmp_cis.tar.gz` is now at:
- **WSL path:** `/mnt/c/Users/venh7u/CIS/cis/gmp_cis.tar.gz`
- **Windows path:** `C:\Users\venh7u\CIS\cis\gmp_cis.tar.gz`

You can open it in Windows Explorer normally.

---

## Step 8 — Upload to HDFS

Still inside WSL:

```bash
# Check hdfs is available
hdfs version

# Create the staging directory (ignore error if already exists)
hdfs dfs -mkdir -p /mrw/cis/spark/venvs/

# Upload
hdfs dfs -put -f gmp_cis.tar.gz /mrw/cis/spark/venvs/gmp_cis.tar.gz

# Confirm
hdfs dfs -ls /mrw/cis/spark/venvs/
```

If `hdfs` is not available in WSL, copy the file to the Cloudera edge node
via SCP and upload from there:

```bash
# Copy to edge node
scp /mnt/c/Users/venh7u/CIS/cis/gmp_cis.tar.gz \
    venh7u@edge-node.yourcompany.com:~/

# SSH to edge node and upload
ssh venh7u@edge-node.yourcompany.com
hdfs dfs -put -f ~/gmp_cis.tar.gz /mrw/cis/spark/venvs/gmp_cis.tar.gz
```

---

## Step 9 — spark-submit

From the Cloudera edge node (SSH) or CML terminal:

```bash
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --num-executors 4 \
  --executor-cores 2 \
  --executor-memory 4g \
  --driver-memory 2g \
  --archives hdfs:///mrw/cis/spark/venvs/gmp_cis.tar.gz#gmp_cis \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11 \
  your_etl_job.py
```

---

## Full Command Sequence — Copy & Paste

Open WSL (`wsl` in CMD or PowerShell) then paste all at once:

```bash
cd /mnt/c/Users/venh7u/CIS/cis/

# Clean old venv
rm -rf gmp_cis

# Create fresh Linux venv
python3.11 -m venv gmp_cis
source gmp_cis/bin/activate

# Install packages
pip install --upgrade pip
pip install PyHive==0.7.0 thrift==0.16.0 thrift-sasl==0.4.3 \
            pyarrow>=14.0.0 openpyxl>=3.1.0 chardet>=5.0.0 \
            python-dotenv==1.0.1 impyla venv-pack
pip check
deactivate

# Pack
venv-pack -p gmp_cis -o gmp_cis.tar.gz
ls -lh gmp_cis.tar.gz

# Upload to HDFS
hdfs dfs -mkdir -p /mrw/cis/spark/venvs/
hdfs dfs -put -f gmp_cis.tar.gz /mrw/cis/spark/venvs/gmp_cis.tar.gz
hdfs dfs -ls /mrw/cis/spark/venvs/
```

---

## How Windows Path Maps to WSL Path

| Windows | WSL |
|---|---|
| `C:\` | `/mnt/c/` |
| `C:\Users\venh7u\` | `/mnt/c/Users/venh7u/` |
| `C:\Users\venh7u\CIS\cis\` | `/mnt/c/Users/venh7u/CIS/cis/` |
| `C:\Users\venh7u\CIS\cis\gmp_cis.tar.gz` | `/mnt/c/Users/venh7u/CIS/cis/gmp_cis.tar.gz` |

Files created inside WSL at `/mnt/c/...` appear immediately in Windows Explorer.

---

## Troubleshooting

### `python3.11: command not found` in WSL

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

### `venv-pack` still gives WinError 2

You are running it in Windows CMD/PowerShell, not WSL.
Check your prompt — it must show `venh7u@DESKTOP-...:~$` not `C:\>`.

### `permission denied` writing to `/mnt/c/...`

WSL sometimes has permission issues on Windows NTFS paths. Use your WSL home
directory instead:

```bash
# Build in WSL home
cd ~
rm -rf gmp_cis
python3.11 -m venv gmp_cis
source gmp_cis/bin/activate
pip install --upgrade pip
pip install PyHive==0.7.0 thrift==0.16.0 thrift-sasl==0.4.3 \
            pyarrow openpyxl chardet python-dotenv impyla venv-pack
deactivate
venv-pack -p ~/gmp_cis -o ~/gmp_cis.tar.gz

# Copy to Windows folder
cp ~/gmp_cis.tar.gz /mnt/c/Users/venh7u/CIS/cis/gmp_cis.tar.gz
```

### Slow pip install over `/mnt/c/`

NTFS mounts in WSL are slower than native Linux paths. Build in `~` (WSL home)
as shown above, then copy the finished tar.gz to Windows.

### `hdfs: command not found` in WSL

```bash
# Option A: upload via SCP to edge node
scp ~/gmp_cis.tar.gz venh7u@edge-node.yourcompany.com:~/

# Option B: use the Cloudera CLI from Windows CMD with the tar.gz path
# Option C: use CML Files UI to upload gmp_cis.tar.gz to HDFS manually
```
