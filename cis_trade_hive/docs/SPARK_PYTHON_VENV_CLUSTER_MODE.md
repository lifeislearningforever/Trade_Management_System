# Python Virtual Environment for Spark Cluster Mode (--archives)

## Overview

When running a PySpark job in **cluster mode** on a Cloudera CDP / YARN cluster,
the driver and all executors run on worker nodes that may not have your Python
packages installed. The solution is to:

1. Build a self-contained Python virtual environment locally
2. Zip it
3. Ship the zip via `--archives` in `spark-submit`
4. Point Spark at the bundled Python interpreter with `PYSPARK_PYTHON`

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10.x | Must match the Python version on cluster worker nodes |
| `venv` module | Included in Python 3.3+ stdlib |
| `pip` | Included with Python |
| Network access to PyPI | Or a local mirror / Nexus repo |
| `spark-submit` on PATH | Available on the Cloudera edge node |

> **Important:** Build the virtual environment **on a Linux machine with the same
> OS and Python version as the cluster workers.** A venv built on macOS will not
> work on a Linux YARN cluster.

---

## Step 1 — Create the Virtual Environment

```bash
# Choose a name that reflects the job or project
VENV_NAME="cis_etl_env"

# Create venv (do NOT use --system-site-packages — keep it isolated)
python3.10 -m venv ${VENV_NAME}

# Activate it
source ${VENV_NAME}/bin/activate
```

Verify you are using the venv's Python:

```bash
which python   # should show /path/to/cis_etl_env/bin/python
python --version   # Python 3.10.x
```

---

## Step 2 — Install Required Packages

Install from the project `requirements.txt`, or install only the packages your
Spark job actually needs (keep it lean — fewer packages = smaller zip = faster
distribution to executors).

### Option A — Full project requirements

```bash
pip install --upgrade pip

pip install \
    PyHive==0.7.0 \
    thrift==0.16.0 \
    thrift-sasl==0.4.3 \
    pyarrow>=14.0.0 \
    openpyxl>=3.1.0 \
    chardet>=5.0.0 \
    python-dotenv==1.0.1
```

Or from file:

```bash
pip install -r requirements.txt
```

### Option B — Spark-job-only packages (recommended for lean bundles)

```bash
pip install --upgrade pip

# Only what the ETL job imports
pip install pyarrow impyla thrift thrift-sasl python-dotenv chardet openpyxl
```

### Verify installs

```bash
pip list
pip check    # flag any dependency conflicts before zipping
```

---

## Step 3 — Deactivate and Zip the Virtual Environment

```bash
# Deactivate first
deactivate

# Zip the entire venv directory
# Use zip -r, NOT tar.gz — Spark's --archives unpacks .zip natively
zip -r ${VENV_NAME}.zip ${VENV_NAME}/
```

Verify the zip:

```bash
ls -lh ${VENV_NAME}.zip        # check size (typically 50 MB – 300 MB)
unzip -l ${VENV_NAME}.zip | head -20   # spot-check contents
```

Expected structure inside the zip:

```
cis_etl_env/
cis_etl_env/bin/
cis_etl_env/bin/python
cis_etl_env/bin/python3.10
cis_etl_env/lib/
cis_etl_env/lib/python3.10/
cis_etl_env/lib/python3.10/site-packages/
cis_etl_env/lib/python3.10/site-packages/pyarrow/
...
```

---

## Step 4 — Copy the Zip to HDFS (optional but recommended)

Putting the zip on HDFS avoids re-uploading it on every submission and lets all
nodes fetch it from a shared location efficiently.

```bash
# Create a staging directory on HDFS
hdfs dfs -mkdir -p /mrw/cis/spark/venvs/

# Upload the zip
hdfs dfs -put -f ${VENV_NAME}.zip /mrw/cis/spark/venvs/${VENV_NAME}.zip

# Verify
hdfs dfs -ls /mrw/cis/spark/venvs/
```

---

## Step 5 — spark-submit in Cluster Mode

```bash
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --num-executors 4 \
  --executor-cores 2 \
  --executor-memory 4g \
  --driver-memory 2g \
  \
  # Ship the venv zip to every node via YARN's distributed cache
  --archives hdfs:///mrw/cis/spark/venvs/cis_etl_env.zip#cis_etl_env \
  \
  # Tell Spark to use the bundled Python (path is relative to the unpacked archive)
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
  \
  # Your PySpark script
  your_etl_job.py \
  --arg1 value1 \
  --arg2 value2
```

### Key `--archives` Syntax

```
--archives <source>#<alias>
```

