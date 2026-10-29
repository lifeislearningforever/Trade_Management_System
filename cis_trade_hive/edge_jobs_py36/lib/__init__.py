"""
edge_jobs_py36.lib -- Django-free support package for the standalone
Python 3.6 edge-node forks of the trade/reference_data management commands.

Importing this package inserts the main cis_trade_hive project root onto
sys.path so the (Django-free) config.environments and
core.notifications.constants modules can be imported directly from the
original tree -- they have zero Django dependency, so there is no need to
duplicate them here. Everything else that touches django.conf.settings,
django.core.cache, django.core.management, or core.notifications.sender is
forked into a sibling module in this package instead.

This is a parallel, independently-maintained fork of the Django commands in
trade/management/commands/ and reference_data/management/commands/, built
because Django 5.2.9 requires Python >=3.10 and this edge node's spark-submit
driver is pinned to Python 3.6. The original files are untouched -- any
future bugfix to shared business logic must be applied to BOTH copies.
"""
import os
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_PACKAGE_ROOT = os.path.dirname(_LIB_DIR)          # edge_jobs_py36/
_PROJECT_ROOT = os.path.dirname(_PACKAGE_ROOT)     # cis_trade_hive/

for _p in (_PROJECT_ROOT, _PACKAGE_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
