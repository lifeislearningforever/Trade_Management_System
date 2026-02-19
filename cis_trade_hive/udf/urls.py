"""
UDF URL Configuration

Single table CRUD operations for cis_udf_field:
- List, Create, Detail, Edit, Delete, Restore
- API endpoints for AJAX operations
"""

from django.urls import path
from . import views

app_name = 'udf'

urlpatterns = [
    # UDF Field CRUD
    path('', views.udf_list, name='list'),
    path('create/', views.udf_create, name='create'),
    path('<str:field_id>/', views.udf_detail, name='detail'),
    path('<str:field_id>/edit/', views.udf_edit, name='edit'),
    path('<str:field_id>/delete/', views.udf_delete, name='delete'),
    path('<str:field_id>/restore/', views.udf_restore, name='restore'),

    # Statistics Dashboard
    path('dashboard/statistics/', views.udf_statistics, name='statistics'),

    # API Endpoints
    path('api/object-types/', views.api_get_object_types, name='api_object_types'),
    path('api/fields/<str:object_type>/', views.api_get_fields_by_object_type, name='api_fields_by_type'),
    path('api/field/<str:field_id>/', views.api_get_field, name='api_field'),
    path('api/statistics/', views.api_get_statistics, name='api_statistics'),
]
