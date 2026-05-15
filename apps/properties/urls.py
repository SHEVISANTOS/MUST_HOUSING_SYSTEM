from django.urls import path
from . import views

app_name = 'properties'
urlpatterns = [
    path('', views.property_list, name='list'),
    path('<int:pk>/', views.property_detail, name='detail'),
    path('create/', views.property_create, name='create'),
    
]