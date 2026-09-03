-- =====================================================
-- Sample Users for CisTrade
-- Note: Django will hash passwords, these are for reference
-- Use Django's createsuperuser command instead
-- =====================================================

-- To create users via Django:
-- python manage.py shell
-- from django.contrib.auth.models import User
-- User.objects.create_user('maker1', 'maker1@cistrade.com', 'password123')

-- Sample User Roles:
-- 1. Superuser (admin) - Full access
-- 2. Makers (maker1, maker2) - Create/Edit portfolios and UDFs
-- 3. Checkers (checker1, checker2) - Approve/Reject
-- 4. Viewers (viewer1) - Read-only access

-- Commands to create users:
/*
python manage.py shell << EOF
from django.contrib.auth.models import User, Group

# Create superuser (if not already exists)
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@cistrade.com', 'admin@2025')

# Create Makers
maker1 = User.objects.create_user('maker1', 'maker1@cistrade.com', 'maker@2025')
maker1.first_name = 'John'
maker1.last_name = 'Doe'
maker1.save()

maker2 = User.objects.create_user('maker2', 'maker2@cistrade.com', 'maker@2025')
maker2.first_name = 'Jane'
maker2.last_name = 'Smith'
maker2.save()

# Create Checkers
checker1 = User.objects.create_user('checker1', 'checker1@cistrade.com', 'checker@2025')
checker1.first_name = 'Mike'
checker1.last_name = 'Johnson'
checker1.save()

checker2 = User.objects.create_user('checker2', 'checker2@cistrade.com', 'checker@2025')
checker2.first_name = 'Sarah'
checker2.last_name = 'Williams'
checker2.save()

# Create Viewer
viewer1 = User.objects.create_user('viewer1', 'viewer1@cistrade.com', 'viewer@2025')
viewer1.first_name = 'Bob'
viewer1.last_name = 'Brown'
viewer1.save()

# Create Groups
makers_group, _ = Group.objects.get_or_create(name='Makers')
checkers_group, _ = Group.objects.get_or_create(name='Checkers')
viewers_group, _ = Group.objects.get_or_create(name='Viewers')

# Assign users to groups
maker1.groups.add(makers_group)
maker2.groups.add(makers_group)
checker1.groups.add(checkers_group)
checker2.groups.add(checkers_group)
viewer1.groups.add(viewers_group)

print("Users created successfully!")
EOF
*/

-- User Summary:
-- Username     | Password       | Role       | Email
-- -------------|----------------|------------|----------------------
-- admin        | admin@2025     | Superuser  | admin@cistrade.com
-- maker1       | maker@2025     | Maker      | maker1@cistrade.com
-- maker2       | maker@2025     | Maker      | maker2@cistrade.com
-- checker1     | checker@2025   | Checker    | checker1@cistrade.com
-- checker2     | checker@2025   | Checker    | checker2@cistrade.com
-- viewer1      | viewer@2025    | Viewer     | viewer1@cistrade.com
