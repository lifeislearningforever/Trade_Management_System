"""
Orders URL Configuration
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.order_list, name='order_list'),
    path('create/', views.order_create, name='order_create'),
    path('<uuid:pk>/', views.order_detail, name='order_detail'),
    path('<uuid:pk>/edit/', views.order_edit, name='order_edit'),
    path('<uuid:pk>/submit/', views.order_submit, name='order_submit'),
    path('<uuid:pk>/approve/', views.order_approve, name='order_approve'),
    path('<uuid:pk>/reject/', views.order_reject, name='order_reject'),
    path('<uuid:pk>/delete/', views.order_delete, name='order_delete'),
]
