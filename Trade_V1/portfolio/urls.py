from django.urls import path
from . import views

urlpatterns = [
    path('', views.portfolio_list, name='portfolio_list'),
    path('create/', views.portfolio_create, name='portfolio_create'),
    path('<uuid:pk>/', views.portfolio_detail, name='portfolio_detail'),
    path('<uuid:pk>/edit/', views.portfolio_edit, name='portfolio_edit'),
    path('<uuid:pk>/submit/', views.portfolio_submit, name='portfolio_submit'),
    path('<uuid:pk>/approve/', views.portfolio_approve, name='portfolio_approve'),
    path('<uuid:pk>/reject/', views.portfolio_reject, name='portfolio_reject'),
    path('<uuid:pk>/delete/', views.portfolio_delete, name='portfolio_delete'),
]
