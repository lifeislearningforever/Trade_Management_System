"""
CML glibc Test Package
======================

This package contains code to replicate and solve the glibc/SASL connectivity
issue in CML Docker containers.

The Problem:
- CML containers have glibc version mismatch with Cloudera's SASL libraries
- Direct PyHive/impyla connections fail with "GLIBC_2.29 not found"

The Solution:
- Use REST Proxy (app_v2.py) on edge node
- Communicate via HTTP instead of native Hive protocol

Usage:
    from cml_glibc_test.hybrid_connection import HybridConnectionManager, CMLConfig

    config = CMLConfig(rest_proxy_url="http://edge-node:5000")
    manager = HybridConnectionManager(config)

    rows = manager.execute_query("SELECT * FROM my_table")
"""

from .hybrid_connection import (
    HybridConnectionManager,
    CMLConfig,
    RestProxyClient,
    HiveConnectionError,
    GlibcCompatibilityError,
    SASlAuthenticationError,
    RestProxyError,
    attempt_direct_pyhive_connection,
    attempt_direct_impyla_connection,
    execute_query,
    execute_write,
    insert,
    update,
    delete,
    get_manager
)

__all__ = [
    'HybridConnectionManager',
    'CMLConfig',
    'RestProxyClient',
    'HiveConnectionError',
    'GlibcCompatibilityError',
    'SASlAuthenticationError',
    'RestProxyError',
    'attempt_direct_pyhive_connection',
    'attempt_direct_impyla_connection',
    'execute_query',
    'execute_write',
    'insert',
    'update',
    'delete',
    'get_manager'
]

__version__ = '1.0.0'
