-- cis_notification — persistent notification store
-- Used as cross-worker fallback when InMemoryChannelLayer cannot deliver
-- WebSocket messages across Gunicorn processes (no Redis configured).
-- The JS client polls /api/notifications/poll/ every 15 s.

CREATE TABLE IF NOT EXISTS gmp_cis.cis_notification (
    notif_id        STRING NOT NULL,
    username        STRING NOT NULL,
    event_type      STRING,
    severity        STRING,
    title           STRING,
    message         STRING,
    payload_json    STRING,
    is_read         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP,
    PRIMARY KEY (notif_id)
)
PARTITION BY HASH(notif_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_servers' = '1');
