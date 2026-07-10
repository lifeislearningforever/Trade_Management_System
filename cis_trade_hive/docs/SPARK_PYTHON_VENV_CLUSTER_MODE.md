# Bundling Python + Packages for Spark Cluster Mode on Cloudera CML

## The Problem

On **Cloudera CML**, when a PySpark job runs in cluster mode, the driver and
executors land on YARN worker nodes. Those nodes have a system Python managed
by Cloudera — you cannot `pip install` into it, and there is no local venv to
activate before submitting.

The solution: **bundle Python itself together with all required packages into a
single zip**, ship it via `spark-submit --archives`, and tell Spark to use
that bundled interpreter via `PYSPARK_PYTHON`.

Two methods are available depending on what is installed in your CML session:

| Method | Tool | When to use |
|---|---|---|
| **A — venv-pack** | `pip install venv-pack` | You can create a venv inside CML (recommended) |
| **B — conda-pack** | `conda pack` | Your CML runtime uses a conda environment |

Both produce a self-contained archive with Python + all packages + shared libs.

---

## Method A — venv-pack (recommended for CML pip-based runtimes)

### A1 — Open a CML Terminal Session

In the CML UI: **New Session → Terminal Access → Open Terminal**

Check the Python version (must match YARN worker nodes):

```bash
python3 --version        # e.g. Python 3.10.14
which python3            # e.g. /usr/local/bin/python3
```

### A2 — Create a Virtual Environment Inside CML

```bash
# Create venv in your CML home directory
python3 -m venv ~/cis_etl_env

# Activate it
source ~/cis_etl_env/bin/activate

# Confirm
which python     # ~/cis_etl_env/bin/python
python --version
```

### A3 — Install All Required Packages

```bash
pip install --upgrade pip

# Core packages needed by the CIS ETL job
pip install \
    PyHive==0.7.0 \
    thrift==0.16.0 \
    thrift-sasl==0.4.3 \
    pyarrow>=14.0.0 \
    openpyxl>=3.1.0 \
    chardet>=5.0.0 \
    python-dotenv==1.0.1 \
    impyla

# Verify — no missing dependencies
pip check
pip list
```

### A4 — Install venv-pack

`venv-pack` is the key tool. Unlike a plain `zip -r`, it:
- Copies shared libraries (`.so` files) that stdlib modules like `_ssl`, `_lzma` depend on
- Rewrites internal symlinks so the archive is relocatable on any node
- Produces a `.tar.gz` that Spark can unpack natively

```bash
pip install venv-pack
```

### A5 — Pack the Virtual Environment

```bash
# Deactivate first — venv-pack must run from outside the venv
deactivate

# Pack into a tar.gz (Spark --archives supports both .zip and .tar.gz)
venv-pack -p ~/cis_etl_env -o cis_etl_env.tar.gz

# Check the output
ls -lh cis_etl_env.tar.gz   # typically 80–400 MB depending on packages
```

The archive contains:

```
cis_etl_env/
cis_etl_env/bin/python3.10          ← actual interpreter binary
cis_etl_env/bin/python              ← symlink
cis_etl_env/lib/python3.10/        ← stdlib + installed packages
cis_etl_env/lib/python3.10/site-packages/pyarrow/
cis_etl_env/lib/python3.10/site-packages/thrift/
...
```

### A6 — Upload to HDFS

```bash
# Create staging directory
hdfs dfs -mkdir -p /mrw/cis/spark/venvs/

# Upload
hdfs dfs -put -f cis_etl_env.tar.gz /mrw/cis/spark/venvs/cis_etl_env.tar.gz

# Verify
hdfs dfs -ls /mrw/cis/spark/venvs/
```

---

## Method B — conda-pack (for CML conda-based runtimes)

Use this if your CML session is running inside a conda environment.

### B1 — Check Conda Environment

```bash
conda info --envs       # list environments
conda activate base     # or your named env
python --version
```

### B2 — Install Packages into Conda Env

```bash
# Add packages to the current conda env
conda install -y pyarrow openpyxl chardet
pip install PyHive==0.7.0 thrift==0.16.0 thrift-sasl==0.4.3 python-dotenv impyla
```

### B3 — Pack the Conda Environment

```bash
conda install -y conda-pack   # install packer tool

# Pack current active env
conda pack -o cis_etl_env.tar.gz

# Or pack by name
conda pack -n your_env_name -o cis_etl_env.tar.gz
```

### B4 — Upload to HDFS

```bash
hdfs dfs -mkdir -p /mrw/cis/spark/venvs/
hdfs dfs -put -f cis_etl_env.tar.gz /mrw/cis/spark/venvs/cis_etl_env.tar.gz
hdfs dfs -ls /mrw/cis/spark/venvs/
```

---

## spark-submit Command (same for both methods)

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
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
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
| `hdfs-path` | `hdfs:///mrw/cis/spark/venvs/cis_etl_env.tar.gz` | YARN downloads this to every node |
| `local-alias` | `cis_etl_env` | YARN unpacks the tar.gz into this directory name in the executor working dir |
| `PYSPARK_PYTHON` | `./cis_etl_env/bin/python` | Spark uses this interpreter — relative to working dir |

---

## Submitting from CML (no terminal spark-submit)

In CML, jobs can be submitted via **CML Jobs** or **cdsw-run**:

