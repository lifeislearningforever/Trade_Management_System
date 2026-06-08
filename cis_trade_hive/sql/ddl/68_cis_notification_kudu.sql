-- ============================================================================
-- DDL 68: cis_notification — Kudu table for persistent notification store
--
-- Used by core/notifications/kudu_store.py to survive Gunicorn worker
-- boundaries (InMemoryChannelLayer is per-process, not shared).
-- JS client polls /api/notifications/poll/ every 5s as WebSocket fallback.
--
-- Primary key: notif_id (UUID string)
-- Kudu: UPSERT for writes, no UPDATE support.
-- ============================================================================

USE gmp_cis;

CREATE TABLE IF NOT EXISTS gmp_cis.cis_notification (
    notif_id        STRING,
    username        STRING,
    event_type      STRING,
    severity        STRING,
    title           STRING,
    message         STRING,
    payload_json    STRING,
    is_read         BOOLEAN,
    created_at      STRING,
    PRIMARY KEY (notif_id)
)
PARTITION BY HASH(notif_id) PARTITIONS 4
STORED AS KUDU;

-- Verify
DESCRIBE gmp_cis.cis_notification;
