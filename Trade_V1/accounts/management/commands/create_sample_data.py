"""
Management command to create sample data for Trade Management System V1
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal

from accounts.models import User, Role, Permission, RolePermission, UserRole
from udf.models import UDFType, UDFSubtype, UDFField
from reference_data.models import Currency, Broker, Client, TradingCalendar
from orders.models import Stock, Order
from portfolio.models import Portfolio


class Command(BaseCommand):
    help = 'Creates sample data for testing the Trade Management System'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Creating sample data...'))

        # 1. Create Permissions
        self.stdout.write('Creating permissions...')
        permissions_data = [
            ('view_order', 'View Order', 'orders'),
            ('create_order', 'Create Order', 'orders'),
            ('approve_order', 'Approve Order', 'orders'),
            ('view_portfolio', 'View Portfolio', 'portfolio'),
            ('create_portfolio', 'Create Portfolio', 'portfolio'),
            ('approve_portfolio', 'Approve Portfolio', 'portfolio'),
            ('view_report', 'View Report', 'reporting'),
            ('generate_report', 'Generate Report', 'reporting'),
        ]

        for code, name, category in permissions_data:
            Permission.objects.get_or_create(
                code=code,
                defaults={'name': name, 'category': category, 'is_active': True}
            )

        # 2. Create Roles
        self.stdout.write('Creating roles...')
        admin_role, _ = Role.objects.get_or_create(
            code='ADMIN',
            defaults={'name': 'Administrator', 'is_active': True, 'is_system_role': True, 'display_order': 1}
        )
        maker_role, _ = Role.objects.get_or_create(
            code='MAKER',
            defaults={'name': 'Maker', 'is_active': True, 'is_system_role': True, 'display_order': 2}
        )
        checker_role, _ = Role.objects.get_or_create(
            code='CHECKER',
            defaults={'name': 'Checker', 'is_active': True, 'is_system_role': True, 'display_order': 3}
        )
        viewer_role, _ = Role.objects.get_or_create(
            code='VIEWER',
            defaults={'name': 'Viewer', 'is_active': True, 'is_system_role': True, 'display_order': 4}
        )

        # 3. Assign Permissions to Roles
        self.stdout.write('Assigning permissions to roles...')
        # Maker: can create orders and portfolios
        for perm_code in ['view_order', 'create_order', 'view_portfolio', 'create_portfolio', 'view_report']:
            perm = Permission.objects.get(code=perm_code)
            RolePermission.objects.get_or_create(role=maker_role, permission=perm)

        # Checker: can approve
        for perm_code in ['view_order', 'approve_order', 'view_portfolio', 'approve_portfolio', 'view_report']:
            perm = Permission.objects.get(code=perm_code)
            RolePermission.objects.get_or_create(role=checker_role, permission=perm)

        # Admin: all permissions
        for perm in Permission.objects.all():
            RolePermission.objects.get_or_create(role=admin_role, permission=perm)

        # 4. Create Test Users
        self.stdout.write('Creating test users...')
        maker1, _ = User.objects.get_or_create(
            username='maker1',
            defaults={
                'email': 'maker1@trademanagement.com',
                'first_name': 'John',
                'last_name': 'Smith',
                'employee_id': 'EMP101',
                'department': 'Trading',
                'designation': 'Trader',
                'employment_status': 'ACTIVE',
            }
        )
        if not maker1.password:
            maker1.set_password('maker123456')
            maker1.save()

        maker2, _ = User.objects.get_or_create(
            username='maker2',
            defaults={
                'email': 'maker2@trademanagement.com',
                'first_name': 'Jane',
                'last_name': 'Doe',
                'employee_id': 'EMP102',
                'department': 'Trading',
                'designation': 'Senior Trader',
                'employment_status': 'ACTIVE',
            }
        )
        if not maker2.password:
            maker2.set_password('maker123456')
            maker2.save()

        checker1, _ = User.objects.get_or_create(
            username='checker1',
            defaults={
                'email': 'checker1@trademanagement.com',
                'first_name': 'Robert',
                'last_name': 'Johnson',
                'employee_id': 'EMP201',
                'department': 'Risk',
                'designation': 'Risk Manager',
                'employment_status': 'ACTIVE',
            }
        )
        if not checker1.password:
            checker1.set_password('checker123456')
            checker1.save()

        # 5. Assign Roles to Users
        self.stdout.write('Assigning roles to users...')
        UserRole.objects.get_or_create(user=maker1, role=maker_role, defaults={'is_primary': True})
        UserRole.objects.get_or_create(user=maker2, role=maker_role, defaults={'is_primary': True})
        UserRole.objects.get_or_create(user=checker1, role=checker_role, defaults={'is_primary': True})

        # 6. Create UDF Types, Subtypes, and Fields
        self.stdout.write('Creating UDF data...')
        # Portfolio UDF
        portfolio_type, _ = UDFType.objects.get_or_create(
            code='PORTFOLIO',
            defaults={'name': 'Portfolio', 'is_active': True, 'display_order': 1}
        )

        group_subtype, _ = UDFSubtype.objects.get_or_create(
            udf_type=portfolio_type,
            code='GROUP',
            defaults={'name': 'Portfolio Group', 'field_label': 'Portfolio Group', 'is_active': True, 'display_order': 1}
        )

        for code, value in [('EQUITY', 'Equity'), ('FIXED_INCOME', 'Fixed Income'), ('DERIVATIVES', 'Derivatives')]:
            UDFField.objects.get_or_create(
                udf_subtype=group_subtype,
                code=code,
                defaults={'value': value, 'is_active': True, 'is_default': (code == 'EQUITY')}
            )

        manager_subtype, _ = UDFSubtype.objects.get_or_create(
            udf_type=portfolio_type,
            code='MANAGER',
            defaults={'name': 'Portfolio Manager', 'field_label': 'Manager', 'is_active': True, 'display_order': 2}
        )

        for code, value in [('MGR001', 'John Smith (EMP101)'), ('MGR002', 'Jane Doe (EMP102)')]:
            UDFField.objects.get_or_create(
                udf_subtype=manager_subtype,
                code=code,
                defaults={'value': value, 'is_active': True}
            )

        # Report UDF
        report_type, _ = UDFType.objects.get_or_create(
            code='REPORT',
            defaults={'name': 'Report', 'is_active': True, 'display_order': 2}
        )

        type_subtype, _ = UDFSubtype.objects.get_or_create(
            udf_type=report_type,
            code='TYPE',
            defaults={'name': 'Report Type', 'field_label': 'Report Type', 'is_active': True, 'display_order': 1}
        )

        for code, value in [('PORTFOLIO_SUMMARY', 'Portfolio Summary'), ('TRADE_HISTORY', 'Trade History'), ('PNL_STATEMENT', 'P&L Statement')]:
            UDFField.objects.get_or_create(
                udf_subtype=type_subtype,
                code=code,
                defaults={'value': value, 'is_active': True}
            )

        # 7. Create Currencies
        self.stdout.write('Creating currencies...')
        for code, name, symbol, country in [
            ('INR', 'Indian Rupee', '₹', 'India'),
            ('USD', 'US Dollar', '$', 'United States'),
            ('EUR', 'Euro', '€', 'European Union'),
            ('GBP', 'British Pound', '£', 'United Kingdom'),
        ]:
            Currency.objects.get_or_create(
                code=code,
                defaults={'name': name, 'symbol': symbol, 'country': country, 'is_active': True, 'is_base_currency': (code == 'INR')}
            )

        # 8. Create Brokers
        self.stdout.write('Creating brokers...')
        for code, name in [
            ('ZERODHA', 'Zerodha'),
            ('ICICI', 'ICICI Direct'),
            ('HDFC', 'HDFC Securities'),
        ]:
            Broker.objects.get_or_create(
                code=code,
                defaults={'name': name, 'broker_type': 'DISCOUNT', 'is_active': True}
            )

        # 9. Create Clients
        self.stdout.write('Creating clients...')
        for client_id, name, client_type in [
            ('CLT001', 'ABC Corporation', 'CORPORATE'),
            ('CLT002', 'XYZ Ltd', 'CORPORATE'),
            ('CLT003', 'Individual Investor 1', 'INDIVIDUAL'),
        ]:
            Client.objects.get_or_create(
                client_id=client_id,
                defaults={'name': name, 'client_type': client_type, 'status': 'ACTIVE', 'kyc_status': 'VERIFIED'}
            )

        # 10. Create Stocks
        self.stdout.write('Creating stocks...')
        stocks_data = [
            ('RELIANCE', 'Reliance Industries Limited', 'NSE', 'EQUITY', 'Energy', 'Oil & Gas'),
            ('TCS', 'Tata Consultancy Services', 'NSE', 'EQUITY', 'Technology', 'IT Services'),
            ('INFY', 'Infosys Limited', 'NSE', 'EQUITY', 'Technology', 'IT Services'),
            ('HDFCBANK', 'HDFC Bank Limited', 'NSE', 'EQUITY', 'Finance', 'Banking'),
            ('ICICIBANK', 'ICICI Bank Limited', 'NSE', 'EQUITY', 'Finance', 'Banking'),
            ('SBIN', 'State Bank of India', 'NSE', 'EQUITY', 'Finance', 'Banking'),
            ('ITC', 'ITC Limited', 'NSE', 'EQUITY', 'Consumer', 'FMCG'),
            ('BHARTIARTL', 'Bharti Airtel Limited', 'NSE', 'EQUITY', 'Telecom', 'Telecommunications'),
            ('WIPRO', 'Wipro Limited', 'NSE', 'EQUITY', 'Technology', 'IT Services'),
            ('LT', 'Larsen & Toubro Limited', 'NSE', 'EQUITY', 'Infrastructure', 'Engineering'),
        ]

        for symbol, name, exchange, asset_class, sector, industry in stocks_data:
            Stock.objects.get_or_create(
                symbol=symbol,
                defaults={
                    'name': name,
                    'exchange': exchange,
                    'asset_class': asset_class,
                    'sector': sector,
                    'industry': industry,
                    'currency': 'INR',
                    'is_active': True,
                }
            )

        # 11. Create Trading Calendar
        self.stdout.write('Creating trading calendar...')
        today = timezone.now().date()
        for i in range(30):  # Next 30 days
            date = today + timedelta(days=i)
            is_weekend = date.weekday() >= 5
            TradingCalendar.objects.get_or_create(
                date=date,
                exchange='NSE',
                defaults={
                    'is_trading_day': not is_weekend,
                    'is_settlement_day': not is_weekend,
                    'is_holiday': is_weekend,
                    'holiday_name': 'Weekend' if is_weekend else '',
                }
            )

        self.stdout.write(self.style.SUCCESS('✅ Sample data created successfully!'))
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Test Users Created:'))
        self.stdout.write(f'  Maker1:   username=maker1,   password=maker123456  ({maker1.get_display_name()})')
        self.stdout.write(f'  Maker2:   username=maker2,   password=maker123456  ({maker2.get_display_name()})')
        self.stdout.write(f'  Checker1: username=checker1, password=checker123456 ({checker1.get_display_name()})')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Sample Data Summary:'))
        self.stdout.write(f'  Roles: {Role.objects.count()}')
        self.stdout.write(f'  Permissions: {Permission.objects.count()}')
        self.stdout.write(f'  Users: {User.objects.count()}')
        self.stdout.write(f'  UDF Types: {UDFType.objects.count()}')
        self.stdout.write(f'  UDF Subtypes: {UDFSubtype.objects.count()}')
        self.stdout.write(f'  UDF Fields: {UDFField.objects.count()}')
        self.stdout.write(f'  Currencies: {Currency.objects.count()}')
        self.stdout.write(f'  Brokers: {Broker.objects.count()}')
        self.stdout.write(f'  Clients: {Client.objects.count()}')
        self.stdout.write(f'  Stocks: {Stock.objects.count()}')
        self.stdout.write(f'  Trading Calendar Entries: {TradingCalendar.objects.count()}')
