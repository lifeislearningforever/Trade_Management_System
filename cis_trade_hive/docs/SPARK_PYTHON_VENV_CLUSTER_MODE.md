# Bundling Python + Packages for Spark Cluster Mode on Cloudera CML

## What Was Actually Done (Our Setup)

| Item | Value |
|---|---|
| **Build machine** | Windows laptop (user: `venh7u`) using **WSL 2** |
| **venv name** | `gmp_cis` |
| **Python version** | 3.11 (built inside WSL 2) |
| **Archive** | `gmp_cis.tar.gz` (produced by `venv-pack` inside WSL 2) |
| **Transfer** | SCP from WSL → Cloudera **edge node** (`~/gmp_cis.tar.gz`) |
| **HDFS path** | `/mrw/cis/spark/venvs/gmp_cis.tar.gz` |
| **spark-submit alias** | `gmp_cis` (`--archives ...#gmp_cis`) |
| **PYSPARK_PYTHON** | `./gmp_cis/bin/python3.11` |

> **Why WSL 2 and not Windows CMD/PowerShell?**
> `venv-pack` only works on Linux/macOS. Running it in Windows gives:
> `FileNotFoundError: [WinError 2] The system cannot find the path specified`
> WSL 2 provides a real Linux kernel so the packed archive contains correct
> Linux binaries that run on YARN worker nodes.

---

## The Problem

On **Cloudera CML**, when a PySpark job runs in cluster mode, the driver and
executors land on YARN worker nodes. Those nodes have a system Python managed
by Cloudera — you cannot `pip install` into it, and there is no local venv to
activate before submitting.

The solution: **bundle Python itself together with all required packages into a
tar.gz**, ship it via `spark-submit --archives`, and tell Spark to use that
bundled interpreter via `PYSPARK_PYTHON`.

---

## Step-by-Step — What We Did

### Step 1 — Open WSL 2 on Windows

```
# In PowerShell or CMD:
wsl
```

You will see a prompt like:
```
venh7u@DESKTOP-XXXXX:~$
```

You are now on Linux inside Windows.

### Step 2 — Check Python 3.11 is Available in WSL

```bash
python3.11 --version    # Python 3.11.x
```

If not found:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

### Step 3 — Navigate to Your Working Folder

Windows path `C:\Users\venh7u\CIS\cis\` maps to `/mnt/c/Users/venh7u/CIS/cis/` in WSL.

```bash
cd /mnt/c/Users/venh7u/CIS/cis/
```

If you hit NTFS permission issues, build in WSL home instead and copy over at the end:

```bash
cd ~
```

### Step 4 — Remove Any Old venv and Create a Fresh One

```bash
# Remove old Windows-built venv if it exists
rm -rf gmp_cis

# Create fresh Linux venv with Python 3.11
python3.11 -m venv gmp_cis

# Activate
source gmp_cis/bin/activate

# Confirm
which python      # .../gmp_cis/bin/python
python --version  # Python 3.11.x
```

### Step 5 — Install All Required Packages

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
    impyla \
    venv-pack

# Verify no broken dependencies
pip check
pip list
```

### Step 6 — Pack the venv

```bash
# Deactivate BEFORE packing
deactivate

# Pack — produces a self-contained Linux tar.gz
venv-pack -p gmp_cis -o gmp_cis.tar.gz

# Check output (typically 150–300 MB)
ls -lh gmp_cis.tar.gz
```

The archive contains:

```
gmp_cis/
gmp_cis/bin/python3.11          ← actual interpreter binary
gmp_cis/bin/python              ← symlink
gmp_cis/lib/python3.11/         ← stdlib + installed packages
gmp_cis/lib/python3.11/site-packages/pyarrow/
gmp_cis/lib/python3.11/site-packages/thrift/
...
```

### Step 6b — Verify All Required Packages Are Inside the Archive

