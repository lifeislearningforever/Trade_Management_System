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

    # Counterparty URLs (legacy - kept for backward compatibility)
    path('counterparty/', views.counterparty_list, name='counterparty_list'),
    path('counterparty/create/', views.counterparty_create, name='counterparty_create'),
    path('counterparty/<str:short_name>/', views.counterparty_detail, name='counterparty_detail'),
    path('counterparty/<str:short_name>/edit/', views.counterparty_edit, name='counterparty_edit'),
    path('counterparty/<str:short_name>/delete/', views.counterparty_delete, name='counterparty_delete'),
    path('counterparty/<str:short_name>/restore/', views.counterparty_restore, name='counterparty_restore'),

    # Counterparty CIF URLs (AJAX API) - legacy
    path('counterparty/<str:short_name>/cif/', views.counterparty_cif_list, name='counterparty_cif_list'),
    path('counterparty/<str:short_name>/cif/create/', views.counterparty_cif_create, name='counterparty_cif_create'),
    path('counterparty/<str:short_name>/cif/<str:m_label>/update/', views.counterparty_cif_update, name='counterparty_cif_update'),
    path('counterparty/<str:short_name>/cif/<str:m_label>/delete/', views.counterparty_cif_delete, name='counterparty_cif_delete'),

    # Party URLs (new naming - uses cis_party and cis_party_cif tables)
    path('party/', views.party_list, name='party_list'),
    path('party/create/', views.party_create, name='party_create'),
    path('party/pending/', views.party_pending_approvals, name='party_pending_approvals'),
    path('party/<str:short_name>/', views.party_detail, name='party_detail'),
    path('party/<str:short_name>/edit/', views.party_edit, name='party_edit'),
    path('party/<str:short_name>/delete/', views.party_delete, name='party_delete'),
    path('party/<str:short_name>/restore/', views.party_restore, name='party_restore'),
    path('party/<str:short_name>/validate/', views.party_validate, name='party_validate'),

    # Party CIF URLs (AJAX API)
    path('party/<str:short_name>/cif/', views.party_cif_list, name='party_cif_list'),
    path('party/<str:short_name>/cif/create/', views.party_cif_create, name='party_cif_create'),
    path('party/<str:short_name>/cif/<str:m_label>/update/', views.party_cif_update, name='party_cif_update'),
    path('party/<str:short_name>/cif/<str:m_label>/delete/', views.party_cif_delete, name='party_cif_delete'),
]
