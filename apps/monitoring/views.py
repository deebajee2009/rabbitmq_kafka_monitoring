from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from .models import MetricSnapshot
from .collectors import metrics_collector
import logging

logger = logging.getLogger('monitoring')

@api_view(['GET'])
def current_metrics(request):
    """Get current metrics for all systems"""
    try:
        metrics = metrics_collector.collect_all_metrics()
        return Response(metrics)
    except Exception as e:
        logger.error(f"Error collecting current metrics: {e}")
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def kafka_dashboard_metrics(request):
    """Get Kafka-specific metrics for dashboard"""
    return Response({
        'broker': metrics_collector.collect_kafka_broker_metrics(),
        'topics': metrics_collector.collect_kafka_topic_metrics(),
        'consumers': metrics_collector.collect_kafka_consumer_metrics()
    })

@api_view(['GET'])
def rabbitmq_dashboard_metrics(request):
    """Get RabbitMQ-specific metrics for dashboard"""
    return Response(metrics_collector.collect_rabbitmq_metrics())

@api_view(['GET'])
def historical_metrics(request):
    """Get historical metrics for a specific time range"""
    hours = int(request.GET.get('hours', 24))
    metric_type = request.GET.get('type', None)

    since = timezone.now() - timedelta(hours=hours)

    queryset = MetricSnapshot.objects.filter(timestamp__gte=since)
    if metric_type:
        queryset = queryset.filter(metric_type=metric_type)

    metrics_data = {}
    for snapshot in queryset.order_by('timestamp'):
        key = f"{snapshot.metric_type}_{snapshot.name}"
        if key not in metrics_data:
            metrics_data[key] = []

        metrics_data[key].append({
            'timestamp': snapshot.timestamp.isoformat(),
            'data': snapshot.metrics_data
        })

    return Response(metrics_data)
