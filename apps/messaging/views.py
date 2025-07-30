from rest_framework import status, generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from .kafka_client import kafka_client
from .rabbitmq_client import rabbitmq_client
import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
def kafka_metrics(request):
    """Get Kafka metrics for monitoring"""
    try:
        metadata = kafka_client.get_topic_metadata()

        # Get consumer lag for active consumer groups
        consumer_groups = ConsumerGroup.objects.filter(is_active=True)
        lag_info = {}

        for group in consumer_groups:
            lag_info[group.name] = kafka_client.get_consumer_lag(group.name)

        return Response({
            'cluster_metadata': metadata,
            'consumer_lag': lag_info,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting Kafka metrics: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def rabbitmq_metrics(request):
    """Get RabbitMQ metrics for monitoring"""
    try:
        queues_info = rabbitmq_client.get_all_queues_info()

        return Response({
            'queues': queues_info,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting RabbitMQ metrics: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
