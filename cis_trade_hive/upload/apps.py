"""
Upload App Configuration

File upload and ingestion into Hive external tables.
"""

from django.apps import AppConfig


class UploadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "upload"
    verbose_name = "File Upload Management"