Run these checks **before** copying to the edge node. Do not proceed if any
required package is missing — re-activate, pip install, deactivate, re-pack.

```bash
# 1. List every installed package (name + version) inside the archive
tar -tzf cis_etl_env.tar.gz \
  | grep "\.dist-info/METADATA" \
  | sed 's|.*/site-packages/||' \
  | sed 's|/METADATA||' \
  | sort

# 2. Confirm the specific packages we need are all present
tar -tzf cis_etl_env.tar.gz \
  | grep -E "site-packages/(pyhive|PyHive|thrift|pyarrow|openpyxl|chardet|dotenv|impyla|sasl|thrift_sasl)" \
  | grep "\.dist-info/METADATA"

# 3. Confirm the Python binary is inside and executable
tar -tzvf cis_etl_env.tar.gz | grep "bin/python"

# 4. Check archive size is reasonable (expect 100–300 MB)
ls -lh cis_etl_env.tar.gz
```

Expected output for check 2 — all 8 lines must appear:

```
cis_etl_env/lib/python3.10/site-packages/PyHive-0.7.0.dist-info/METADATA
cis_etl_env/lib/python3.10/site-packages/thrift-0.16.0.dist-info/METADATA
cis_etl_env/lib/python3.10/site-packages/thrift_sasl-0.4.3.dist-info/METADATA
cis_etl_env/lib/python3.10/site-packages/pyarrow-xx.x.x.dist-info/METADATA
cis_etl_env/lib/python3.10/site-packages/openpyxl-x.x.x.dist-info/METADATA
cis_etl_env/lib/python3.10/site-packages/chardet-x.x.x.dist-info/METADATA
cis_etl_env/lib/python3.10/site-packages/python_dotenv-1.0.1.dist-info/METADATA
cis_etl_env/lib/python3.10/site-packages/impyla-x.x.x.dist-info/METADATA
```

If any package is missing:

```bash
source cis_etl_env/bin/activate
pip install <missing-package>
deactivate
venv-pack -p cis_etl_env -o cis_etl_env.tar.gz
```

---

### Step 7 — SCP to Cloudera Edge Node

If you built in WSL home (`~`), first copy to the Windows-accessible path:

```bash
cp ~/gmp_cis.tar.gz /mnt/c/Users/venh7u/CIS/cis/gmp_cis.tar.gz
```

Then SCP to the edge node (run from WSL or Windows PowerShell):

```bash
scp /mnt/c/Users/venh7u/CIS/cis/gmp_cis.tar.gz \
    venh7u@<edge-node-hostname>:~/
```

### Step 8 — Upload from Edge Node to HDFS

SSH to the edge node:

```bash
ssh venh7u@<edge-node-hostname>
```

Then upload:

```bash
# Create staging directory (ignore error if already exists)
hdfs dfs -mkdir -p /mrw/cis/spark/venvs/

# Upload
hdfs dfs -put -f ~/gmp_cis.tar.gz /mrw/cis/spark/venvs/gmp_cis.tar.gz

# Verify
hdfs dfs -ls /mrw/cis/spark/venvs/
```

---

## spark-submit Command

Run from the Cloudera **edge node** (SSH) or CML terminal:

```bash
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --num-executors 4 \
  --executor-cores 2 \
  --executor-memory 4g \
  --driver-memory 2g \
  \
  --archives hdfs:///mrw/cis/spark/venvs/gmp_cis.tar.gz#gmp_cis \
  \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11 \
  \
  your_etl_job.py \
  --arg1 value1
```

### How `--archives` works

```
--archives <hdfs-path>#<local-alias>
```

| Part | Value | What happens |
|---|---|---|
| `hdfs-path` | `hdfs:///mrw/cis/spark/venvs/gmp_cis.tar.gz` | YARN downloads this to every node |
| `local-alias` | `gmp_cis` | YARN unpacks the tar.gz into this directory name in each executor's working dir |
| `PYSPARK_PYTHON` | `./gmp_cis/bin/python3.11` | Spark uses this interpreter — relative to executor working dir |

