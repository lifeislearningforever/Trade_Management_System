"""
Audit System Usage Examples

This file demonstrates various ways to use the audit logging system.
"""

from .audit_models import AuditEntry, ActionType, ActionCategory, EntityType, AuditStatus
from .audit_context import AuditContext, audit_action, audit_change
from .audit_logger import get_audit_logger


# =============================================================================
# Example 1: Using the Decorator (Recommended for Functions)
# =============================================================================

@audit_action(
    ActionType.CREATE,
    ActionCategory.PORTFOLIO,
    "Create new portfolio",
    entity_type=EntityType.PORTFOLIO
)
def create_portfolio_example(request, name, currency, manager):
    """
    Example: Create a portfolio with automatic audit logging.

    The decorator automatically captures:
    - Username from request
    - Function name and module
    - Execution time
    - Success/failure status
    - Errors if any occur
    """
    portfolio_data = {
        'name': name,
        'currency': currency,
        'manager': manager,
        'status': 'Active'
    }

    # Simulate creating portfolio
    portfolio_id = "PORT-12345"  # In real app, this would come from DB

    # Return dict with 'id' key - decorator will capture it
    return {
        'id': portfolio_id,
        'name': name,
        'status': 'created'
    }


# =============================================================================
# Example 2: Using Context Manager (For Complex Operations)
# =============================================================================

def update_portfolio_status_example(request, portfolio_id, new_status):
    """
    Example: Update portfolio status with detailed audit logging.

    Context manager allows:
    - Setting entity information during execution
    - Adding custom metadata
    - Tracking duration automatically
    """
    with AuditContext(
        action_type=ActionType.UPDATE,
        action_category=ActionCategory.PORTFOLIO,
        username=request.user.username,
        action_description=f"Update portfolio {portfolio_id} status to {new_status}",
        entity_type=EntityType.PORTFOLIO,
        entity_id=str(portfolio_id)
    ) as audit_ctx:
        # Simulate fetching portfolio
        portfolio = {
            'id': portfolio_id,
            'name': 'Global Equity Fund',
            'status': 'Active'
        }

        # Set entity name in context
        audit_ctx.set_entity(
            EntityType.PORTFOLIO,
            str(portfolio_id),
            portfolio['name']
        )

        # Add metadata about the change
        audit_ctx.add_metadata('old_status', portfolio['status'])
        audit_ctx.add_metadata('new_status', new_status)
        audit_ctx.add_metadata('changed_by_role', 'Portfolio Manager')

        # Perform the update
        old_status = portfolio['status']
        portfolio['status'] = new_status

        # If an exception occurs here, it will be captured in audit log
        return portfolio


# =============================================================================
# Example 3: Tracking Field-Level Changes
# =============================================================================

def update_portfolio_manager_example(request, portfolio_id, new_manager):
    """
    Example: Track field-level changes with before/after values.

    The audit_change context manager specifically tracks:
    - Field name
    - Old value
    - New value
    - Entity being changed
    """
    # Simulate fetching portfolio
    portfolio = {
        'id': portfolio_id,
        'name': 'Asia Pacific Fund',
        'manager': 'John Smith'
    }

    old_manager = portfolio['manager']

    with audit_change(
        username=request.user.username,
        entity_type=EntityType.PORTFOLIO,
        entity_id=str(portfolio_id),
        field_name='manager',
        old_value=old_manager,
        new_value=new_manager,
        entity_name=portfolio['name']
    ):
        # Make the change
        portfolio['manager'] = new_manager

        # Simulate saving to database
        # portfolio.save()

    return portfolio


# =============================================================================
# Example 4: Manual Audit Entry (For Custom Scenarios)
# =============================================================================

