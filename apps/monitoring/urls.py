from django.urls import path
from . import views

urlpatterns = [
    path('current/', views.current_metrics, name='current_metrics'),
    path('kafka/', views.kafka_dashboard_metrics, name='kafka_dashboard'),
    path('rabbitmq/', views.rabbitmq_dashboard_metrics, name='rabbitmq_dashboard'),
    path('historical/', views.historical_metrics, name='historical_metrics'),
]