---

## Submitting from CML (no terminal spark-submit)

### Via CML Jobs UI

1. **New Job** → Script: `your_etl_job.py`
2. Engine: **Spark**
3. **Spark Config** (add these):
   ```
   spark.archives=hdfs:///mrw/cis/spark/venvs/gmp_cis.tar.gz#gmp_cis
   spark.yarn.appMasterEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11
   spark.executorEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11
   ```
4. **File Dependencies**: *(not needed — archive is on HDFS)*

### Via Python Script in CML Session

```python
import subprocess

result = subprocess.run([
    "spark-submit",
    "--master", "yarn",
    "--deploy-mode", "cluster",
    "--archives", "hdfs:///mrw/cis/spark/venvs/gmp_cis.tar.gz#gmp_cis",
    "--conf", "spark.yarn.appMasterEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11",
    "--conf", "spark.executorEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11",
    "your_etl_job.py",
], capture_output=True, text=True)

print(result.stdout)
print(result.stderr)
```

---

## Verify the Bundled Environment Works

Add this snippet to the top of your PySpark job to confirm the correct Python
and packages are active on both the driver and executors:

```python
import sys
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("CIS_ETL_ENV_CHECK").getOrCreate()
sc = spark.sparkContext

# Check driver
print(f"[DRIVER] Python: {sys.executable}")

# Check executors
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

Expected output in YARN driver logs:

```
[DRIVER]   Python: ./gmp_cis/bin/python3.11
[EXECUTOR] Python: ./gmp_cis/bin/python3.11 | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./gmp_cis/bin/python3.11 | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./gmp_cis/bin/python3.11 | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./gmp_cis/bin/python3.11 | pyarrow: 14.0.2 | thrift: 0.16.0
```

---

## Quick Reference — Full Copy-Paste Sequence

Open WSL (`wsl` in PowerShell/CMD) then paste:

```bash
# 1. Navigate (or use ~ if /mnt/c/ has permission issues)
cd /mnt/c/Users/venh7u/CIS/cis/

# 2. Clean and create fresh Linux venv
rm -rf gmp_cis
python3.11 -m venv gmp_cis
source gmp_cis/bin/activate

# 3. Install packages
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

# 4. Pack
venv-pack -p gmp_cis -o gmp_cis.tar.gz
ls -lh gmp_cis.tar.gz

# 4b. Verify all required packages are inside BEFORE copying to edge node
tar -tzf gmp_cis.tar.gz \
  | grep -E "site-packages/(pyhive|PyHive|thrift|pyarrow|openpyxl|chardet|dotenv|impyla|sasl|thrift_sasl)" \
  | grep "\.dist-info/METADATA"
# All 8 packages must appear — if any missing: re-activate, pip install, deactivate, re-pack

# 5. SCP to edge node (only after verify passes)
scp gmp_cis.tar.gz venh7u@<edge-node-hostname>:~/
```

On the edge node:

```bash
# 6. Upload to HDFS
hdfs dfs -mkdir -p /mrw/cis/spark/venvs/
hdfs dfs -put -f ~/gmp_cis.tar.gz /mrw/cis/spark/venvs/gmp_cis.tar.gz
hdfs dfs -ls /mrw/cis/spark/venvs/

# 7. Submit
spark-submit \
  --master yarn --deploy-mode cluster \
  --archives hdfs:///mrw/cis/spark/venvs/gmp_cis.tar.gz#gmp_cis \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./gmp_cis/bin/python3.11 \
  your_etl_job.py
```

---

## Re-packing After Package Changes

```bash
# In WSL — activate, add/remove packages, re-pack with a version tag
source gmp_cis/bin/activate
pip install new-package==x.y.z
deactivate

venv-pack -p gmp_cis -o gmp_cis_v1.1.tar.gz

