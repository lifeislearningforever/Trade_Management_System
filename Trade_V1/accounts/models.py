"""
Accounts Models - Enhanced RBAC System
Comprehensive Role-Based Access Control with Users, Roles, Permissions, and Audit Logs
"""

from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator, MinLengthValidator
from django.utils import timezone
import uuid


class Permission(models.Model):
    """
    Defines granular permissions for system actions
    Examples: view_customer_data, edit_product_inventory, approve_trade, etc.
    """
    code = models.CharField(
        max_length=100,
        unique=True,
        validators=[RegexValidator(r'^[a-z_]+$', 'Only lowercase letters and underscores allowed')],
        help_text="Unique code for permission (e.g., 'view_customer_data')"
    )
    name = models.CharField(
        max_length=200,
        help_text="Display name for the permission"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of what this permission allows"
    )
    category = models.CharField(
        max_length=50,
        help_text="Permission category (e.g., 'orders', 'portfolio', 'reports')"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this permission is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'permission'
        ordering = ['category', 'name']
        verbose_name = 'Permission'
        verbose_name_plural = 'Permissions'
        indexes = [
            models.Index(fields=['category', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Role(models.Model):
    """
    Defines job functions/groups
    Examples: Manager, Sales Associate, Trader, Portfolio Manager, Checker, Maker
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        validators=[RegexValidator(r'^[A-Z_]+$', 'Only uppercase letters and underscores allowed')],
        help_text="Unique code for role (e.g., 'PORTFOLIO_MANAGER')"
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name for the role"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of this role's responsibilities"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this role is active"
    )
    is_system_role = models.BooleanField(
        default=False,
        help_text="Whether this is a system-defined role (cannot be deleted)"
    )
    permissions = models.ManyToManyField(
        Permission,
        through='RolePermission',
        related_name='roles',
        help_text="Permissions assigned to this role"
    )
    display_order = models.IntegerField(
        default=0,
        help_text="Order for displaying in lists"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'role'
        ordering = ['display_order', 'name']
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_permission_codes(self):
        """Returns list of permission codes for this role"""
        return list(self.permissions.filter(is_active=True).values_list('code', flat=True))


class RolePermission(models.Model):
    """
    Many-to-many mapping between Roles and Permissions
    Allows fine-grained control and audit trail of permission assignments
    """
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name='role_permissions'
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name='permission_roles'
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.CharField(
        max_length=200,
        blank=True,
        help_text="User who granted this permission"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about why this permission was granted"
    )

    class Meta:
        db_table = 'role_permission'
        unique_together = [['role', 'permission']]
        verbose_name = 'Role Permission'
        verbose_name_plural = 'Role Permissions'

    def __str__(self):
        return f"{self.role.code} - {self.permission.code}"


class UserManager(BaseUserManager):
    """Custom user manager for enhanced User model"""

    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required')
        if not username:
            raise ValueError('Username is required')

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')

        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """
    Enhanced User Model with comprehensive attributes
    Extends Django's AbstractUser with business-specific fields
    """

    # Override email to make it required and unique
    email = models.EmailField(
        unique=True,
        help_text="User's email address"
    )

    # Personal Information
    first_name = models.CharField(
        max_length=100,
        validators=[MinLengthValidator(2)],
        help_text="User's first name"
    )
    last_name = models.CharField(
        max_length=100,
        validators=[MinLengthValidator(2)],
        help_text="User's last name"
    )
    middle_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="User's middle name"
    )
    full_name = models.CharField(
        max_length=300,
        editable=False,
        help_text="Auto-generated full name"
    )

    # Employee Information
    employee_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text="Unique employee identifier"
    )
    department = models.CharField(
        max_length=100,
        blank=True,
        help_text="Department name"
    )
    designation = models.CharField(
        max_length=100,
        blank=True,
        help_text="Job title/designation"
    )
    reporting_manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates',
        help_text="Direct reporting manager"
    )

    # Contact Information
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', 'Enter a valid phone number')],
        help_text="Contact phone number"
    )
    mobile_number = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', 'Enter a valid mobile number')],
        help_text="Mobile phone number"
    )
    alternate_email = models.EmailField(
        blank=True,
        help_text="Alternate email address"
    )

    # Address Information
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default='India')
    postal_code = models.CharField(max_length=20, blank=True)

    # Professional Information
    joining_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of joining the organization"
    )
    leaving_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of leaving the organization"
    )
    employment_status = models.CharField(
        max_length=20,
        choices=[
            ('ACTIVE', 'Active'),
            ('ON_LEAVE', 'On Leave'),
            ('SUSPENDED', 'Suspended'),
            ('TERMINATED', 'Terminated'),
            ('RESIGNED', 'Resigned'),
        ],
        default='ACTIVE',
        help_text="Current employment status"
    )

    # Role-based Access (Many-to-Many with Role)
    roles = models.ManyToManyField(
        Role,
        through='UserRole',
        related_name='users',
        help_text="Roles assigned to this user"
    )

    # Profile & Settings
    profile_picture = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True,
        help_text="User profile picture"
    )
    bio = models.TextField(
        blank=True,
        help_text="Short biography"
    )
    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="User's timezone"
    )
    language = models.CharField(
        max_length=10,
        default='en',
        choices=[
            ('en', 'English'),
            ('hi', 'Hindi'),
        ],
        help_text="Preferred language"
    )

    # Security & Access
    last_login_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of last login"
    )
    failed_login_attempts = models.IntegerField(
        default=0,
        help_text="Number of consecutive failed login attempts"
    )
    account_locked_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Account locked until this timestamp"
    )
    password_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When password was last changed"
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="User must change password on next login"
    )

    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=200, blank=True)
    updated_by = models.CharField(max_length=200, blank=True)

    # Additional Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional user metadata as JSON"
    )

    objects = UserManager()

    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']

    class Meta:
        db_table = 'user'
        ordering = ['first_name', 'last_name']
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['employment_status']),
            models.Index(fields=['department']),
        ]

    def save(self, *args, **kwargs):
        # Auto-generate full name
        name_parts = [self.first_name]
        if self.middle_name:
            name_parts.append(self.middle_name)
        name_parts.append(self.last_name)
        self.full_name = ' '.join(name_parts)

        super().save(*args, **kwargs)

    def __str__(self):
        if self.employee_id:
            return f"{self.full_name} ({self.employee_id})"
        return self.full_name

    def get_full_name(self):
        """Returns the full name"""
        return self.full_name

    def get_short_name(self):
        """Returns first name"""
        return self.first_name

    def get_display_name(self):
        """Returns name with employee ID for display purposes"""
        if self.employee_id:
            return f"{self.full_name} ({self.employee_id})"
        return self.full_name

    def has_role(self, role_code):
        """Check if user has a specific role"""
        return self.user_roles.filter(role__code=role_code, role__is_active=True).exists()

    def has_permission(self, permission_code):
        """Check if user has a specific permission through any of their roles"""
        user_role_ids = self.user_roles.filter(role__is_active=True).values_list('role_id', flat=True)
        return Permission.objects.filter(
            roles__id__in=user_role_ids,
            code=permission_code,
            is_active=True
        ).exists()

    def has_any_permission(self, permission_codes):
        """Check if user has any of the given permissions"""
        if not isinstance(permission_codes, list):
            permission_codes = [permission_codes]
        for code in permission_codes:
            if self.has_permission(code):
                return True
        return False

    def get_role_codes(self):
        """Get list of role codes assigned to this user"""
        return list(
            self.user_roles.filter(role__is_active=True)
            .values_list('role__code', flat=True)
        )

    def get_all_permissions(self, obj=None):
        """
        Get all permission codes for this user
        Returns Django permissions in format 'app.codename' for admin compatibility
        Filters out custom RBAC permissions to prevent Jazzmin errors
        """
        if self.is_superuser:
            # Superuser has all permissions
            from django.contrib.auth.models import Permission as DjangoPermission
            return set(f"{p.content_type.app_label}.{p.codename}"
                      for p in DjangoPermission.objects.select_related('content_type'))

        # Get Django's built-in permissions only
        user_perms = set()

        # User permissions
        for perm in self.user_permissions.select_related('content_type'):
            user_perms.add(f"{perm.content_type.app_label}.{perm.codename}")

        # Group permissions
        for group in self.groups.all():
            for perm in group.permissions.select_related('content_type'):
                user_perms.add(f"{perm.content_type.app_label}.{perm.codename}")

        # Filter to ensure all have dots (Jazzmin compatibility)
        return {p for p in user_perms if '.' in p}

    def is_account_locked(self):
        """Check if account is currently locked"""
        if self.account_locked_until:
            if timezone.now() < self.account_locked_until:
                return True
            else:
                # Auto-unlock if lock period has expired
                self.account_locked_until = None
                self.failed_login_attempts = 0
                self.save()
        return False


class UserRole(models.Model):
    """
    Many-to-many mapping between Users and Roles
    Allows users to have multiple roles and tracks assignment history
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='user_roles'
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name='role_users'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.CharField(
        max_length=200,
        blank=True,
        help_text="User who assigned this role"
    )
    valid_from = models.DateTimeField(
        default=timezone.now,
        help_text="Role valid from this date"
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Role valid until this date (null = indefinite)"
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Whether this is the user's primary role"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about this role assignment"
    )

    class Meta:
        db_table = 'user_role'
        unique_together = [['user', 'role']]
        verbose_name = 'User Role'
        verbose_name_plural = 'User Roles'

    def __str__(self):
        return f"{self.user.get_display_name()} - {self.role.name}"

    def is_valid(self):
        """Check if this role assignment is currently valid"""
        now = timezone.now()
        if self.valid_until:
            return self.valid_from <= now <= self.valid_until
        return self.valid_from <= now


class AuditLog(models.Model):
    """
    Comprehensive audit logging for all system actions
    Tracks both application-level and user-level activities
    """
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('READ', 'Read'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('APPROVE', 'Approve'),
        ('REJECT', 'Reject'),
        ('SUBMIT', 'Submit'),
        ('CANCEL', 'Cancel'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('LOGIN_FAILED', 'Login Failed'),
        ('PASSWORD_CHANGE', 'Password Change'),
        ('PERMISSION_GRANTED', 'Permission Granted'),
        ('PERMISSION_REVOKED', 'Permission Revoked'),
        ('EXPORT', 'Export'),
        ('IMPORT', 'Import'),
        ('OTHER', 'Other'),
    ]

    LEVEL_CHOICES = [
        ('USER', 'User Level'),
        ('APPLICATION', 'Application Level'),
        ('SYSTEM', 'System Level'),
    ]

    # Basic Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # User Information
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text="User who performed the action"
    )
    username = models.CharField(
        max_length=200,
        help_text="Username at time of action (preserved even if user deleted)"
    )
    user_full_name = models.CharField(
        max_length=300,
        blank=True,
        help_text="User's full name at time of action"
    )
    user_employee_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Employee ID at time of action"
    )

    # Action Information
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        db_index=True,
        help_text="Type of action performed"
    )
    level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES,
        default='USER',
        db_index=True,
        help_text="Level of audit (user/application/system)"
    )
    category = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Category of the action (e.g., 'order', 'portfolio', 'user')"
    )
    description = models.TextField(
        help_text="Human-readable description of the action"
    )

    # Object Information
    object_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Type of object affected (model name)"
    )
    object_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="ID of the affected object"
    )
    object_repr = models.TextField(
        blank=True,
        help_text="String representation of the object"
    )

    # Change Tracking
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Details of changes made (before/after values)"
    )

    # Request Information
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the request"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Browser user agent string"
    )
    request_method = models.CharField(
        max_length=10,
        blank=True,
        help_text="HTTP request method (GET, POST, etc.)"
    )
    request_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL path of the request"
    )

    # Result Information
    success = models.BooleanField(
        default=True,
        help_text="Whether the action succeeded"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if action failed"
    )

    # Additional Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata as JSON"
    )

    class Meta:
        db_table = 'audit_log'
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['-timestamp', 'user']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['category', '-timestamp']),
            models.Index(fields=['level', '-timestamp']),
            models.Index(fields=['object_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {self.username} - {self.action} - {self.description}"

    @classmethod
    def log_action(cls, user, action, description, **kwargs):
        """
        Convenience method to create audit log entries
        Usage: AuditLog.log_action(request.user, 'CREATE', 'Created new order', category='order', ...)
        """
        log_data = {
            'user': user if not isinstance(user, str) else None,
            'username': user.username if hasattr(user, 'username') else str(user),
            'action': action,
            'description': description,
        }

        # Add user details if user object available
        if hasattr(user, 'full_name'):
            log_data['user_full_name'] = user.full_name
        if hasattr(user, 'employee_id'):
            log_data['user_employee_id'] = user.employee_id or ''

        # Add any additional kwargs
        log_data.update(kwargs)

        return cls.objects.create(**log_data)
