"""
Market Data URL Configuration
"""

from django.urls import path
from . import views

app_name = 'market_data'

urlpatterns = [
    # FX Rates
    path('fx-rates/', views.fx_rate_list, name='fx_rate_list'),
    path('fx-rates/dashboard/', views.fx_rate_dashboard, name='fx_dashboard'),
    path('fx-rates/<str:currency_pair>/', views.fx_rate_detail, name='fx_rate_detail'),
]
