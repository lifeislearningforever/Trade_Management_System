"""
Order Workflow Validators
Contains business logic for validating order workflow actions
"""


def can_edit_order(user, order):
    """
    Check if user can edit an order

    Rules:
    - User must be the creator
    - Order must be in DRAFT status

    Args:
        user: User attempting to edit
        order: Order instance

    Returns:
        bool: True if user can edit, False otherwise
    """
    return order.created_by == user and order.status == 'DRAFT'


def can_submit_order(user, order):
    """
    Check if user can submit an order for approval

    Rules:
    - User must be the creator
    - Order must be in DRAFT status

    Args:
        user: User attempting to submit
        order: Order instance

    Returns:
        bool: True if user can submit, False otherwise
    """
    return order.created_by == user and order.status == 'DRAFT'


def can_approve_order(user, order):
    """
    Check if user can approve an order

    Rules:
    - Order must be in PENDING_APPROVAL status
    - User must NOT be the creator (four-eyes principle)
    - User must have 'approve_order' permission

    Args:
        user: User attempting to approve
        order: Order instance

    Returns:
        bool: True if user can approve, False otherwise
    """
    return (
        order.status == 'PENDING_APPROVAL' and
        order.created_by != user and
        user.has_permission('approve_order')
    )


def can_reject_order(user, order):
    """
    Check if user can reject an order

    Rules:
    - Same as approve (order must be pending, user is not creator)
    - User must have 'approve_order' permission

    Args:
        user: User attempting to reject
        order: Order instance

    Returns:
        bool: True if user can reject, False otherwise
    """
    return can_approve_order(user, order)


def can_delete_order(user, order):
    """
    Check if user can delete an order

    Rules:
    - User must be the creator
    - Order must be in DRAFT status
    - Only soft delete allowed (status change, not actual deletion)

    Args:
        user: User attempting to delete
        order: Order instance

    Returns:
        bool: True if user can delete, False otherwise
    """
    return order.created_by == user and order.status == 'DRAFT'


def validate_order_data(order_data):
    """
    Validate order data before saving

    Args:
        order_data: Dictionary containing order field values

    Returns:
        tuple: (is_valid, errors_dict)
    """
    errors = {}

    # Required fields
    required_fields = ['order_type', 'side', 'instrument', 'quantity', 'price', 'order_date']
    for field in required_fields:
        if not order_data.get(field):
            errors[field] = f'{field.replace("_", " ").title()} is required'

    # Quantity must be positive
    quantity = order_data.get('quantity')
    if quantity is not None and quantity <= 0:
        errors['quantity'] = 'Quantity must be greater than 0'

    # Price must be positive
    price = order_data.get('price')
    if price is not None and price <= 0:
        errors['price'] = 'Price must be greater than 0'

    return (len(errors) == 0, errors)


def get_workflow_error_message(action, user, order):
    """
    Get appropriate error message for workflow validation failure

    Args:
        action: str - 'edit', 'submit', 'approve', 'reject', 'delete'
        user: User instance
        order: Order instance

    Returns:
        str: Error message
    """
    if action == 'edit':
        if order.created_by != user:
            return 'You can only edit orders you created'
        if order.status != 'DRAFT':
            return f'Cannot edit order in {order.get_status_display()} status'

    elif action == 'submit':
        if order.created_by != user:
            return 'You can only submit orders you created'
        if order.status != 'DRAFT':
            return f'Cannot submit order in {order.get_status_display()} status'

    elif action in ['approve', 'reject']:
        if order.status != 'PENDING_APPROVAL':
            return f'Cannot {action} order in {order.get_status_display()} status'
        if order.created_by == user:
            return f'You cannot {action} your own order (four-eyes principle)'
        if not user.has_permission('approve_order'):
            return f'You do not have permission to {action} orders'

    elif action == 'delete':
        if order.created_by != user:
            return 'You can only delete orders you created'
        if order.status != 'DRAFT':
            return f'Cannot delete order in {order.get_status_display()} status'

    return f'Cannot {action} this order'
