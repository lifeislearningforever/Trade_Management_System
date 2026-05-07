"""
Management command to verify RBAC V2 tables have users and permission mappings.

Read-only — never creates or modifies any data.
Prints a health report showing:
  - User count and active user list (cis_user_info)
  - Group count and group list (cis_user_group_info)
  - Permission count (cis_permission_info)
  - User-group mapping count (cis_user_group_mapping_info)
  - Group-permission mapping count (cis_group_permission_map)
  - Sample permission check for each active user

Usage:
    python manage.py verify_rbac
    python manage.py verify_rbac --user TMP3RC
    python manage.py verify_rbac --group SG-TRADER
"""

from django.core.management.base import BaseCommand
from core.repositories.impala_connection import impala_manager

DB = 'gmp_cis'


class Command(BaseCommand):
    help = 'Verify RBAC V2 tables — read-only health check, no data created'

    def add_arguments(self, parser):
        parser.add_argument('--user', help='Show permissions for a specific login')
        parser.add_argument('--group', help='Show permissions for a specific group')

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('RBAC V2 Health Check (read-only)'))
        self.stdout.write('=' * 60)

        ok = True

        # ── 1. Users ──────────────────────────────────────────────────
        try:
            rows = impala_manager.execute_query(
                f"SELECT login, name, default_entity, is_active, is_deleted "
                f"FROM {DB}.cis_user_info ORDER BY login",
                database=DB
            ) or []
            active = [r for r in rows if r.get('is_active') and not r.get('is_deleted')]
            self.stdout.write(f'\n[cis_user_info]  total={len(rows)}  active={len(active)}')
            for r in active:
                self.stdout.write(f"  {r['login']:<20} {r['name']:<30} {r.get('default_entity','')}")
            if not active:
                self.stdout.write(self.style.ERROR('  !! No active users found'))
                ok = False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  !! cis_user_info query failed: {e}'))
            ok = False

        # ── 2. Groups ─────────────────────────────────────────────────
        try:
            rows = impala_manager.execute_query(
                f"SELECT group_name, entity, is_active, is_deleted "
                f"FROM {DB}.cis_user_group_info ORDER BY group_name",
                database=DB
            ) or []
            active = [r for r in rows if r.get('is_active') and not r.get('is_deleted')]
            self.stdout.write(f'\n[cis_user_group_info]  total={len(rows)}  active={len(active)}')
            for r in active:
                self.stdout.write(f"  {r['group_name']:<30} {r.get('entity','')}")
            if not active:
                self.stdout.write(self.style.ERROR('  !! No active groups found'))
                ok = False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  !! cis_user_group_info query failed: {e}'))
            ok = False

        # ── 3. Permissions ────────────────────────────────────────────
        try:
            rows = impala_manager.execute_query(
                f"SELECT COUNT(*) AS cnt FROM {DB}.cis_permission_info "
                f"WHERE is_active = true AND is_deleted = false",
                database=DB
            ) or []
            cnt = rows[0].get('cnt', 0) if rows else 0
            self.stdout.write(f'\n[cis_permission_info]  active={cnt}')
            if not cnt:
                self.stdout.write(self.style.WARNING('  !! No active permissions defined'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  !! cis_permission_info query failed: {e}'))
            ok = False

        # ── 4. User-Group mappings ─────────────────────────────────────
        try:
            rows = impala_manager.execute_query(
                f"SELECT u.login, ugm.group_name, ugm.entity "
                f"FROM {DB}.cis_user_group_mapping_info ugm "
                f"JOIN {DB}.cis_user_info u ON ugm.user_id = u.user_id "
                f"WHERE ugm.is_active = true AND ugm.is_deleted = false "
                f"  AND u.is_active = true AND u.is_deleted = false "
                f"ORDER BY u.login, ugm.group_name",
                database=DB
            ) or []
            self.stdout.write(f'\n[cis_user_group_mapping_info]  active mappings={len(rows)}')
            for r in rows:
                self.stdout.write(f"  {r['login']:<20} → {r['group_name']}")
            if not rows:
                self.stdout.write(self.style.ERROR('  !! No user-group mappings found — users cannot log in'))
                ok = False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  !! cis_user_group_mapping_info query failed: {e}'))
            ok = False

        # ── 5. Group-Permission mappings ──────────────────────────────
        try:
            rows = impala_manager.execute_query(
                f"SELECT group_name, COUNT(*) AS cnt "
                f"FROM {DB}.cis_group_permission_map "
                f"WHERE is_active = true AND is_deleted = false "
                f"GROUP BY group_name ORDER BY group_name",
                database=DB
            ) or []
            total = sum(r.get('cnt', 0) for r in rows)
            self.stdout.write(f'\n[cis_group_permission_map]  total active={total}')
            for r in rows:
                self.stdout.write(f"  {r['group_name']:<30} {r['cnt']} permissions")
            if not rows:
                self.stdout.write(self.style.ERROR('  !! No group-permission mappings — all users will have no access'))
                ok = False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  !! cis_group_permission_map query failed: {e}'))
            ok = False

        # ── 6. Optional: filter by --user ─────────────────────────────
        specific_user = options.get('user')
        if specific_user:
            self.stdout.write(f'\n[Permissions for user: {specific_user}]')
            try:
                rows = impala_manager.execute_query(
                    f"SELECT gpm.permission_name, gpm.mode, ugm.group_name "
                    f"FROM {DB}.cis_user_info u "
                    f"JOIN {DB}.cis_user_group_mapping_info ugm ON u.user_id = ugm.user_id "
                    f"JOIN {DB}.cis_group_permission_map gpm ON ugm.group_name = gpm.group_name "
                    f"WHERE u.login = '{specific_user}' "
                    f"  AND u.is_active = true AND u.is_deleted = false "
                    f"  AND ugm.is_active = true AND ugm.is_deleted = false "
                    f"  AND gpm.is_active = true AND gpm.is_deleted = false "
                    f"ORDER BY ugm.group_name, gpm.permission_name",
                    database=DB
                ) or []
                if rows:
                    for r in rows:
                        self.stdout.write(f"  [{r['group_name']}] {r['permission_name']:<35} {r.get('mode','')}")
                else:
                    self.stdout.write(self.style.WARNING(f'  No permissions found for {specific_user}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  !! Query failed: {e}'))

        # ── 7. Optional: filter by --group ────────────────────────────
        specific_group = options.get('group')
        if specific_group:
            self.stdout.write(f'\n[Permissions for group: {specific_group}]')
            try:
                rows = impala_manager.execute_query(
                    f"SELECT permission_name, mode FROM {DB}.cis_group_permission_map "
                    f"WHERE group_name = '{specific_group}' "
                    f"  AND is_active = true AND is_deleted = false "
                    f"ORDER BY permission_name",
                    database=DB
                ) or []
                if rows:
                    for r in rows:
                        self.stdout.write(f"  {r['permission_name']:<35} {r.get('mode','')}")
                else:
                    self.stdout.write(self.style.WARNING(f'  No permissions found for group {specific_group}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  !! Query failed: {e}'))

        # ── Summary ───────────────────────────────────────────────────
        self.stdout.write('\n' + '=' * 60)
        if ok:
            self.stdout.write(self.style.SUCCESS('RBAC V2 tables OK — users and permissions present'))
        else:
            self.stdout.write(self.style.ERROR('RBAC V2 check FAILED — see errors above'))
        self.stdout.write('=' * 60)
