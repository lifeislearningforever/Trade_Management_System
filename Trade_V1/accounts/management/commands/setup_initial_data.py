"""
Management command to setup initial data
- Creates roles and permissions
- Creates test users (maker and checker)
- Creates sample reference data
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from accounts.models import Role, Permission, UserRole, RolePermission
from reference_data.models import Currency, Client, Broker
from orders.models import Stock
from decimal import Decimal

User = get_user_model()


class Command(BaseCommand):
    help = 'Setup initial data for the application'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-users',
            action='store_true',
            help='Skip creating test users',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting initial data setup...\n'))

        # 1. Create Permissions
        self.create_permissions()

        # 2. Create Roles
        self.create_roles()

        # 3. Assign Permissions to Roles
        self.assign_permissions_to_roles()

        # 4. Create Test Users (unless skipped)
        if not options['skip_users']:
            self.create_test_users()

        # 5. Create Sample Reference Data
        self.create_sample_currencies()
        self.create_sample_clients()
        self.create_sample_brokers()
        self.create_sample_stocks()

        self.stdout.write(self.style.SUCCESS('\n✅ Initial data setup completed successfully!'))
        self.stdout.write(self.style.SUCCESS('\nTest Users Created:'))
        self.stdout.write('  Maker:   username=maker1,   password=Test@1234')
        self.stdout.write('  Checker: username=checker1, password=Test@1234')
        self.stdout.write('  Admin:   username=admin1,   password=Admin@1234')

    def create_permissions(self):
        """Create system permissions"""
        self.stdout.write('Creating permissions...')

        permissions_data = [
            # Orders
            ('create_order', 'Create Order', 'Can create trading orders', 'orders'),
            ('view_order', 'View Order', 'Can view trading orders', 'orders'),
            ('edit_order', 'Edit Order', 'Can edit draft orders', 'orders'),
            ('delete_order', 'Delete Order', 'Can delete draft orders', 'orders'),
            ('submit_order', 'Submit Order', 'Can submit orders for approval', 'orders'),
            ('approve_order', 'Approve Order', 'Can approve orders', 'orders'),
            ('reject_order', 'Reject Order', 'Can reject orders', 'orders'),

            # Portfolio
            ('create_portfolio', 'Create Portfolio', 'Can create portfolios', 'portfolio'),
            ('view_portfolio', 'View Portfolio', 'Can view portfolios', 'portfolio'),
            ('edit_portfolio', 'Edit Portfolio', 'Can edit draft portfolios', 'portfolio'),
            ('delete_portfolio', 'Delete Portfolio', 'Can delete draft portfolios', 'portfolio'),
            ('submit_portfolio', 'Submit Portfolio', 'Can submit portfolios for approval', 'portfolio'),
            ('approve_portfolio', 'Approve Portfolio', 'Can approve portfolios', 'portfolio'),
            ('reject_portfolio', 'Reject Portfolio', 'Can reject portfolios', 'portfolio'),

            # Reference Data
            ('view_reference_data', 'View Reference Data', 'Can view reference data', 'reference_data'),
            ('edit_reference_data', 'Edit Reference Data', 'Can edit reference data', 'reference_data'),

            # UDF
            ('manage_udf', 'Manage UDF', 'Can manage user defined fields', 'udf'),

            # Reports
            ('generate_report', 'Generate Report', 'Can generate reports', 'reports'),
            ('view_report', 'View Report', 'Can view reports', 'reports'),

            # Admin
            ('view_audit_log', 'View Audit Log', 'Can view audit logs', 'admin'),
            ('manage_users', 'Manage Users', 'Can manage users', 'admin'),
            ('manage_roles', 'Manage Roles', 'Can manage roles and permissions', 'admin'),
        ]

        created_count = 0
        for code, name, description, category in permissions_data:
            permission, created = Permission.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': description,
                    'category': category,
                    'is_active': True
                }
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created_count} permissions'))

    def create_roles(self):
        """Create system roles"""
        self.stdout.write('Creating roles...')

        roles_data = [
            ('MAKER', 'Maker', 'Can create and submit records for approval', True, 1),
            ('CHECKER', 'Checker', 'Can approve or reject submitted records', True, 2),
            ('VIEWER', 'Viewer', 'Can only view records', True, 3),
            ('ADMIN', 'Administrator', 'Full system access', True, 4),
        ]

        created_count = 0
        for code, name, description, is_system_role, display_order in roles_data:
            role, created = Role.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': description,
                    'is_system_role': is_system_role,
                    'is_active': True,
                    'display_order': display_order
                }
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created_count} roles'))

    def assign_permissions_to_roles(self):
        """Assign permissions to roles"""
        self.stdout.write('Assigning permissions to roles...')

        # MAKER permissions
        maker_permissions = [
            'create_order', 'view_order', 'edit_order', 'delete_order', 'submit_order',
            'create_portfolio', 'view_portfolio', 'edit_portfolio', 'delete_portfolio', 'submit_portfolio',
            'view_reference_data', 'generate_report', 'view_report',
        ]

        # CHECKER permissions
        checker_permissions = [
            'view_order', 'approve_order', 'reject_order',
            'view_portfolio', 'approve_portfolio', 'reject_portfolio',
            'view_reference_data', 'view_report',
        ]

        # VIEWER permissions
        viewer_permissions = [
            'view_order', 'view_portfolio', 'view_reference_data', 'view_report',
        ]

        # ADMIN permissions (all)
        admin_permissions = Permission.objects.values_list('code', flat=True)

        assignments = [
            ('MAKER', maker_permissions),
            ('CHECKER', checker_permissions),
            ('VIEWER', viewer_permissions),
            ('ADMIN', admin_permissions),
        ]

        created_count = 0
        for role_code, permission_codes in assignments:
            try:
                role = Role.objects.get(code=role_code)
                for perm_code in permission_codes:
                    try:
                        permission = Permission.objects.get(code=perm_code)
                        _, created = RolePermission.objects.get_or_create(
                            role=role,
                            permission=permission
                        )
                        if created:
                            created_count += 1
                    except Permission.DoesNotExist:
                        pass
            except Role.DoesNotExist:
                pass

        self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created_count} role-permission assignments'))

    def create_test_users(self):
        """Create test users for maker and checker"""
        self.stdout.write('Creating test users...')

        users_data = [
            {
                'username': 'maker1',
                'email': 'maker1@trademanagement.com',
                'password': 'Test@1234',
                'first_name': 'Test',
                'last_name': 'Maker',
                'employee_id': 'EMP001',
                'department': 'Trading',
                'designation': 'Trader',
                'role': 'MAKER',
            },
            {
                'username': 'checker1',
                'email': 'checker1@trademanagement.com',
                'password': 'Test@1234',
                'first_name': 'Test',
                'last_name': 'Checker',
                'employee_id': 'EMP002',
                'department': 'Risk',
                'designation': 'Risk Manager',
                'role': 'CHECKER',
            },
            {
                'username': 'admin1',
                'email': 'admin1@trademanagement.com',
                'password': 'Admin@1234',
                'first_name': 'System',
                'last_name': 'Administrator',
                'employee_id': 'EMP000',
                'department': 'IT',
                'designation': 'System Admin',
                'role': 'ADMIN',
                'is_superuser': True,
                'is_staff': True,
            },
        ]

        created_count = 0
        for user_data in users_data:
            role_code = user_data.pop('role')
            password = user_data.pop('password')
            is_superuser = user_data.pop('is_superuser', False)
            is_staff = user_data.pop('is_staff', False)

            user, created = User.objects.get_or_create(
                username=user_data['username'],
                defaults={
                    **user_data,
                    'is_active': True,
                    'is_superuser': is_superuser,
                    'is_staff': is_staff,
                }
            )

            if created:
                user.set_password(password)
                user.save()
                created_count += 1

                # Assign role
                try:
                    role = Role.objects.get(code=role_code)
                    UserRole.objects.get_or_create(
                        user=user,
                        role=role,
                        defaults={'is_primary': True}
                    )
                except Role.DoesNotExist:
                    pass

        self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created_count} test users'))

    def create_sample_currencies(self):
        """Create sample currencies"""
        self.stdout.write('Creating sample currencies...')

        currencies = [
            ('INR', 'Indian Rupee', '₹', 'India', 2),
            ('USD', 'US Dollar', '$', 'United States', 2),
            ('EUR', 'Euro', '€', 'European Union', 2),
            ('GBP', 'British Pound', '£', 'United Kingdom', 2),
            ('JPY', 'Japanese Yen', '¥', 'Japan', 0),
        ]

        created_count = 0
        for code, name, symbol, country, decimal_places in currencies:
            _, created = Currency.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'symbol': symbol,
                    'country': country,
                    'decimal_places': decimal_places,
                    'is_active': True,
                    'is_base_currency': (code == 'INR')
                }
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created_count} currencies'))

    def create_sample_clients(self):
        """Create sample clients"""
        self.stdout.write('Creating sample clients...')

        clients = [
            ('CLI001', 'INDIVIDUAL', 'John Smith', 'john.smith@email.com'),
            ('CLI002', 'CORPORATE', 'ABC Corporation', 'contact@abc.com'),
            ('CLI003', 'HNI', 'Wealth Client One', 'wealth1@email.com'),
        ]

        created_count = 0
        for client_id, client_type, name, email in clients:
            _, created = Client.objects.get_or_create(
                client_id=client_id,
                defaults={
                    'client_type': client_type,
                    'name': name,
                    'email': email,
                    'status': 'ACTIVE',
                    'is_active': True,
                    'kyc_status': 'VERIFIED',
                }
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created_count} clients'))

    def create_sample_brokers(self):
        """Create sample brokers"""
        self.stdout.write('Creating sample brokers...')

        brokers = [
            ('ZERODHA', 'Zerodha', 'DISCOUNT'),
            ('ICICI', 'ICICI Direct', 'FULL_SERVICE'),
            ('HDFC', 'HDFC Securities', 'FULL_SERVICE'),
        ]

        created_count = 0
        for code, name, broker_type in brokers:
            _, created = Broker.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'broker_type': broker_type,
                    'is_active': True,
                }
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created_count} brokers'))

    def create_sample_stocks(self):
        """Create sample stocks"""
        self.stdout.write('Creating sample stocks...')

        stocks = [
            ('RELIANCE', 'Reliance Industries Ltd', 'INE002A01018', 'NSE', 'EQUITY', 'Energy', 'Oil & Gas'),
            ('TCS', 'Tata Consultancy Services Ltd', 'INE467B01029', 'NSE', 'EQUITY', 'Technology', 'IT Services'),
            ('HDFCBANK', 'HDFC Bank Ltd', 'INE040A01034', 'NSE', 'EQUITY', 'Finance', 'Banking'),
            ('INFY', 'Infosys Ltd', 'INE009A01021', 'NSE', 'EQUITY', 'Technology', 'IT Services'),
            ('ICICIBANK', 'ICICI Bank Ltd', 'INE090A01021', 'NSE', 'EQUITY', 'Finance', 'Banking'),
        ]

        created_count = 0
        for symbol, name, isin, exchange, asset_class, sector, industry in stocks:
            _, created = Stock.objects.get_or_create(
                symbol=symbol,
                defaults={
                    'name': name,
                    'isin': isin,
                    'exchange': exchange,
                    'asset_class': asset_class,
                    'sector': sector,
                    'industry': industry,
                    'currency': 'INR',
                    'lot_size': 1,
                    'is_active': True,
                }
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'  ✓ Created {created_count} stocks'))
