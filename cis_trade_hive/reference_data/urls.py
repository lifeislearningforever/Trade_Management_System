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
    path('counterparty/create/', views.counterparty_create, name='counterparty_create'),
    path('counterparty/<str:short_name>/edit/', views.counterparty_edit, name='counterparty_edit'),
    path('counterparty/<str:short_name>/delete/', views.counterparty_delete, name='counterparty_delete'),
    path('counterparty/<str:short_name>/restore/', views.counterparty_restore, name='counterparty_restore'),

    # Counterparty CIF URLs (AJAX API)
    path('counterparty/<str:short_name>/cif/', views.counterparty_cif_list, name='counterparty_cif_list'),
    path('counterparty/<str:short_name>/cif/create/', views.counterparty_cif_create, name='counterparty_cif_create'),
    path('counterparty/<str:short_name>/cif/<str:m_label>/update/', views.counterparty_cif_update, name='counterparty_cif_update'),
    path('counterparty/<str:short_name>/cif/<str:m_label>/delete/', views.counterparty_cif_delete, name='counterparty_cif_delete'),
]
