from django.urls import path
from . import views

app_name = 'properties'

urlpatterns = [
    
    path('', views.property_list, name='list'),
    path('create/', views.property_create, name='create'),
    path('my-properties/', views.my_properties, name='my_properties'),
    
    
    path('<int:pk>/', views.property_detail, name='detail'),
    
]