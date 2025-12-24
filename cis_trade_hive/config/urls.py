"""
CisTrade - Main URL Configuration
Professional Trade Management System - No Authentication
"""

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

# Simple home view
def home_view(request):
    return HttpResponse("""
    <html>
    <head><title>CisTrade - Trade Management System</title></head>
    <body style="font-family: Arial, sans-serif; margin: 40px;">
        <h1>CisTrade - Trade Management System</h1>
        <p>Welcome to CisTrade. The system is connected to Hive database.</p>
        <ul>
            <li><a href="/reference-data/">Reference Data</a></li>
            <li><a href="/portfolio/">Portfolio</a></li>
            <li><a href="/udf/">UDF Management</a></li>
        </ul>
    </body>
    </html>
    """)

urlpatterns = [
    # Home
    path('', home_view, name='home'),

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
