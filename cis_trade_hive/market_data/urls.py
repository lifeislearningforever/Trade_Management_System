"""
Market Data URL Configuration
"""

from django.urls import path
from . import views

app_name = 'market_data'

urlpatterns = [
    # Market Data Dashboard (combined)
    path('dashboard/', views.market_data_dashboard, name='market_data_dashboard'),

    # FX Rates
    path('fx-rates/', views.fx_rate_list, name='fx_rate_list'),
    path('fx-rates/dashboard/', views.fx_rate_dashboard, name='fx_dashboard'),  # Backward compatibility
    path('fx-rates/<str:currency_pair>/', views.fx_rate_detail, name='fx_rate_detail'),

    # Equity Prices
    path('equity-prices/', views.equity_price_list, name='equity_price_list'),
    path('equity-prices/create/', views.equity_price_create, name='equity_price_create'),
    path('equity-prices/<int:equity_price_id>/edit/', views.equity_price_edit, name='equity_price_edit'),
]
