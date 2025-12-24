# udf/urls.py — Kudu-only routes (ordered correctly)
from django.urls import path
from udf import views

app_name = 'udf'

urlpatterns = [
    path('', views.udf_list, name='list'),
    path('create/', views.udf_create, name='create'),
    path('bulk-upload/', views.udf_bulk_upload, name='bulk_upload'),
    path('values/<str:entity_type>/<int:entity_id>/', views.entity_udf_values, name='entity_values'),
    # put catch-all routes last
    path('<str:field_name>/', views.udf_detail, name='detail'),
    path('<str:field_name>/edit/', views.udf_edit, name='edit'),
    path('<str:field_name>/delete/', views.udf_delete, name='delete'),
]