| Part | Example | Meaning |
|---|---|---|
| `<source>` | `hdfs:///mrw/cis/spark/venvs/cis_etl_env.zip` | Where YARN fetches the zip from |
| `<alias>` | `cis_etl_env` | The local directory name after unpacking on each worker |

YARN unpacks the zip into `./cis_etl_env/` in the executor's working directory.
`PYSPARK_PYTHON=./cis_etl_env/bin/python` then points at the bundled interpreter.

### Local file (no HDFS) — alternative

If you cannot use HDFS, pass a local path on the edge node. Spark will distribute
it automatically, but this is slower for large zips:

```bash
--archives /home/your_user/cis_etl_env.zip#cis_etl_env \
```

---

## Step 6 — Verify Inside the Job

Add this to the top of your PySpark script to confirm the correct Python and
packages are active on executors:

```python
import sys
import pyspark
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("CIS_ETL").getOrCreate()
sc    = spark.sparkContext

def _check_env(_):
    import sys, pyarrow, thrift
    return f"Python: {sys.executable} | pyarrow: {pyarrow.__version__} | thrift: {thrift.__version__}"

result = sc.parallelize([1], 1).map(_check_env).collect()
print(result[0])
```

Expected output on the driver log:

```
Python: ./cis_etl_env/bin/python | pyarrow: 14.0.2 | thrift: 0.16.0
```

---

## Quick Reference — Full Command Sequence

```bash
# 1. Build
python3.10 -m venv cis_etl_env
source cis_etl_env/bin/activate
pip install --upgrade pip
pip install pyarrow thrift thrift-sasl impyla python-dotenv chardet openpyxl
deactivate

# 2. Package
zip -r cis_etl_env.zip cis_etl_env/

# 3. Upload to HDFS
hdfs dfs -put -f cis_etl_env.zip /mrw/cis/spark/venvs/cis_etl_env.zip

# 4. Submit
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --archives hdfs:///mrw/cis/spark/venvs/cis_etl_env.zip#cis_etl_env \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python \
  your_etl_job.py
```

---

## Troubleshooting

### `No module named 'X'` on executors

The package is missing from the venv zip.  
**Fix:** Re-install, re-zip, re-upload.

```bash
source cis_etl_env/bin/activate
pip install missing-package
deactivate
zip -r cis_etl_env.zip cis_etl_env/
hdfs dfs -put -f cis_etl_env.zip /mrw/cis/spark/venvs/cis_etl_env.zip
```

### `Cannot run program "./cis_etl_env/bin/python": Permission denied`

The zip lost execute permissions.  
**Fix:** Use `zip -r` (not a GUI tool). Re-create the zip on Linux.  
Or restore permissions inside the unpacked archive:

```bash
# On the edge node, check:
unzip -l cis_etl_env.zip | grep "bin/python"
# Should show permission 755 or 100755
```

### `PYTHON_VERSION mismatch`

The venv was built with Python 3.11 but workers have Python 3.10.  
**Fix:** Build on a node with the **exact same Python version as the workers**.

```bash
# Check worker Python version
yarn node -list -all   # find a worker hostname
ssh worker-node "python3 --version"
```

### `ModuleNotFoundError: No module named '_ssl'` or `_lzma`

The venv copies the interpreter's shared libraries by reference. On Linux some
stdlib extension modules need system `.so` files.  
**Fix:** Use `venv-pack` (or `conda-pack` for conda envs) which handles shared
library copying correctly:

```bash
pip install venv-pack
venv-pack -o cis_etl_env.tar.gz
# Then use --archives cis_etl_env.tar.gz#cis_etl_env with Spark
```

### Job hangs at `PYSPARK_PYTHON` resolution

Check YARN logs for the app:

```bash
yarn logs -applicationId application_XXXXXXXX_XXXX | grep -i "PYSPARK_PYTHON\|python\|error" | head -40
```

---

## Notes for Cloudera CDP / CML

- On **Cloudera CML**, Spark jobs run via the CML Jobs UI or `cml.run_job()`.
  The `--archives` flag maps to the **File dependencies** field in the job config.
- If **Ranger policies** restrict HDFS paths, ensure the service account running
  `spark-submit` has READ on `/mrw/cis/spark/venvs/`.
- For **Kerberos** clusters, kinit before submitting:
  ```bash
  kinit your_user@YOUR.REALM.COM
  spark-submit ...
  ```
- The venv zip should be **rebuilt whenever `requirements.txt` changes**.
  Tag it with a version: `cis_etl_env_v1.2.zip` to avoid cache confusion.
