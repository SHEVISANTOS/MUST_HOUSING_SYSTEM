from django.urls import path
from . import views

app_name = 'properties'

urlpatterns = [
    
    path('', views.property_list, name='list'),
    path('create/', views.property_create, name='create'),
    path('my-properties/', views.my_properties, name='my_properties'),
    path('saved/', views.saved_properties, name='saved'),


    path('<int:pk>/', views.property_detail, name='detail'),
    path('<int:pk>/edit/', views.property_edit, name='edit'),
    path('<int:pk>/pause/', views.property_pause, name='pause'),
    path('<int:pk>/save/', views.toggle_saved, name='toggle_saved'),

]