"""
CisTrade - Main URL Configuration
Professional Trade Management System
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from core import views as core_views

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Authentication
    path('login/', core_views.user_login, name='login'),
    path('logout/', core_views.user_logout, name='logout'),
    path('profile/', core_views.profile, name='profile'),

    # Dashboard
    path('', core_views.dashboard, name='dashboard'),
    path('dashboard/', core_views.dashboard, name='dashboard_alt'),

    # Core
    path('core/', include('core.urls')),

    # Reference Data
    path('reference-data/', include('reference_data.urls')),

    # Portfolio
    path('portfolio/', include('portfolio.urls')),

    # UDF (User Defined Fields)
    path('udf/', include('udf.urls')),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
