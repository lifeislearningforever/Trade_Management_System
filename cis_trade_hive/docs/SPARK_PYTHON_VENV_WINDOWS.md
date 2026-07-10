# Python 3.11 Virtual Environment on Windows — Pack for Spark Cluster Mode

## Overview

This guide covers building a Python 3.11 virtual environment on **Windows**,
packing it into a zip/tar.gz, uploading to HDFS, and submitting to a Cloudera
YARN cluster via `spark-submit --archives`.

> **Important:** The packed environment runs on **Linux** YARN worker nodes.
> A venv built on Windows cannot be used directly — you must use **WSL 2**
> (Windows Subsystem for Linux) or a **Docker container** to build the Linux
> binary. Steps for both are covered below.

---

## Prerequisites

| Item | Download / Install |
|---|---|
| Python 3.11.x (Windows) | https://www.python.org/downloads/ — tick "Add to PATH" |
| WSL 2 with Ubuntu 22.04 | `wsl --install` in PowerShell (Admin) |
| Python 3.11 inside WSL | `sudo apt install python3.11 python3.11-venv python3.11-dev` |
| Git Bash or PowerShell | Already on Windows |
| HDFS client (`hdfs` CLI) | Available on Cloudera edge node or via WinUtils |

---

## Option 1 — Build Inside WSL 2 (Recommended)

WSL 2 runs a real Linux kernel — the venv built here works natively on Linux
YARN worker nodes.

### Step 1 — Open WSL Terminal

```
# In PowerShell or Windows Terminal:
wsl
```

You are now inside Ubuntu on Windows.

### Step 2 — Install Python 3.11 in WSL

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip zip
python3.11 --version     # Python 3.11.x
```

### Step 3 — Create Virtual Environment

```bash
# Navigate to your working directory (accessible from both Windows and WSL)
cd /mnt/c/Users/<YourWindowsUsername>/spark_jobs/

# Create venv
python3.11 -m venv cis_etl_env

# Activate
source cis_etl_env/bin/activate

# Confirm
which python        # /mnt/c/Users/.../cis_etl_env/bin/python
python --version    # Python 3.11.x
```

### Step 4 — Install Required Packages

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

# Verify — no broken dependencies
pip check
pip list
```

### Step 5 — Install venv-pack and Pack

```bash
pip install venv-pack

# Deactivate before packing
deactivate

# Pack into tar.gz (includes Python binary + shared libs — fully relocatable)
venv-pack -p cis_etl_env -o cis_etl_env.tar.gz

# Check output
ls -lh cis_etl_env.tar.gz    # typically 80–250 MB
```

> `venv-pack` copies system shared libraries (`.so` files) and rewrites internal
> symlinks so the archive works on any Linux node regardless of what is installed.

### Step 6 — Upload to HDFS

From WSL (if `hdfs` CLI is available):

```bash
hdfs dfs -mkdir -p /mrw/cis/spark/venvs/
hdfs dfs -put -f cis_etl_env.tar.gz /mrw/cis/spark/venvs/cis_etl_env.tar.gz
hdfs dfs -ls /mrw/cis/spark/venvs/
```

Or copy to the Cloudera edge node first, then upload from there:

```bash
# From Windows PowerShell / Git Bash
scp C:\Users\<YourUser>\spark_jobs\cis_etl_env.tar.gz \
    your_user@edge-node.yourcompany.com:~/

# SSH to edge node and upload
ssh your_user@edge-node.yourcompany.com
hdfs dfs -put -f ~/cis_etl_env.tar.gz /mrw/cis/spark/venvs/cis_etl_env.tar.gz
```

---

## Option 2 — Build Inside Docker on Windows (No WSL 2)

Use this if WSL 2 is not available or IT policy blocks it.

### Step 1 — Install Docker Desktop for Windows

Download from https://www.docker.com/products/docker-desktop/
Enable **Linux containers** (default on Windows).

### Step 2 — Run a Python 3.11 Linux Container

Open PowerShell or Git Bash:

```powershell
# Mount your local folder into the container
docker run -it --rm `
  -v C:\Users\<YourUser>\spark_jobs:/workspace `
  python:3.11-slim bash
```

You are now inside a Linux container.

### Step 3 — Create Venv and Install Packages

```bash
cd /workspace

apt-get update && apt-get install -y zip

python3.11 -m venv cis_etl_env
source cis_etl_env/bin/activate

pip install --upgrade pip
pip install \
    PyHive==0.7.0 \
    thrift==0.16.0 \
    thrift-sasl==0.4.3 \
    pyarrow>=14.0.0 \
    openpyxl>=3.1.0 \
    chardet>=5.0.0 \
    python-dotenv==1.0.1 \
    impyla \
    venv-pack

pip check
deactivate

# Pack
venv-pack -p cis_etl_env -o cis_etl_env.tar.gz
ls -lh cis_etl_env.tar.gz
```

The file is written to `C:\Users\<YourUser>\spark_jobs\cis_etl_env.tar.gz`
because the folder is mounted.

### Step 4 — Upload to HDFS

From PowerShell, copy to edge node then upload:

```powershell
scp C:\Users\<YourUser>\spark_jobs\cis_etl_env.tar.gz `
    your_user@edge-node.yourcompany.com:~/
