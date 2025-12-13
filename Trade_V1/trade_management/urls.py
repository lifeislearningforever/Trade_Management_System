"""
URL configuration for trade_management project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import login_view, logout_view, dashboard_view

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # Authentication & Dashboard
    path('', include('accounts.urls')),
    path('', dashboard_view, name='home'),

    # Orders Module
    path('orders/', include('orders.urls')),

    # Portfolio Module
    path('portfolio/', include('portfolio.urls')),

    # UDF Module
    path('udf/', include('udf.urls')),

    # Reference Data Module
    path('reference/', include('reference_data.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
