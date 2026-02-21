# SSL Certificates for Hive Connection

This folder contains SSL certificates required for Hive JDBC connections.

## Required Files

Copy the following file from your Cloudera edge node:

```bash
# From edge node, copy the truststore:
scp /var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks \
    user@cml-host:/path/to/project/config/certs/
```

## File: cm-auto-global_truststore.jks

This is the Cloudera Manager auto-generated truststore containing SSL certificates
for secure connections to HiveServer2 via ZooKeeper.

**Source location on edge node:**
`/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks`

## Usage

The `HiveBeelineExecutor` class automatically looks for this file in:
1. `/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks` (edge node)
2. `{PROJECT_ROOT}/config/certs/cm-auto-global_truststore.jks` (CML/bundled)
3. Environment variable `HIVE_TRUSTSTORE_PATH`

## Security Note

Do NOT commit the actual .jks file to git. Add it to .gitignore.
The truststore should be deployed separately or mounted as a secret in CML.
