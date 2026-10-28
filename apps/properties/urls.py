from django.urls import path
from . import views

app_name = 'properties'

urlpatterns = [
    
    path('', views.property_list, name='list'),
    path('create/', views.property_create, name='create'),
    path('my-properties/', views.my_properties, name='my_properties'),
    path('saved/', views.saved_properties, name='saved'),

    # 🧙 5-step add/edit wizard
    path('wizard/new/', views.property_wizard_start, name='wizard_start'),
    path('wizard/<int:pk>/<str:step>/', views.property_wizard_step, name='wizard_step'),
    path('wizard/<int:pk>/photos/delete/<int:image_id>/', views.property_wizard_delete_image, name='wizard_delete_image'),

    path('<int:pk>/', views.property_detail, name='detail'),
    path('<int:pk>/edit/', views.property_edit, name='edit'),
    path('<int:pk>/pause/', views.property_pause, name='pause'),
    path('<int:pk>/save/', views.toggle_saved, name='toggle_saved'),

]