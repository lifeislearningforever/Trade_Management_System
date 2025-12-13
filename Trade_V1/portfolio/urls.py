from django.urls import path
from . import views

urlpatterns = [
    path('', views.portfolio_list, name='portfolio_list'),
    path('create/', views.portfolio_create, name='portfolio_create'),
    path('<int:pk>/', views.portfolio_detail, name='portfolio_detail'),
    path('<int:pk>/edit/', views.portfolio_edit, name='portfolio_edit'),
    path('<int:pk>/submit/', views.portfolio_submit, name='portfolio_submit'),
    path('<int:pk>/approve/', views.portfolio_approve, name='portfolio_approve'),
    path('<int:pk>/reject/', views.portfolio_reject, name='portfolio_reject'),
]