# Upload new version
scp gmp_cis_v1.1.tar.gz venh7u@<edge-node-hostname>:~/
ssh venh7u@<edge-node-hostname>
hdfs dfs -put -f ~/gmp_cis_v1.1.tar.gz /mrw/cis/spark/venvs/gmp_cis_v1.1.tar.gz
```

Update the `--archives` path in `spark-submit` to reference the new version.

---

## Troubleshooting

### `FileNotFoundError: [WinError 2]` when running venv-pack

You are running `venv-pack` in Windows CMD or PowerShell — it only works on Linux.
Open WSL (`wsl`) and run all steps from there.

### `exec format error` on executors

The archive was built in Windows (not WSL/Docker). Windows binaries are PE format,
not ELF — they cannot run on Linux YARN nodes. Rebuild inside WSL 2.

### `No module named 'X'` on executors

The package was not installed before packing. Re-run from Step 4 (activate → pip install → deactivate → venv-pack → scp → hdfs put).

### `Permission denied` on `./gmp_cis/bin/python3.11`

`venv-pack` preserves execute bits correctly. If this happens, someone re-zipped
the archive with a Windows tool (e.g. 7-Zip, Windows Explorer) that strips Unix
permissions. Always transfer the original `gmp_cis.tar.gz` produced by `venv-pack`.

### `Python version mismatch` in Spark logs

The Python version inside the archive (3.11) must match what YARN worker nodes
expect. If YARN workers run 3.8 or 3.9 as system Python, that is fine —
`PYSPARK_PYTHON` overrides it entirely. The warning can be ignored as long as
executor output shows `python3.11`.

### Archive size mismatch after SCP (corruption check)

```bash
# Local (WSL)
ls -lh gmp_cis.tar.gz

# On edge node after SCP
ls -lh ~/gmp_cis.tar.gz

# On HDFS after put
hdfs dfs -du -h /mrw/cis/spark/venvs/gmp_cis.tar.gz
```

All three sizes should match. If not, re-SCP and re-upload.

### `permission denied` writing to `/mnt/c/` in WSL

Build in WSL home instead and copy the finished archive to Windows:

```bash
cd ~
rm -rf gmp_cis
python3.11 -m venv gmp_cis
source gmp_cis/bin/activate
pip install --upgrade pip
pip install PyHive==0.7.0 thrift==0.16.0 thrift-sasl==0.4.3 \
            pyarrow openpyxl chardet python-dotenv impyla venv-pack
deactivate
venv-pack -p ~/gmp_cis -o ~/gmp_cis.tar.gz
# Copy to Windows folder (optional)
cp ~/gmp_cis.tar.gz /mnt/c/Users/venh7u/CIS/cis/gmp_cis.tar.gz
```

### Check YARN application logs

```bash
# Get applicationId from CML job output, then on edge node:
yarn logs -applicationId application_XXXXXXXXX_XXXX 2>&1 | \
  grep -i "python\|PYSPARK\|error\|exception" | head -60
```

---

## Ranger / Kerberos Notes (Cloudera CDP)

```bash
# If Kerberos is enabled, kinit before spark-submit
kinit venh7u@YOUR.REALM.COM
klist    # verify ticket is valid

# Ranger: ensure the service account has READ on the venv HDFS path
# Cloudera Ranger UI → HDFS policies → /mrw/cis/spark/venvs/ → READ for spark user
```

---

## Windows Path → WSL Path Reference

| Windows | WSL |
|---|---|
| `C:\` | `/mnt/c/` |
| `C:\Users\venh7u\` | `/mnt/c/Users/venh7u/` |
| `C:\Users\venh7u\CIS\cis\` | `/mnt/c/Users/venh7u/CIS/cis/` |
| `C:\Users\venh7u\CIS\cis\gmp_cis.tar.gz` | `/mnt/c/Users/venh7u/CIS/cis/gmp_cis.tar.gz` |
