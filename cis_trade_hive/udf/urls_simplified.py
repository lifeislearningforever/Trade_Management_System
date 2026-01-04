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

    # API Endpoints
    path('api/<str:entity_type>/fields/', views.udf_get_fields_by_entity, name='api_fields_by_entity'),
]