### Via CML Jobs UI

1. **New Job** → Script: `your_etl_job.py`
2. Engine: **Spark**
3. **Spark Config** (add these):
   ```
   spark.archives=hdfs:///mrw/cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env
   spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python
   spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python
   ```
4. **File Dependencies**: *(not needed — archive is on HDFS)*

### Via Python Script in CML Session

```python
import subprocess

result = subprocess.run([
    "spark-submit",
    "--master", "yarn",
    "--deploy-mode", "cluster",
    "--archives", "hdfs:///mrw/cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env",
    "--conf", "spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python",
    "--conf", "spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python",
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

# Check executor
def _check(_):
    import sys, pyarrow, thrift
    return (
        f"Python: {sys.executable} | "
        f"pyarrow: {pyarrow.__version__} | "
        f"thrift: {thrift.__version__}"
    )

results = sc.parallelize(range(4), 4).map(_check).collect()
for r in results:
    print(f"[EXECUTOR] {r}")
```

Expected output in YARN driver logs:

```
[DRIVER]   Python: ./cis_etl_env/bin/python
[EXECUTOR] Python: ./cis_etl_env/bin/python | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./cis_etl_env/bin/python | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./cis_etl_env/bin/python | pyarrow: 14.0.2 | thrift: 0.16.0
[EXECUTOR] Python: ./cis_etl_env/bin/python | pyarrow: 14.0.2 | thrift: 0.16.0
```

---

## Quick Reference

```bash
# ── Method A: venv-pack ─────────────────────────────────────────────────────

# 1. Inside CML terminal — create venv and install packages
python3 -m venv ~/cis_etl_env
source ~/cis_etl_env/bin/activate
pip install --upgrade pip
pip install PyHive==0.7.0 thrift==0.16.0 thrift-sasl==0.4.3 \
            pyarrow openpyxl chardet python-dotenv impyla venv-pack
deactivate

# 2. Pack
venv-pack -p ~/cis_etl_env -o cis_etl_env.tar.gz

# 3. Upload to HDFS
hdfs dfs -mkdir -p /mrw/cis/spark/venvs/
hdfs dfs -put -f cis_etl_env.tar.gz /mrw/cis/spark/venvs/cis_etl_env.tar.gz

# 4. Submit
spark-submit \
  --master yarn --deploy-mode cluster \
  --archives hdfs:///mrw/cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
  your_etl_job.py


# ── Method B: conda-pack ─────────────────────────────────────────────────────

# 1. Install packages into current conda env
conda install -y pyarrow openpyxl chardet conda-pack
pip install PyHive thrift thrift-sasl impyla python-dotenv

# 2. Pack
conda pack -o cis_etl_env.tar.gz

# 3. Upload & submit (same as above)
hdfs dfs -put -f cis_etl_env.tar.gz /mrw/cis/spark/venvs/cis_etl_env.tar.gz
spark-submit \
  --master yarn --deploy-mode cluster \
  --archives hdfs:///mrw/cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
  your_etl_job.py
```

---

## Troubleshooting

### `No module named 'X'` on executors

Package was not in the venv when it was packed.

```bash
source ~/cis_etl_env/bin/activate
pip install missing-package
deactivate
venv-pack -p ~/cis_etl_env -o cis_etl_env.tar.gz
hdfs dfs -put -f cis_etl_env.tar.gz /mrw/cis/spark/venvs/cis_etl_env.tar.gz
```

### `Permission denied` on `./cis_etl_env/bin/python`

venv-pack sets correct permissions. If using plain `zip -r` instead, bits are
lost. Always use `venv-pack` or `conda-pack` — they preserve execute bits.

### `Python version mismatch`

The Python in your CML session must match the Python on YARN worker nodes.
Check both:

```bash
# In CML terminal
python3 --version

# On a YARN worker (ask Cloudera admin or check CDP Manager)
# Cloudera Manager → Hosts → any worker → Processes → check Python version
```

If they differ, ask your Cloudera admin to align them, or use a different CML
runtime version that matches.

### `Error: Archive is not a valid zip/tar file`

HDFS upload may have been corrupted or truncated. Re-upload and verify:

```bash
hdfs dfs -du -h /mrw/cis/spark/venvs/cis_etl_env.tar.gz
# Compare with local:
ls -lh cis_etl_env.tar.gz
```

### Check YARN application logs

```bash
# Get application ID from CML job logs, then:
yarn logs -applicationId application_XXXXXXXXX_XXXX 2>&1 | \
  grep -i "python\|PYSPARK\|error\|exception" | head -60
```

### Re-pack after adding packages (versioning tip)

Tag the archive with a version to avoid stale caches on YARN nodes:

```bash
venv-pack -p ~/cis_etl_env -o cis_etl_env_v1.2.tar.gz
hdfs dfs -put cis_etl_env_v1.2.tar.gz /mrw/cis/spark/venvs/
# Update --archives path in spark-submit accordingly
```

---

## Ranger / Kerberos Notes (Cloudera CDP)

```bash
# If Kerberos is enabled, kinit before spark-submit
kinit your_user@YOUR.REALM.COM
klist    # verify ticket

# Ranger: ensure the service account has READ on the venv HDFS path
# Cloudera Ranger UI → HDFS policies → /mrw/cis/spark/venvs/ → READ for spark user
```
