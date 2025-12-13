"""
Pytest configuration and fixtures
"""
import pytest
from django.contrib.auth import get_user_model
from orders.models import Stock, Order
from portfolio.models import Portfolio
from reference_data.models import Client, Broker, Currency
from accounts.models import Role, Permission, RolePermission, UserRole

User = get_user_model()


@pytest.fixture
def create_permissions(db):
    """Create test permissions"""
    permissions = {
        'create_order': Permission.objects.create(
            code='create_order',
            name='Create Order',
            category='orders',
            description='Can create orders'
        ),
        'view_order': Permission.objects.create(
            code='view_order',
            name='View Order',
            category='orders',
            description='Can view orders'
        ),
        'approve_order': Permission.objects.create(
            code='approve_order',
            name='Approve Order',
            category='orders',
            description='Can approve orders'
        ),
        'create_portfolio': Permission.objects.create(
            code='create_portfolio',
            name='Create Portfolio',
            category='portfolio',
            description='Can create portfolios'
        ),
        'approve_portfolio': Permission.objects.create(
            code='approve_portfolio',
            name='Approve Portfolio',
            category='portfolio',
            description='Can approve portfolios'
        ),
    }
    return permissions


@pytest.fixture
def create_roles(db, create_permissions):
    """Create test roles with permissions"""
    # Maker role
    maker_role = Role.objects.create(
        code='MAKER',
        name='Maker',
        description='Can create and submit orders/portfolios'
    )
    RolePermission.objects.create(
        role=maker_role,
        permission=create_permissions['create_order']
    )
    RolePermission.objects.create(
        role=maker_role,
        permission=create_permissions['view_order']
    )
    RolePermission.objects.create(
        role=maker_role,
        permission=create_permissions['create_portfolio']
    )

    # Checker role
    checker_role = Role.objects.create(
        code='CHECKER',
        name='Checker',
        description='Can approve/reject orders/portfolios'
    )
    RolePermission.objects.create(
        role=checker_role,
        permission=create_permissions['view_order']
    )
    RolePermission.objects.create(
        role=checker_role,
        permission=create_permissions['approve_order']
    )
    RolePermission.objects.create(
        role=checker_role,
        permission=create_permissions['approve_portfolio']
    )

    return {'maker': maker_role, 'checker': checker_role}


@pytest.fixture
def maker_user(db, create_roles):
    """Create a maker user"""
    user = User.objects.create_user(
        username='testmaker',
        email='maker@test.com',
        password='Test@1234',
        first_name='Test',
        last_name='Maker',
        employee_id='EMP001',
        is_staff=True
    )
    UserRole.objects.create(
        user=user,
        role=create_roles['maker'],
        is_primary=True
    )
    return user


@pytest.fixture
def checker_user(db, create_roles):
    """Create a checker user"""
    user = User.objects.create_user(
        username='testchecker',
        email='checker@test.com',
        password='Test@1234',
        first_name='Test',
        last_name='Checker',
        employee_id='EMP002',
        is_staff=True
    )
    UserRole.objects.create(
        user=user,
        role=create_roles['checker'],
        is_primary=True
    )
    return user


@pytest.fixture
def admin_user(db):
    """Create an admin user"""
    return User.objects.create_superuser(
        username='testadmin',
        email='admin@test.com',
        password='Admin@1234',
        first_name='Test',
        last_name='Admin'
    )


@pytest.fixture
def test_stock(db):
    """Create a test stock"""
    return Stock.objects.create(
        symbol='RELIANCE',
        name='Reliance Industries Ltd',
        exchange='NSE',
        asset_class='EQUITY',
        currency='INR',
        lot_size=1
    )


@pytest.fixture
def test_client(db):
    """Create a test client"""
    return Client.objects.create(
        name='Test Client Ltd',
        client_id='CLI001',
        client_type='CORPORATE',
        email='client@test.com',
        phone='+919876543210',
        is_active=True
    )


@pytest.fixture
def test_broker(db):
    """Create a test broker"""
    return Broker.objects.create(
        name='Test Broker Ltd',
        code='BRK001',
        broker_type='FULL_SERVICE',
        email='broker@test.com',
        phone='+919876543210',
        is_active=True
    )


@pytest.fixture
def draft_order(db, maker_user, test_stock, test_client):
    """Create a draft order"""
    order = Order.objects.create(
        order_id='ORD-000001',
        stock=test_stock,
        side='BUY',
        order_type='MARKET',
        quantity=100,
        price=2500.00,
        status='DRAFT',
        created_by=maker_user,
        created_by_name=maker_user.get_full_name(),
        created_by_employee_id=maker_user.employee_id or '',
        client=test_client,
        validity='DAY'
    )
    return order


@pytest.fixture
def pending_order(db, maker_user, test_stock, test_client):
    """Create a pending approval order"""
    order = Order.objects.create(
        order_id='ORD-000002',
        stock=test_stock,
        side='SELL',
        order_type='LIMIT',
        quantity=50,
        price=2600.00,
        status='PENDING_APPROVAL',
        created_by=maker_user,
        created_by_name=maker_user.get_full_name(),
        created_by_employee_id=maker_user.employee_id or '',
        client=test_client,
        validity='DAY'
    )
    return order


@pytest.fixture
def approved_order(db, maker_user, checker_user, test_stock, test_client):
    """Create an approved order"""
    from django.utils import timezone
    order = Order.objects.create(
        order_id='ORD-000003',
        stock=test_stock,
        side='BUY',
        order_type='MARKET',
        quantity=200,
        price=2550.00,
        status='APPROVED',
        created_by=maker_user,
        created_by_name=maker_user.get_full_name(),
        created_by_employee_id=maker_user.employee_id or '',
        approved_by=checker_user,
        approved_by_name=checker_user.get_full_name(),
        approved_by_employee_id=checker_user.employee_id or '',
        approved_at=timezone.now(),
        client=test_client,
        validity='DAY'
    )
    return order