```

```bash
# On edge node
hdfs dfs -put -f ~/cis_etl_env.tar.gz /mrw/cis/spark/venvs/cis_etl_env.tar.gz
hdfs dfs -ls /mrw/cis/spark/venvs/
```

---

## spark-submit Command

Run this from the Cloudera **edge node** (Linux) or from a CML terminal:

```bash
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --num-executors 4 \
  --executor-cores 2 \
  --executor-memory 4g \
  --driver-memory 2g \
  \
  --archives hdfs:///mrw/cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \
  \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.11 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.11 \
  \
  your_etl_job.py \
  --arg1 value1
```

> **Note:** Use `python3.11` not `python` in `PYSPARK_PYTHON` — venv-pack
> creates a versioned symlink (`bin/python3.11`) that is more reliable than the
> generic `bin/python` symlink.

### How `--archives` works

```
--archives <hdfs-path>#<alias>
```

| Part | Value |
|---|---|
| `hdfs-path` | `hdfs:///mrw/cis/spark/venvs/cis_etl_env.tar.gz` — YARN downloads to every node |
| `alias` | `cis_etl_env` — directory name after unpacking on each worker |
| `PYSPARK_PYTHON` | `./cis_etl_env/bin/python3.11` — relative to executor working dir |

---

## Verify the Environment on Executors

Add this to your PySpark script to confirm the correct Python is used:

```python
import sys
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("CIS_ETL").getOrCreate()
sc = spark.sparkContext

print(f"[DRIVER] Python: {sys.executable}")

def _check(_):
    import sys, pyarrow, thrift
    return (
        f"Python: {sys.executable} | "
        f"pyarrow: {pyarrow.__version__} | "
        f"thrift: {thrift.__version__}"
    )

for r in sc.parallelize(range(4), 4).map(_check).collect():
    print(f"[EXECUTOR] {r}")
```

Expected output in YARN logs:

```
[DRIVER]   Python: ./cis_etl_env/bin/python3.11
[EXECUTOR] Python: ./cis_etl_env/bin/python3.11 | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./cis_etl_env/bin/python3.11 | pyarrow: 14.0.2 | thrift: 0.16.0
```

---

## Quick Reference

```
WINDOWS MACHINE
│
├── WSL 2 (Ubuntu) ──────────────────────────────────────────────────────┐
│   python3.11 -m venv cis_etl_env                                       │
│   source cis_etl_env/bin/activate                                       │
│   pip install <packages> venv-pack                                      │
│   deactivate                                                            │
│   venv-pack -p cis_etl_env -o cis_etl_env.tar.gz          ──┐         │
│                                                               │         │
│   OR                                                          │         │
│                                                               │         │
├── Docker (python:3.11-slim) ────────────────────────────────-┤         │
│   same steps inside container                                 │         │
│   file written to mounted C:\ folder             ────────────┘         │
│                                                                         │
└────────────── scp cis_etl_env.tar.gz → edge-node ──────────────────────┘
                                │
                                ▼
                   hdfs dfs -put cis_etl_env.tar.gz
                   /mrw/cis/spark/venvs/
                                │
                                ▼
                   spark-submit --archives
                   hdfs:///mrw/cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env
                   --conf PYSPARK_PYTHON=./cis_etl_env/bin/python3.11
                                │
                         ┌──────┴──────┐
                         ▼             ▼
                     Executor 1   Executor 2   ...
                  (unpacks tar.gz, uses bundled Python 3.11)
```

---

## Rebuilding After Package Changes

```bash
# In WSL or Docker container
source cis_etl_env/bin/activate
pip install new-package==x.y.z
pip uninstall old-package
deactivate

# Re-pack with version tag to avoid YARN node cache confusion
venv-pack -p cis_etl_env -o cis_etl_env_v1.2.tar.gz

# Upload new version
hdfs dfs -put cis_etl_env_v1.2.tar.gz /mrw/cis/spark/venvs/
```

Update your `spark-submit` to reference `cis_etl_env_v1.2.tar.gz`.

---

## Troubleshooting

### `exec format error` — wrong architecture

The venv was built inside a Windows native environment (not WSL/Docker).
Windows binaries cannot run on Linux. Rebuild inside WSL 2 or Docker.

### `No module named 'X'` on executors

The package was not installed before packing.

```bash
# Rebuild:
source cis_etl_env/bin/activate
pip install missing-package
deactivate
venv-pack -p cis_etl_env -o cis_etl_env.tar.gz
hdfs dfs -put -f cis_etl_env.tar.gz /mrw/cis/spark/venvs/cis_etl_env.tar.gz
```

### `Permission denied: ./cis_etl_env/bin/python3.11`

venv-pack preserves permissions. If this happens, the tar.gz was re-zipped
with a Windows tool that stripped execute bits. Always use `venv-pack` or
`tar` on Linux — never re-zip with Windows Explorer.

### `Python version mismatch` warning in Spark logs

YARN worker nodes may have Python 3.8 or 3.9 as the system Python. That is
fine — `PYSPARK_PYTHON` overrides it entirely and points to the bundled 3.11.
The warning can be ignored as long as the executor output shows `python3.11`.

### Check YARN logs from Windows

```powershell
# SSH to edge node, then:
yarn logs -applicationId application_XXXXXXXXX_XXXX 2>&1 | `
  grep -i "python|PYSPARK|error|exception" | head -60
```
