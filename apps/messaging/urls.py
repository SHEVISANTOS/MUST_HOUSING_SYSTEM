from django.urls import path
from . import views

app_name = 'messaging'

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('start/<int:property_id>/', views.start_conversation, name='start_conversation'),
    path('<int:conversation_id>/', views.thread, name='thread'),
]
