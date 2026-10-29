"""
Upload URL Configuration

Routes for file upload and Hive ingestion functionality.
"""

from django.urls import path
from . import views

app_name = 'upload'

urlpatterns = [
    # List and Dashboard
    path('', views.upload_list, name='list'),
    path('dashboard/', views.upload_dashboard, name='dashboard'),

    # Create (Upload)
    path('create/', views.upload_create, name='create'),

    # Detail, Preview, Edit
    path('<str:upload_id>/', views.upload_detail, name='detail'),
    path('<str:upload_id>/preview/', views.upload_preview, name='preview'),
    path('<str:upload_id>/schema/', views.upload_update_schema, name='update_schema'),

    # Actions
    path('<str:upload_id>/ingest/', views.upload_ingest, name='ingest'),
    path('<str:upload_id>/delete/', views.upload_delete, name='delete'),

    # Position Upload ETL
    path('<str:upload_id>/run-position/', views.run_position_etl, name='run_position'),
    path('<str:upload_id>/download-report/', views.download_position_report, name='download_position_report'),

    # API Endpoints
    path('api/validate/', views.api_validate_file, name='api_validate'),
    path('api/<str:upload_id>/status/', views.api_upload_status, name='api_status'),
    path('api/<str:upload_id>/cancel-etl/', views.api_cancel_etl, name='api_cancel_etl'),
    path('api/<str:upload_id>/preview/', views.api_table_preview, name='api_preview'),
    path('api/<str:upload_id>/reconciliation/', views.api_reconciliation, name='api_reconciliation'),
]