def calculate_portfolio_valuation_example(request, portfolio_id):
    """
    Example: Create manual audit entry for custom actions.

    Use manual entries when:
    - Action doesn't fit decorator/context manager pattern
    - Need complete control over audit data
    - Logging external system interactions
    """
    from datetime import datetime
    import time

    start_time = time.time()

    # Simulate calculation
    valuation = 10_500_000.75
    currency = 'USD'

    # Calculate duration
    duration_ms = int((time.time() - start_time) * 1000)

    # Create detailed audit entry
    audit_entry = AuditEntry(
        action_type=ActionType.CALCULATE,
        action_category=ActionCategory.PORTFOLIO,
        username=request.user.username,
        user_id=str(request.user.id),
        user_email=request.user.email,
        action_description="Calculate portfolio market valuation",
        entity_type=EntityType.PORTFOLIO,
        entity_id=str(portfolio_id),
        entity_name="Global Equity Fund",
        status=AuditStatus.SUCCESS,
        duration_ms=duration_ms,
        metadata={
            'valuation_date': datetime.now().isoformat(),
            'total_value': valuation,
            'currency': currency,
            'calculation_method': 'Mark-to-Market',
            'price_source': 'Bloomberg'
        },
        tags=['valuation', 'calculation', 'scheduled']
    )

    # Log the audit entry
    audit_logger = get_audit_logger()
    audit_logger.log(audit_entry)

    return {
        'portfolio_id': portfolio_id,
        'valuation': valuation,
        'currency': currency
    }


# =============================================================================
# Example 5: Batch Audit Logging (For Bulk Operations)
# =============================================================================

def import_portfolios_from_file_example(request, file_path):
    """
    Example: Import multiple portfolios with batch audit logging.

    Batch logging is more efficient when:
    - Importing bulk data
    - Processing multiple entities
    - Running scheduled jobs
    """
    audit_logger = get_audit_logger()
    audit_entries = []

    # Simulate reading CSV file
    portfolios_data = [
        {'name': 'Fund A', 'currency': 'USD'},
        {'name': 'Fund B', 'currency': 'EUR'},
        {'name': 'Fund C', 'currency': 'GBP'},
    ]

    for idx, portfolio_data in enumerate(portfolios_data, 1):
        # Create portfolio
        portfolio_id = f"PORT-IMPORT-{idx}"

        # Create audit entry
        entry = AuditEntry(
            action_type=ActionType.IMPORT,
            action_category=ActionCategory.PORTFOLIO,
            username=request.user.username,
            action_description=f"Imported portfolio from file: {file_path}",
            entity_type=EntityType.PORTFOLIO,
            entity_id=portfolio_id,
            entity_name=portfolio_data['name'],
            status=AuditStatus.SUCCESS,
            metadata={
                'source_file': file_path,
                'row_number': idx,
                'total_rows': len(portfolios_data)
            },
            tags=['import', 'bulk', 'file-upload']
        )

        audit_entries.append(entry)

    # Log all entries in one batch
    audit_logger.log_batch(audit_entries)

    return {
        'imported': len(portfolios_data),
        'success': True
    }


# =============================================================================
# Example 6: Query Audit Logs
# =============================================================================

def get_portfolio_audit_history_example(portfolio_id, limit=50):
    """
    Example: Retrieve audit history for a specific portfolio.

    This shows how to query audit logs programmatically.
    """
    audit_logger = get_audit_logger()

    # Get all changes to this portfolio
    history = audit_logger.get_entity_history(
        entity_type='PORTFOLIO',
        entity_id=str(portfolio_id),
        limit=limit
    )

    # Format for display
    formatted_history = []
    for entry in history:
        formatted_history.append({
            'timestamp': entry.get('audit_timestamp'),
            'action': entry.get('action_type'),
            'user': entry.get('username'),
            'description': entry.get('action_description'),
            'field_changed': entry.get('field_name'),
            'old_value': entry.get('old_value'),
            'new_value': entry.get('new_value'),
            'status': entry.get('status')
        })

    return formatted_history


