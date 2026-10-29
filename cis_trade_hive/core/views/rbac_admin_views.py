"""
RBAC Admin Views

Superuser-only UI for managing RBAC v2 entities:
  - Users (cis_user_info)
  - Groups (cis_user_group_info)
  - Permissions (cis_permission_info)
  - User → Group assignments (cis_user_group_mapping_info)
  - Group → Permission assignments (cis_group_permission_map)
  - Audit log (cis_audit_log, RBAC entity types)

Access control: requires 'rbac-admin' permission (WRITE).
All views use @require_login; explicit permission check inside each view.
"""

import json
import logging
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings

from core.views.auth_views import require_login
from core.repositories.rbac_admin_repository import rbac_admin_repository
from core.audit.audit_kudu_repository import audit_log_kudu_repository

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _is_rbac_admin(request) -> bool:
    """Return True when user has rbac-admin WRITE permission (or skip-checks mode)."""
    if getattr(settings, 'SKIP_PERMISSION_CHECKS', False):
        return True
    perms = request.session.get('user_permissions', {})
    return perms.get('rbac-admin') == 'WRITE'


def _audit(request, action_type, entity_type, entity_id, entity_name,
           description, old_val=None, new_val=None):
    """Fire-and-forget audit log entry."""
    try:
        audit_log_kudu_repository.log_action(
            user_id=request.session.get('user_id', ''),
            username=request.session.get('user_login', ''),
            action_type=action_type,
            entity_type=entity_type,
            entity_id=str(entity_id),
            entity_name=entity_name,
            action_description=description,
            old_value=old_val,
            new_value=new_val,
            ip_address=request.META.get('REMOTE_ADDR'),
            request_path=request.path,
            request_method=request.method,
        )
    except Exception as e:
        logger.error(f"RBAC audit log error: {e}")


def _forbidden(request):
    return render(request, 'core/rbac/forbidden.html', status=403)


# --------------------------------------------------------------------------- #
# Dashboard / landing
# --------------------------------------------------------------------------- #

@require_login
def rbac_dashboard(request):
    if not _is_rbac_admin(request):
        return _forbidden(request)
    stats = {
        'users': len(rbac_admin_repository.get_all_users()),
        'groups': len(rbac_admin_repository.get_all_groups()),
        'permissions': len(rbac_admin_repository.get_all_permissions()),
    }
    return render(request, 'core/rbac/dashboard.html', {'stats': stats})


# --------------------------------------------------------------------------- #
# USERS
# --------------------------------------------------------------------------- #

@require_login
def user_list(request):
    if not _is_rbac_admin(request):
        return _forbidden(request)
    include_inactive = request.GET.get('include_inactive') == '1'
    users = rbac_admin_repository.get_all_users(include_inactive=include_inactive)
    return render(request, 'core/rbac/user_list.html', {
        'users': users,
        'include_inactive': include_inactive,
    })


