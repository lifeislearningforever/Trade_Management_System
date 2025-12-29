"""
Reference Data URLs
"""

from django.urls import path
from . import views

app_name = 'reference_data'

urlpatterns = [
    # Currency URLs
    path('currency/', views.currency_list, name='currency_list'),

    # Country URLs
    path('country/', views.country_list, name='country_list'),

    # Calendar URLs
    path('calendar/', views.calendar_list, name='calendar_list'),

    # Counterparty URLs
    path('counterparty/', views.counterparty_list, name='counterparty_list'),
]
