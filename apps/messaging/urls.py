# messaging/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('kafka/metrics/', views.kafka_metrics, name='kafka_metrics'),
    path('rabbitmq/metrics/', views.rabbitmq_metrics, name='rabbitmq_metrics'),
]
