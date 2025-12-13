from django.urls import path
from . import views

urlpatterns = [
    # Currency
    path('currency/', views.currency_list, name='currency_list'),
    path('currency/<str:code>/', views.currency_detail, name='currency_detail'),

    # Broker
    path('broker/', views.broker_list, name='broker_list'),
    path('broker/create/', views.broker_create, name='broker_create'),
    path('broker/<int:pk>/', views.broker_detail, name='broker_detail'),
    path('broker/<int:pk>/edit/', views.broker_edit, name='broker_edit'),

    # Trading Calendar
    path('calendar/', views.calendar_list, name='calendar_list'),

    # Client
    path('client/', views.client_list, name='client_list'),
    path('client/create/', views.client_create, name='client_create'),
    path('client/<int:pk>/', views.client_detail, name='client_detail'),
    path('client/<int:pk>/edit/', views.client_edit, name='client_edit'),
]
