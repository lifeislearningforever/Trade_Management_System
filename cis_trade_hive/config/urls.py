"""
CisTrade - Main URL Configuration
Professional Trade Management System - ACL-Based Authentication
"""

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

from core.views.auth_views import LoginView, LogoutView, auto_login_tmp3rc
from core.views.dashboard_views import dashboard_view, global_search_view

# Redirect home to auto-login (which will authenticate and redirect to dashboard)
def home_view(request):
    return redirect('auto_login')

urlpatterns = [
    # Home - redirect to dashboard or login
    path('', home_view, name='home'),

    # Authentication
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('auto-login/', auto_login_tmp3rc, name='auto_login'),

    # Dashboard
    path('dashboard/', dashboard_view, name='dashboard'),

    # Global Search
    path('search/', global_search_view, name='global_search'),

    # Core
    path('core/', include('core.urls')),

    # Reference Data
    path('reference-data/', include('reference_data.urls')),

    # Portfolio
    path('portfolio/', include('portfolio.urls')),

    # Market Data
    path('market-data/', include('market_data.urls')),

    # UDF (User Defined Fields)
    path('udf/', include('udf.urls')),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
