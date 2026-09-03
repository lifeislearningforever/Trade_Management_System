# Bundling Python + Packages for Spark Cluster Mode on Cloudera CML

## What Was Actually Done (Our Setup)

| Item | Value |
|---|---|
| **Build machine** | Cloudera CML terminal (`cdsw@...`) |
| **venv name** | `cis_etl_env` |
| **Python version** | 3.10 (CML system Python) |
| **Archive** | `cis_etl_env.tar.gz` (116 MB, produced by `venv-pack` on CML) |
| **Transfer** | SCP from CML → Cloudera **edge node** `lxmrwtsgv0w1` |
| **HDFS path** | `/cis/spark/venvs/cis_etl_env.tar.gz` |
| **HDFS owner** | `ownicisgw` / supergroup |
| **spark-submit alias** | `cis_etl_env` (`--archives ...#cis_etl_env`) |
| **PYSPARK_PYTHON** | `./cis_etl_env/bin/python3.10` |

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

## Step-by-Step — What We Did (CML Terminal)

### Step 1 — Open CML Terminal Session

In the CML UI: **New Session → Terminal Access → Open Terminal**

```bash
# Confirm Python version
python3 --version       # e.g. Python 3.10.x
which python3           # e.g. /usr/local/bin/python3
```

### Step 2 — Create venv with `--copies` Flag (CRITICAL)

> **Why `--copies`?**
> Without this flag, `venv-pack` creates symlinks that point to the CML system
> Python path (e.g. `/usr/local/bin/python3.10`). That path does not exist on
> YARN worker nodes — so `python3`, `pip` etc. all show "No such file or
> directory" after unpacking on the edge node. `--copies` forces real binary
> copies that work on any node.

```bash
# Remove any old venv
rm -rf ~/cis_etl_env

# Create fresh venv with --copies (real binaries, not symlinks)
python3 -m venv --copies ~/cis_etl_env

# Activate
source ~/cis_etl_env/bin/activate

# Confirm
which python
python --version
```

### Step 3 — Install All Required Packages

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

### Step 4 — Pack the venv

```bash
# Deactivate BEFORE packing
deactivate

# Pack — produces a self-contained Linux tar.gz
venv-pack -p ~/cis_etl_env -o ~/cis_etl_env.tar.gz

# Check output (typically 100–200 MB)
ls -lh ~/cis_etl_env.tar.gz
```

### Step 5 — Add `cis_etl_env/` Prefix to Archive (CRITICAL)

> **Why this step?**
> `venv-pack` always produces a **flat** archive — contents are at the root
> (`bin/python3.10`, `lib/...`). When YARN unpacks `--archives file.tar.gz#alias`,
> it creates a folder named `alias/` and puts the flat contents inside it.
> So `PYSPARK_PYTHON=./alias/bin/python3.10` would look for
> `alias/bin/python3.10` but actually finds `alias/bin/python3.10` only if
> the archive already has the subfolder. To be safe and explicit, we wrap
> the flat archive into a named subfolder so the path is unambiguous.

```bash
# Unpack flat archive into a named subfolder
mkdir -p ~/cis_etl_env_wrap/cis_etl_env
tar -xzf ~/cis_etl_env.tar.gz -C ~/cis_etl_env_wrap/cis_etl_env

# Verify python3.10 is a REAL FILE not a symlink
ls -la ~/cis_etl_env_wrap/cis_etl_env/bin/python*
# Must show: -rwxr-xr-x (not lrwxrwxrwx)

# Re-pack with cis_etl_env/ prefix
cd ~/cis_etl_env_wrap
tar -czf ~/cis_etl_env.tar.gz cis_etl_env/

# Verify — must show cis_etl_env/bin/python3.10
tar -tzf ~/cis_etl_env.tar.gz | grep "bin/python"

# Clean up temp folder
rm -rf ~/cis_etl_env_wrap
cd ~
```

Expected output:
```
cis_etl_env/bin/python
cis_etl_env/bin/python3
cis_etl_env/bin/python3.10   ← must be present
```

The archive now contains:

```
cis_etl_env/
cis_etl_env/bin/python3.10      ← real binary (not symlink)
cis_etl_env/bin/python3         ← real binary
cis_etl_env/bin/python          ← real binary
cis_etl_env/lib/python3.10/     ← stdlib + installed packages
cis_etl_env/lib/python3.10/site-packages/pyarrow/
cis_etl_env/lib/python3.10/site-packages/thrift/
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
    ownicisgw@lxmrwtsgv0w1:~/
```

### Step 8 — Upload from Edge Node to HDFS

SSH to the edge node:

```bash
ssh ownicisgw@lxmrwtsgv0w1
```

Then upload:

```bash
# Create staging directory (ignore error if already exists)
hdfs dfs -mkdir -p /cis/spark/venvs/

# Upload
hdfs dfs -put -f ~/gmp_cis.tar.gz /cis/spark/venvs/gmp_cis.tar.gz

# Verify
hdfs dfs -ls /cis/spark/venvs/
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
  --archives hdfs:///cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \
  \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
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
| `hdfs-path` | `hdfs:///cis/spark/venvs/gmp_cis.tar.gz` | YARN downloads this to every node |
| `local-alias` | `gmp_cis` | YARN unpacks the tar.gz into this directory name in each executor's working dir |
| `PYSPARK_PYTHON` | `./cis_etl_env/bin/python3.10` | Spark uses this interpreter — relative to executor working dir |

---

## Submitting from CML (no terminal spark-submit)

### Via CML Jobs UI

1. **New Job** → Script: `your_etl_job.py`
2. Engine: **Spark**
3. **Spark Config** (add these):
   ```
   spark.archives=hdfs:///cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env
   spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10
   spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10
   ```
4. **File Dependencies**: *(not needed — archive is on HDFS)*

### Via Python Script in CML Session

```python
import subprocess

result = subprocess.run([
    "spark-submit",
    "--master", "yarn",
    "--deploy-mode", "cluster",
    "--archives", "hdfs:///cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env",
    "--conf", "spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10",
    "--conf", "spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10",
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
[DRIVER]   Python: ./cis_etl_env/bin/python3.10
[EXECUTOR] Python: ./cis_etl_env/bin/python3.10 | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./cis_etl_env/bin/python3.10 | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./cis_etl_env/bin/python3.10 | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./cis_etl_env/bin/python3.10 | pyarrow: 14.0.2 | thrift: 0.16.0
```

---

## Quick Reference — Full Copy-Paste Sequence

Run in **CML Terminal**:

```bash
# 1. Create venv with --copies (real binaries, not symlinks)
rm -rf ~/cis_etl_env
python3 -m venv --copies ~/cis_etl_env
source ~/cis_etl_env/bin/activate

# 2. Install packages
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

# 3. Pack
venv-pack -p ~/cis_etl_env -o ~/cis_etl_env.tar.gz
ls -lh ~/cis_etl_env.tar.gz

# 4. Verify all required packages are inside BEFORE copying to edge node
tar -tzf ~/cis_etl_env.tar.gz \
  | grep -E "site-packages/(pyhive|PyHive|thrift|pyarrow|openpyxl|chardet|dotenv|impyla|sasl|thrift_sasl)" \
  | grep "\.dist-info/METADATA"
# All 8 packages must appear

# 5. Wrap with cis_etl_env/ prefix (venv-pack always packs flat)
mkdir -p ~/cis_etl_env_wrap/cis_etl_env
tar -xzf ~/cis_etl_env.tar.gz -C ~/cis_etl_env_wrap/cis_etl_env
ls -la ~/cis_etl_env_wrap/cis_etl_env/bin/python*  # must be -rwxr-xr-x not symlinks
cd ~/cis_etl_env_wrap
tar -czf ~/cis_etl_env.tar.gz cis_etl_env/
cd ~
rm -rf ~/cis_etl_env_wrap

# 6. Verify prefix is correct
tar -tzf ~/cis_etl_env.tar.gz | grep "bin/python"
# Must show: cis_etl_env/bin/python3.10

# 7. SCP to edge node (only after verify passes)
scp ~/cis_etl_env.tar.gz ownicisgw@lxmrwtsgv0w1:~/
```

On the edge node:

```bash
# 6. Upload to HDFS
hdfs dfs -mkdir -p /cis/spark/venvs/
hdfs dfs -put -f ~/gmp_cis.tar.gz /cis/spark/venvs/gmp_cis.tar.gz
hdfs dfs -ls /cis/spark/venvs/

# 7. Submit
spark-submit \
  --master yarn --deploy-mode cluster \
  --archives hdfs:///cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
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
scp gmp_cis_v1.1.tar.gz ownicisgw@lxmrwtsgv0w1:~/
ssh ownicisgw@lxmrwtsgv0w1
hdfs dfs -put -f ~/gmp_cis_v1.1.tar.gz /cis/spark/venvs/gmp_cis_v1.1.tar.gz
```

Update the `--archives` path in `spark-submit` to reference the new version.

---

## Troubleshooting

### `libpython3.10.so.1.0: cannot open shared object file: No such file or directory`

**Symptom:** Python binary runs on CML but fails on the edge node or YARN workers:
```
error while loading shared libraries: libpython3.10.so.1.0: cannot open shared object file: No such file or directory
```

**Cause:** Even with `--copies`, the Python binary is **dynamically linked** — it needs
`libpython3.10.so.1.0` at runtime. The `.so` exists on the CML build machine but is
missing on the edge node (because the edge node has no Python 3.10 installed).

**Fix: copy the `.so` from CML into the venv's `lib/` folder before packing.**

Run on **CML terminal**:

```bash
# Step 1: Find where the .so lives on CML
find / -name "libpython3.10.so.1.0" 2>/dev/null
# Typically: /usr/local/lib/libpython3.10.so.1.0

# Step 2: Verify the python binary is linked to it
ldd /usr/local/bin/python3.10 | grep python
# Expected: libpython3.10.so.1.0 => /usr/local/lib/libpython3.10.so.1.0

# Step 3: Copy .so into the venv lib folder
cp /usr/local/lib/libpython3.10.so.1.0 ~/cis_etl_env/lib/

# Step 4: Repack (deactivate first if still active)
deactivate
venv-pack -p ~/cis_etl_env -o ~/cis_etl_env.tar.gz

# Step 5: Verify .so is inside the archive
tar -tzf ~/cis_etl_env.tar.gz | grep "libpython"
# Must show: cis_etl_env/lib/libpython3.10.so.1.0
```

Then add these two `--conf` lines to your `spark-submit`:

```bash
--conf "spark.executorEnv.LD_LIBRARY_PATH=./cis_etl_env/lib" \
--conf "spark.yarn.appMasterEnv.LD_LIBRARY_PATH=./cis_etl_env/lib" \
```

**Quick test on the edge node after unpacking:**
```bash
cd /path/to/unpacked/
LD_LIBRARY_PATH=./cis_etl_env/lib ./cis_etl_env/bin/python3.10 --version
# Must print: Python 3.10.x  (not "No such file or directory")
```

> **Why not rebuild on the edge node?**
> The edge node does not have Python 3.10 installed, so a venv cannot be created
> there. The CML-built venv + bundled `.so` is the correct approach.

---

### `FileNotFoundError: [WinError 2]` when running venv-pack

You are running `venv-pack` in Windows CMD or PowerShell — it only works on Linux.
Open WSL (`wsl`) and run all steps from there.

### `exec format error` on executors

The archive was built in Windows (not WSL/Docker). Windows binaries are PE format,
not ELF — they cannot run on Linux YARN nodes. Rebuild inside WSL 2.

### `No module named 'X'` on executors

The package was not installed before packing. Re-run from Step 4 (activate → pip install → deactivate → venv-pack → scp → hdfs put).

### `Permission denied` on `./cis_etl_env/bin/python3.10`

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
hdfs dfs -du -h /cis/spark/venvs/gmp_cis.tar.gz
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
# Cloudera Ranger UI → HDFS policies → /cis/spark/venvs/ → READ for spark user
```

---

## Windows Path → WSL Path Reference

| Windows | WSL |
|---|---|
| `C:\` | `/mnt/c/` |
| `C:\Users\venh7u\` | `/mnt/c/Users/venh7u/` |
| `C:\Users\venh7u\CIS\cis\` | `/mnt/c/Users/venh7u/CIS/cis/` |
| `C:\Users\venh7u\CIS\cis\gmp_cis.tar.gz` | `/mnt/c/Users/venh7u/CIS/cis/gmp_cis.tar.gz` |
