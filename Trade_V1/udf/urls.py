from django.urls import path
from . import views

urlpatterns = [
    path('types/', views.udf_type_list, name='udf_type_list'),
    path('types/create/', views.udf_type_create, name='udf_type_create'),
    path('types/<int:pk>/edit/', views.udf_type_edit, name='udf_type_edit'),
]