@require_login
def user_create(request):
    if not _is_rbac_admin(request):
        return _forbidden(request)

    if request.method == 'POST':
        data = {
            'login': request.POST.get('login', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'name': request.POST.get('name', '').strip(),
            'default_entity': request.POST.get('default_entity', 'UOBS').strip(),
        }
        created_by = request.session.get('user_login', 'system')
        ok, result = rbac_admin_repository.create_user(data, created_by)
        if ok:
            _audit(request, 'CREATE', 'RBAC_USER', result, data['login'],
                   f"Created user {data['login']}", new_val=str(data))
            messages.success(request, f"User '{data['login']}' created.")
            return redirect('core:rbac_user_list')
        else:
            messages.error(request, f"Failed to create user: {result}")

    return render(request, 'core/rbac/user_form.html', {
        'action': 'Create',
        'user': None,
    })


@require_login
def user_edit(request, user_id):
    if not _is_rbac_admin(request):
        return _forbidden(request)

    user = rbac_admin_repository.get_user(user_id)
    if not user:
        messages.error(request, 'User not found.')
        return redirect('core:rbac_user_list')

    if request.method == 'POST':
        data = {
            'login': request.POST.get('login', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'name': request.POST.get('name', '').strip(),
            'default_entity': request.POST.get('default_entity', 'UOBS').strip(),
            'is_active': request.POST.get('is_active') == '1',
        }
        updated_by = request.session.get('user_login', 'system')
        old_val = str({k: user.get(k) for k in ('login', 'email', 'name', 'default_entity', 'is_active')})
        ok = rbac_admin_repository.update_user(user_id, data, updated_by)
        if ok:
            _audit(request, 'UPDATE', 'RBAC_USER', user_id, data['login'],
                   f"Updated user {data['login']}", old_val=old_val, new_val=str(data))
            messages.success(request, f"User '{data['login']}' updated.")
            return redirect('core:rbac_user_list')
        else:
            messages.error(request, 'Failed to update user.')

    return render(request, 'core/rbac/user_form.html', {
        'action': 'Edit',
        'user': user,
    })


@require_login
def user_deactivate(request, user_id):
    if not _is_rbac_admin(request):
        return _forbidden(request)
    if request.method == 'POST':
        user = rbac_admin_repository.get_user(user_id)
        updated_by = request.session.get('user_login', 'system')
        ok = rbac_admin_repository.deactivate_user(user_id, updated_by)
        if ok:
            name = user.get('login', user_id) if user else user_id
            _audit(request, 'DEACTIVATE', 'RBAC_USER', user_id, name,
                   f"Deactivated user {name}")
            messages.success(request, f"User deactivated.")
        else:
            messages.error(request, 'Failed to deactivate user.')
    return redirect('core:rbac_user_list')


# --------------------------------------------------------------------------- #
# USER → GROUP assignment
# --------------------------------------------------------------------------- #

@require_login
def user_groups(request, user_id):
    """View/edit which groups a user belongs to (multi-select)."""
    if not _is_rbac_admin(request):
        return _forbidden(request)

    user = rbac_admin_repository.get_user(user_id)
    if not user:
        messages.error(request, 'User not found.')
        return redirect('core:rbac_user_list')

    all_groups = rbac_admin_repository.get_all_groups()
    current_mappings = rbac_admin_repository.get_user_group_mappings(user_id)
    current_group_names = {m['group_name'] for m in current_mappings}

    if request.method == 'POST':
        selected_groups = request.POST.getlist('group_names')
        entity = request.POST.get('entity', user.get('default_entity', 'UOBS'))
        updated_by = request.session.get('user_login', 'system')
        user_login = user.get('login', '')
        old_val = str(sorted(current_group_names))
        ok = rbac_admin_repository.save_user_groups(
            user_id, user_login, selected_groups, entity, updated_by
        )
        if ok:
            _audit(request, 'UPDATE', 'RBAC_USER_GROUP', user_id, user_login,
                   f"Updated groups for {user_login}",
                   old_val=old_val, new_val=str(sorted(selected_groups)))
            messages.success(request, f"Group assignments saved for '{user_login}'.")
            return redirect('core:rbac_user_list')
        else:
            messages.error(request, 'Failed to save group assignments.')

    return render(request, 'core/rbac/user_groups.html', {
        'user': user,
        'all_groups': all_groups,
        'current_group_names': current_group_names,
    })


# --------------------------------------------------------------------------- #
# GROUPS
# --------------------------------------------------------------------------- #

@require_login
def group_list(request):
    if not _is_rbac_admin(request):
        return _forbidden(request)
    include_inactive = request.GET.get('include_inactive') == '1'
    groups = rbac_admin_repository.get_all_groups(include_inactive=include_inactive)
    return render(request, 'core/rbac/group_list.html', {
        'groups': groups,
        'include_inactive': include_inactive,
    })


@require_login
def group_create(request):
    if not _is_rbac_admin(request):
        return _forbidden(request)

    if request.method == 'POST':
        data = {
            'group_name': request.POST.get('group_name', '').strip(),
            'description': request.POST.get('description', '').strip(),
            'entity': request.POST.get('entity', 'UOBS').strip(),
        }
        created_by = request.session.get('user_login', 'system')
        ok, result = rbac_admin_repository.create_group(data, created_by)
        if ok:
            _audit(request, 'CREATE', 'RBAC_GROUP', result, data['group_name'],
                   f"Created group {data['group_name']}", new_val=str(data))
            messages.success(request, f"Group '{data['group_name']}' created.")
            return redirect('core:rbac_group_list')
        else:
            messages.error(request, f"Failed to create group: {result}")

    return render(request, 'core/rbac/group_form.html', {
        'action': 'Create',
        'group': None,
    })


@require_login
def group_edit(request, group_id):
    if not _is_rbac_admin(request):
        return _forbidden(request)

    group = rbac_admin_repository.get_group(group_id)
    if not group:
        messages.error(request, 'Group not found.')
        return redirect('core:rbac_group_list')

    if request.method == 'POST':
        data = {
            'group_name': request.POST.get('group_name', '').strip(),
            'description': request.POST.get('description', '').strip(),
            'entity': request.POST.get('entity', 'UOBS').strip(),
            'is_active': request.POST.get('is_active') == '1',
        }
        updated_by = request.session.get('user_login', 'system')
        old_val = str({k: group.get(k) for k in ('group_name', 'description', 'entity', 'is_active')})
        ok = rbac_admin_repository.update_group(group_id, data, updated_by)
        if ok:
            _audit(request, 'UPDATE', 'RBAC_GROUP', group_id, data['group_name'],
                   f"Updated group {data['group_name']}", old_val=old_val, new_val=str(data))
            messages.success(request, f"Group '{data['group_name']}' updated.")
            return redirect('core:rbac_group_list')
        else:
            messages.error(request, 'Failed to update group.')

    return render(request, 'core/rbac/group_form.html', {
        'action': 'Edit',
        'group': group,
    })


# --------------------------------------------------------------------------- #
# GROUP → PERMISSION assignment
# --------------------------------------------------------------------------- #

@require_login
def group_permissions(request, group_id):
    """View/edit which permissions a group has (permission matrix)."""
    if not _is_rbac_admin(request):
        return _forbidden(request)

    group = rbac_admin_repository.get_group(group_id)
    if not group:
        messages.error(request, 'Group not found.')
        return redirect('core:rbac_group_list')

    all_permissions = rbac_admin_repository.get_all_permissions()
    current_mappings = rbac_admin_repository.get_group_permission_mappings(group.get('group_name', ''))
    # Build dict: permission_name → mode
    current_perm_map = {m['permission_name']: m['mode'] for m in current_mappings}

    if request.method == 'POST':
        entity = request.POST.get('entity', group.get('entity', 'UOBS'))
        updated_by = request.session.get('user_login', 'system')
        group_name = group.get('group_name', '')

        # Collect submitted permissions
        permissions = []
        for perm in all_permissions:
            pname = perm['permission_name']
            mode = request.POST.get(f'perm_{pname}', '')
            if mode in ('READ', 'WRITE'):
                permissions.append({'permission_name': pname, 'mode': mode})

        old_val = str(current_perm_map)
        new_perm_map = {p['permission_name']: p['mode'] for p in permissions}
        ok = rbac_admin_repository.save_group_permissions(
            group_name, permissions, entity, updated_by
        )
        if ok:
            _audit(request, 'UPDATE', 'RBAC_GROUP_PERMISSION', group_id, group_name,
                   f"Updated permissions for {group_name}",
                   old_val=old_val, new_val=str(new_perm_map))
            messages.success(request, f"Permissions saved for group '{group_name}'.")
            return redirect('core:rbac_group_list')
        else:
            messages.error(request, 'Failed to save permissions.')

    return render(request, 'core/rbac/group_permissions.html', {
        'group': group,
        'all_permissions': all_permissions,
        'current_perm_map': current_perm_map,
        'current_perm_map_json': json.dumps(current_perm_map),
    })


# --------------------------------------------------------------------------- #
# PERMISSIONS
# --------------------------------------------------------------------------- #

@require_login
def permission_list(request):
    if not _is_rbac_admin(request):
        return _forbidden(request)
    permissions = rbac_admin_repository.get_all_permissions()
    return render(request, 'core/rbac/permission_list.html', {
        'permissions': permissions,
    })


@require_login
def permission_create(request):
    if not _is_rbac_admin(request):
        return _forbidden(request)

    if request.method == 'POST':
        data = {
            'permission_name': request.POST.get('permission_name', '').strip(),
            'entity': request.POST.get('entity', 'UOBS').strip(),
            'description': request.POST.get('description', '').strip(),
        }
        created_by = request.session.get('user_login', 'system')
        ok, result = rbac_admin_repository.create_permission(data, created_by)
        if ok:
            _audit(request, 'CREATE', 'RBAC_PERMISSION', result, data['permission_name'],
                   f"Created permission {data['permission_name']}", new_val=str(data))
            messages.success(request, f"Permission '{data['permission_name']}' created.")
            return redirect('core:rbac_permission_list')
        else:
            messages.error(request, f"Failed to create permission: {result}")

    return render(request, 'core/rbac/permission_form.html', {
        'permission': None,
    })


# --------------------------------------------------------------------------- #
# AUDIT LOG
# --------------------------------------------------------------------------- #

@require_login
def rbac_audit(request):
    if not _is_rbac_admin(request):
        return _forbidden(request)
    limit = int(request.GET.get('limit', 200))
    entries = rbac_admin_repository.get_rbac_audit(limit=limit)
    return render(request, 'core/rbac/audit.html', {
        'entries': entries,
        'limit': limit,
    })
