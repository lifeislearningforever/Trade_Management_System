# udf/services/udf_service.py — Kudu-only UDF service (no Django ORM)
from typing import List, Dict, Optional, Any, Tuple
import os
from django.core.exceptions import ValidationError
from core.services.acl_service import acl_service
from core.repositories.impala_connection import ImpalaConnectionManager
from core.repositories.udf_kudu_repository import UDFOptionRepository, UDFValueRepository

SCOPE_DEFAULT = os.environ.get('UDF_OPTIONS_SCOPE', 'GLOBAL').upper()


def _udf_id(scope: str, field_name: str) -> str:
    # Deterministic ID used in all cis_udf_* tables
    return f"ABS(FNV_HASH(LOWER('{scope.lower()}')||':'||LOWER('{field_name.lower()}')))"


class UDFService:
    _conn = ImpalaConnectionManager()
    _opt = UDFOptionRepository(_conn)
    _val = UDFValueRepository(_conn)

    # ------- Definitions (Kudu) -------
    @staticmethod
    def list_udfs(entity_type: Optional[str] = None,
                  active_only: Optional[bool] = True,
                  search: Optional[str] = None) -> List[Dict[str, Any]]:
        where = []
        if entity_type:
            where.append(f"entity_type = '{entity_type.upper()}'")
        if active_only is True:
            where.append("is_active = TRUE")
        elif active_only is False:
            where.append("is_active = FALSE")

        sql = (
            "SELECT udf_id, field_name, label, description, field_type, entity_type, "
            "is_required, is_unique, display_order, group_name, default_string, is_active, "
            "created_by, created_at, updated_by, updated_at "
            "FROM gmp_cis.cis_udf_definition"
        )
        extra = ["field_name IS NOT NULL", "field_name <> ''"]
        combined = where + extra
        sql += " WHERE " + " AND ".join(combined) if combined else ""
        sql += " ORDER BY entity_type, display_order, field_name"

        with UDFService._conn.get_cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        cols = ['udf_id', 'field_name', 'label', 'description', 'field_type', 'entity_type',
                'is_required', 'is_unique', 'display_order', 'group_name', 'default_string',
                'is_active', 'created_by', 'created_at', 'updated_by', 'updated_at']
        defs = [{c: r[i] for i, c in enumerate(cols)} for r in rows]

        if search:
            s = search.lower()
            defs = [d for d in defs if s in (d['field_name'] or '').lower()
                    or s in (d['label'] or '').lower()
                    or s in (d['description'] or '').lower()]
        return defs

    @staticmethod
    def create_udf(request, data: Dict[str, Any]) -> Dict[str, Any]:
        # Validate input
        for f in ['field_name', 'label', 'field_type', 'entity_type']:
            if not data.get(f):
                raise ValidationError(f"{f} is required")

        field_name = data['field_name']
        label = data['label']
        field_type = data['field_type']
        entity_type = data['entity_type'].upper()
        login = acl_service.resolve_login(request,
                                          getattr(getattr(request, 'user', None), 'username', None)) or 'system'

        # Upsert definition
        sql = (
            "UPSERT INTO gmp_cis.cis_udf_definition "
            "(udf_id, field_name, label, description, field_type, entity_type, "
            " is_required, is_unique, display_order, group_name, default_string, is_active, "
            " created_by, created_at, updated_by, updated_at) "
            f"VALUES ({_udf_id(SCOPE_DEFAULT, field_name)}, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP(), ?, CURRENT_TIMESTAMP())"
        )
        params = [
            field_name, label, data.get('description'),
            field_type, entity_type,
            bool(data.get('is_required')), bool(data.get('is_unique')),
            int(data.get('display_order') or 0), data.get('group_name'),
            data.get('default_value'), bool(data.get('is_active', True)),
            login, login
        ]
        with UDFService._conn.get_cursor() as cur:
            cur.execute(sql, params)

        # Seed options if dropdown/multiselect
        if field_type in ('DROPDOWN', 'MULTI_SELECT'):
            opts = [(o, i) for i, o in enumerate(data.get('dropdown_options') or [])]
            if opts:
                UDFService._opt.bulk_upsert_options(SCOPE_DEFAULT, field_name, opts, actor=login)

        return {'field_name': field_name, 'label': label, 'field_type': field_type, 'entity_type': entity_type}

    @staticmethod
    def update_udf(request, field_name: str, entity_type: str, data: Dict[str, Any]) -> None:
        login = acl_service.resolve_login(request,
                                          getattr(getattr(request, 'user', None), 'username', None)) or 'system'
        sql = (
            "UPSERT INTO gmp_cis.cis_udf_definition "
            "(udf_id, field_name, label, description, field_type, entity_type, "
            " is_required, is_unique, display_order, group_name, default_string, is_active, "
            " created_by, created_at, updated_by, updated_at) "
            f"VALUES ({_udf_id(SCOPE_DEFAULT, field_name)}, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP(), ?, CURRENT_TIMESTAMP())"
        )
        params = [
            field_name, data.get('label') or '',
            data.get('description'),
                        data.get('field_type') or 'TEXT',
            entity_type.upper(),
            bool(data.get('is_required')), bool(data.get('is_unique')),
            int(data.get('display_order') or 0), data.get('group_name'),
            data.get('default_value'), bool(data.get('is_active', True)),
            login, login
        ]
        with UDFService._conn.get_cursor() as cur:
            cur.execute(sql, params)

        # Update options if provided
        ft = data.get('field_type')
        if ft in ('DROPDOWN', 'MULTI_SELECT') and data.get('dropdown_options'):
            opts = [(o, i) for i, o in enumerate(data['dropdown_options'])]
            UDFService._opt.bulk_upsert_options(SCOPE_DEFAULT, field_name, opts, actor=login)

    @staticmethod
    def deactivate_udf(request, field_name: str) -> None:
        login = acl_service.resolve_login(request,
                                          getattr(getattr(request, 'user', None), 'username', None)) or 'system'
        sql = (
            "UPDATE gmp_cis.cis_udf_definition "
            f"SET is_active = FALSE, updated_by = ?, updated_at = CURRENT_TIMESTAMP() "
            f"WHERE udf_id = {_udf_id(SCOPE_DEFAULT, field_name)}"
        )
        with UDFService._conn.get_cursor() as cur:
            cur.execute(sql, [login])

    @staticmethod
    def get_udf_options(field_name: str) -> List[Tuple[str, int]]:
        return UDFService._opt.list_options_by_scope(SCOPE_DEFAULT, field_name)

    # ------- Values (Kudu) -------
    @staticmethod
    def set_entity_udf_values(request, entity_type: str, entity_id: int, values: Dict[str, Any]) -> None:
        login = acl_service.resolve_login(request,
                                          getattr(getattr(request, 'user', None), 'username', None)) or 'system'

        # Validate dropdowns against Kudu options
        defs = UDFService.list_udfs(entity_type=entity_type, active_only=True)
        types = {d['field_name']: d['field_type'] for d in defs}

        for field_name, value in values.items():
            t = types.get(field_name, 'TEXT')
            if t == 'DROPDOWN':
                opts = [o for o, _ in UDFService._opt.list_options_by_scope(SCOPE_DEFAULT, field_name)]
                if opts and value not in opts:
                    raise ValidationError(f"{field_name} must be one of: {', '.join(opts)}")

            typed = {}
            if t in ('TEXT', 'DROPDOWN'):
                typed['value_string'] = str(value) if value is not None else None
            elif t in ('NUMBER', 'CURRENCY', 'PERCENTAGE'):
                typed['value_decimal'] = value
            elif t == 'BOOLEAN':
                typed['value_bool'] = bool(value) if value is not None else None
            elif t in ('DATE', 'DATETIME'):
                typed['value_datetime'] = value

            UDFService._val_repo.upsert_value(entity_type.upper(), int(entity_id),
                                              field_name, SCOPE_DEFAULT, typed, login)

    @staticmethod
    def get_entity_udf_values(entity_type: str, entity_id: int) -> Dict[str, Any]:
        defs = UDFService.list_udfs(entity_type=entity_type, active_only=True)
        result = {}
        for d in defs:
            # read back current value
            # (use direct repository if you have a getter;
            # here we fallback to default_string when no value row exists)
            result[d['field_name']] = d.get('default_string')
        return result

    @staticmethod
    def bulk_upsert_options(request, scope: Optional[str], rows: List[Dict[str, str]]) -> int:
        login = acl_service.resolve_login(request,
                                          getattr(getattr(request, 'user', None), 'username', None)) or 'system'
        scope_eff = (scope or SCOPE_DEFAULT).upper()
        count = 0
        for r in rows:
            field = (r.get('field_name') or '').strip()
            option = (r.get('option_value') or '').strip()
            order = int(r.get('display_order', '0'))
            if field and option:
                UDFService._opt.bulk_upsert_options(scope_eff, field, [(option, order)], actor=login)
                count += 1
        return count
