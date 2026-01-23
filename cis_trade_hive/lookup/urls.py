"""
Lookup Table URL Configuration
"""

from django.urls import path
from lookup import views

app_name = 'lookup'

urlpatterns = [
    # Table list (Configuration home)
    path('', views.LookupTableListView.as_view(), name='table_list'),

    # Table detail (row list with CRUD)
    path('table/<str:table_name>/', views.LookupTableDetailView.as_view(), name='table_detail'),

    # Row CRUD
    path('table/<str:table_name>/create/', views.LookupRowCreateView.as_view(), name='row_create'),
    path('table/<str:table_name>/edit/<str:pk_value>/', views.LookupRowEditView.as_view(), name='row_edit'),
    path('table/<str:table_name>/delete/<str:pk_value>/', views.LookupRowDeleteView.as_view(), name='row_delete'),

    # API endpoints
    path('api/table/<str:table_name>/', views.LookupTableAPIView.as_view(), name='api_table'),
    path('api/dropdown/<str:table_name>/', views.LookupDropdownAPIView.as_view(), name='api_dropdown'),
]
