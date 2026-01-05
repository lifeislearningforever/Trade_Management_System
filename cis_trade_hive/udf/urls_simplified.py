"""
UDF URL Configuration - Simplified Free Text Approach
"""

from django.urls import path
from . import views_simplified as views

app_name = 'udf'

urlpatterns = [
    # Dashboard
    path('', views.udf_dashboard, name='dashboard'),

    # List View
    path('list/', views.udf_list, name='list'),

    # Create/Edit/Delete
    path('create/', views.udf_create, name='create'),
    path('<int:udf_id>/edit/', views.udf_edit, name='edit'),
    path('<int:udf_id>/delete/', views.udf_delete, name='delete'),
    path('<int:udf_id>/restore/', views.udf_restore, name='restore'),

    # API Endpoints for Cascading Dropdowns
    path('api/object-types/', views.api_get_object_types, name='api_object_types'),
    path('api/fields/<str:object_type>/', views.api_get_fields_by_entity, name='api_fields_by_object_new'),

    # Legacy API Endpoint (for backward compatibility)
    path('api/<str:object_type>/fields/', views.udf_get_fields_by_entity, name='api_fields_by_object'),
]
