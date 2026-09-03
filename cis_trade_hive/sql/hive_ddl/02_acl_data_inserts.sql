-- ================================================================
-- ACL Data INSERT Statements
-- Generated from ACL_TABLES.xlsx
-- Database: cis
-- ================================================================

USE cis;

-- ================================================================
-- Table: cis_user_group (1 row)
-- ================================================================
INSERT INTO cis_user_group VALUES (
    1,
    'CIS-DEV',
    'UOBS',
    NULL,
    false,
    CAST('2025-12-09 18:46:10.376349000' AS TIMESTAMP),
    'CIS_BATCH'
);

-- ================================================================
-- Table: cis_user (3 rows)
-- ================================================================
INSERT INTO cis_user VALUES (
    1,
    'TMP4UG',
    'SANDEEP P',
    'UOBS',
    'Sandeep.POTPELWAR@uobgroup.com',
    'NTSGPDOM',
    1,
    false,
    true,
    CAST('2025-12-09 18:35:28.336675000' AS TIMESTAMP),
    CAST('2025-12-09 18:35:28.336675000' AS TIMESTAMP),
    'CIS_BATCH',
    CAST('2025-12-09 18:35:28.336675000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_user VALUES (
    2,
    'TMP3RC',
    'PRAKASH HOSALLI',
    'UOBS',
    'prakash.hosalli1@uobgroup.com',
    'NTSGPDOM',
    1,
    false,
    true,
    CAST('2025-12-15 16:46:34.093620000' AS TIMESTAMP),
    CAST('2025-12-15 16:46:34.093620000' AS TIMESTAMP),
    'CIS_BATCH',
    CAST('2025-12-15 16:46:34.093620000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_user VALUES (
    3,
    'TMP3OD',
    'RajeshNair GOPIKUTTAN',
    'UOBS',
    'RajeshNair.GOPIKUTTAN@uobgroup.com',
    'NTSGPDOM',
    1,
    false,
    true,
    CAST('2025-12-18 11:25:23.849687000' AS TIMESTAMP),
    CAST('2025-12-18 11:25:23.849687000' AS TIMESTAMP),
    'CIS_BATCH',
    CAST('2025-12-18 11:25:23.849687000' AS TIMESTAMP),
    'CIS_BATCH'
);

-- ================================================================
-- Table: cis_permission (7 rows)
-- ================================================================
INSERT INTO cis_permission VALUES (
    2,
    'cis-report',
    NULL,
    false,
    CAST('2025-12-18 10:05:30.170031000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_permission VALUES (
    3,
    'cis-trade',
    NULL,
    false,
    CAST('2025-12-18 10:05:30.170031000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_permission VALUES (
    5,
    'cis-currency',
    NULL,
    false,
    CAST('2025-12-18 10:05:30.170031000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_permission VALUES (
    6,
    'cis-audit',
    NULL,
    false,
    CAST('2025-12-18 10:05:30.170031000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_permission VALUES (
    7,
    'cis-udf',
    NULL,
    false,
    CAST('2025-12-18 10:05:30.170031000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_permission VALUES (
    1,
    'cis-udflist',
    NULL,
    false,
    CAST('2025-12-18 10:05:30.170031000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_permission VALUES (
    4,
    'cis-portfolio',
    NULL,
    false,
    CAST('2025-12-18 10:05:30.170031000' AS TIMESTAMP),
    'CIS_BATCH'
);

-- ================================================================
-- Table: cis_group_permissions (30 rows)
-- ================================================================
INSERT INTO cis_group_permissions VALUES (
    8,
    1,
    'cis-report',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    17,
    2,
    'cis-report',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    21,
    2,
    'cis-audit',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    4,
    1,
    'cis-portfolio',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    11,
    1,
    'cis-currency',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    14,
    1,
    'cis-udf-view',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    1,
    1,
    'cis-udflist',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    10,
    1,
    'cis-portfolio',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    22,
    2,
    'cis-udflist',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    9,
    1,
    'cis-trade',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    27,
    2,
    'cis-audit',
    'READ_WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    7,
    1,
    'cis-udflist',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    15,
    1,
    'cis-udf-delete',
    'READ_',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    19,
    2,
    'cis-portfolio',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    23,
    2,
    'cis-report',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    25,
    2,
    'cis-portfolio',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    13,
    1,
    'cis-udf-create',
    'READ_WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    29,
    2,
    'cis-udf-view',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    30,
    2,
    'cis-udf-delete',
    'READ_',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    2,
    1,
    'cis-report',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    3,
    1,
    'cis-trade',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    16,
    2,
    'cis-udflist',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    20,
    2,
    'cis-currency',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    24,
    2,
    'cis-trade',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    26,
    2,
    'cis-currency',
    'WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    5,
    1,
    'cis-currency',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    6,
    1,
    'cis-audit',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);

✓ Successfully generated INSERT statements for all ACL tables
  Output written to stdout

INSERT INTO cis_group_permissions VALUES (
    12,
    1,
    'cis-audit',
    'READ_WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    18,
    2,
    'cis-trade',
    'READ',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);
INSERT INTO cis_group_permissions VALUES (
    28,
    2,
    'cis-udf-create',
    'READ_WRITE',
    false,
    CAST('2025-12-15 17:00:17.277941000' AS TIMESTAMP),
    'CIS_BATCH'
);

-- ================================================================
-- End of INSERT statements
-- Total: 41 rows (1 + 3 + 7 + 30)
-- ================================================================