def get_user_activity_example(username, days=7):
    """
    Example: Get recent activity for a specific user.
    """
    audit_logger = get_audit_logger()

    activity = audit_logger.get_user_activity(
        username=username,
        days=days,
        limit=100
    )

    # Aggregate by action type
    action_counts = {}
    for entry in activity:
        action_type = entry.get('action_type')
        action_counts[action_type] = action_counts.get(action_type, 0) + 1

    return {
        'username': username,
        'days': days,
        'total_actions': len(activity),
        'action_breakdown': action_counts,
        'recent_activity': activity[:10]  # Most recent 10
    }


def get_failed_actions_example(days=1):
    """
    Example: Get all failed actions for monitoring.
    """
    audit_logger = get_audit_logger()

    from datetime import datetime, timedelta
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    # Query failed actions
    failed_actions = audit_logger.query(
        filters={
            'status': 'FAILURE',
            'audit_date': cutoff_date
        },
        limit=100
    )

    # Group by error type
    errors_by_type = {}
    for entry in failed_actions:
        error_msg = entry.get('error_message', 'Unknown error')
        if error_msg not in errors_by_type:
            errors_by_type[error_msg] = []
        errors_by_type[error_msg].append(entry)

    return {
        'total_failures': len(failed_actions),
        'unique_errors': len(errors_by_type),
        'errors_by_type': {k: len(v) for k, v in errors_by_type.items()},
        'details': failed_actions[:10]  # First 10 for review
    }


# =============================================================================
# Example 7: Error Handling with Audit
# =============================================================================

def risky_operation_example(request, portfolio_id):
    """
    Example: Properly audit both success and failure scenarios.

    This demonstrates how the audit system captures errors automatically.
    """
    with AuditContext(
        action_type=ActionType.DELETE,
        action_category=ActionCategory.PORTFOLIO,
        username=request.user.username,
        action_description=f"Delete portfolio {portfolio_id}",
        entity_type=EntityType.PORTFOLIO,
        entity_id=str(portfolio_id)
    ) as audit_ctx:
        # Simulate a risky operation
        portfolio = {'id': portfolio_id, 'name': 'Test Fund'}

        audit_ctx.set_entity(
            EntityType.PORTFOLIO,
            str(portfolio_id),
            portfolio['name']
        )

        # This would raise an exception in real scenario
        # raise Exception("Cannot delete portfolio with active trades")

        # If we get here, it succeeded
        return {'deleted': True, 'id': portfolio_id}


# =============================================================================
# Example 8: Integration with Django Views
# =============================================================================

def portfolio_api_view_example(request):
    """
    Example: Django view with automatic audit logging.

    This shows how audit integrates seamlessly with Django views.
    """
    if request.method == 'POST':
        # Create portfolio
        @audit_action(
            ActionType.CREATE,
            ActionCategory.PORTFOLIO,
            "Create portfolio via API",
            entity_type=EntityType.PORTFOLIO,
            capture_args=True  # Capture request parameters
        )
        def handle_create(req):
            name = req.POST.get('name')
            currency = req.POST.get('currency')

            portfolio_id = "PORT-API-001"

            return {
                'id': portfolio_id,
                'name': name,
                'currency': currency
            }

        return handle_create(request)

    elif request.method == 'PUT':
        # Update portfolio
        portfolio_id = request.GET.get('id')

        with AuditContext(
            action_type=ActionType.UPDATE,
            action_category=ActionCategory.PORTFOLIO,
            username=request.user.username,
            entity_type=EntityType.PORTFOLIO,
            entity_id=portfolio_id
        ):
            # Update logic here
            pass

    elif request.method == 'DELETE':
        # Delete portfolio
        portfolio_id = request.GET.get('id')

        with AuditContext(
            action_type=ActionType.DELETE,
            action_category=ActionCategory.PORTFOLIO,
            username=request.user.username,
            entity_type=EntityType.PORTFOLIO,
            entity_id=portfolio_id
        ):
            # Delete logic here
            pass

    return {'status': 'ok'}
