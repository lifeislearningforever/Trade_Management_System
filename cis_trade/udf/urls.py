"""
UDF URL Configuration
"""

from django.urls import path
from . import views

app_name = 'udf'

urlpatterns = [
    # UDF Definition URLs
    path('', views.udf_list, name='list'),
    path('create/', views.udf_create, name='create'),
    path('<int:pk>/', views.udf_detail, name='detail'),
    path('<int:pk>/edit/', views.udf_edit, name='edit'),
    path('<int:pk>/delete/', views.udf_delete, name='delete'),

    # UDF Value Management URLs
    path('values/<str:entity_type>/<int:entity_id>/', views.entity_udf_values, name='entity_values'),
    path('values/<str:entity_type>/<int:entity_id>/history/', views.udf_value_history, name='value_history'),

    # AJAX URLs
    path('ajax/values/<str:entity_type>/<int:entity_id>/', views.ajax_get_entity_udf_values, name='ajax_get_values'),
    path('ajax/validate/', views.ajax_validate_udf_values, name='ajax_validate'),
]
