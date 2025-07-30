import psutil
import time
import logging
from typing import Dict, Any
from django.conf import settings
from prometheus_client import Gauge, Counter, Histogram
from .models import MetricSnapshot
from apps.messaging.kafka_client import kafka_client
from apps.messaging.rabbitmq_client import rabbitmq_client

logger = logging.getLogger('monitoring')

# System metrics
system_cpu_usage = Gauge('system_cpu_usage_percent', 'System CPU usage percentage')
system_memory_usage = Gauge('system_memory_usage_percent', 'System memory usage percentage')
system_disk_usage = Gauge('system_disk_usage_percent', 'System disk usage percentage', ['path'])

class MetricsCollector:
    """Collect and store metrics for monitoring"""

    def __init__(self):
        self.last_collection = time.time()

    def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect system-level metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            system_cpu_usage.set(cpu_percent)
            system_memory_usage.set(memory.percent)
            system_disk_usage.labels(path='/').set(disk.percent)

            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_total': memory.total,
                'memory_used': memory.used,
                'disk_percent': disk.percent,
                'disk_total': disk.total,
                'disk_used': disk.used,
                'timestamp': time.time()
            }

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return {}

    def collect_kafka_broker_metrics(self) -> Dict[str, Any]:
        """Collect Kafka broker metrics"""
        try:
            metadata = kafka_client.get_topic_metadata()
            system_metrics = self.collect_system_metrics()

            broker_metrics = {
                'cluster_id': metadata.get('cluster_id', 'unknown'),
                'topics_count': len(metadata.get('topics', {})),
                'total_partitions': sum(
                    topic_info.get('partitions', 0)
                    for topic_info in metadata.get('topics', {}).values()
                ),
                'system_metrics': system_metrics,
                'online_status': 1,  # 1 if connected, 0 if not
                'timestamp': time.time()
            }

            # Store snapshot
            MetricSnapshot.objects.create(
                metric_type='kafka_broker',
                name='main_cluster',
                metrics_data=broker_metrics
            )

            return broker_metrics

        except Exception as e:
            logger.error(f"Error collecting Kafka broker metrics: {e}")
            return {'online_status': 0, 'error': str(e)}

    def collect_kafka_topic_metrics(self) -> Dict[str, Any]:
        """Collect metrics for each Kafka topic"""
        try:
            metadata = kafka_client.get_topic_metadata()
            topic_metrics = {}

            for topic_name, topic_info in metadata.get('topics', {}).items():
                metrics = {
                    'partitions_count': topic_info.get('partitions', 0),
                    'replication_factor': topic_info.get('replication_factor', 0),
                    'timestamp': time.time()
                }

                topic_metrics[topic_name] = metrics

                # Store snapshot for each topic
                MetricSnapshot.objects.create(
                    metric_type='kafka_topic',
                    name=topic_name,
                    metrics_data=metrics
                )

            return topic_metrics

        except Exception as e:
            logger.error(f"Error collecting Kafka topic metrics: {e}")
            return {}

    def collect_kafka_consumer_metrics(self) -> Dict[str, Any]:
        """Collect Kafka consumer group metrics"""
        try:
            from messaging.models import ConsumerGroup

            consumer_metrics = {}
            consumer_groups = ConsumerGroup.objects.filter(is_active=True)

            for group in consumer_groups:
                lag_info = kafka_client.get_consumer_lag(group.name)

                metrics = {
                    'group_name': group.name,
                    'topics': group.topics,
                    'total_lag': sum(lag_info.values()) if lag_info else 0,
                    'partitions_lag': lag_info,
                    'is_active': group.is_active,
                    'timestamp': time.time()
                }

                consumer_metrics[group.name] = metrics

                # Store snapshot
                MetricSnapshot.objects.create(
                    metric_type='kafka_consumer',
                    name=group.name,
                    metrics_data=metrics
                )

            return consumer_metrics

        except Exception as e:
            logger.error(f"Error collecting Kafka consumer metrics: {e}")
            return {}

    def collect_rabbitmq_metrics(self) -> Dict[str, Any]:
        """Collect RabbitMQ metrics"""
        try:
            queues_info = rabbitmq_client.get_all_queues_info()
            system_metrics = self.collect_system_metrics()

            rabbitmq_metrics = {
                'queues': queues_info,
                'total_queues': len(queues_info),
                'total_messages': sum(
                    queue_info.get('messages', 0)
                    for queue_info in queues_info.values()
                ),
                'total_consumers': sum(
                    queue_info.get('consumers', 0)
                    for queue_info in queues_info.values()
                ),
                'system_metrics': system_metrics,
                'connection_status': 1,  # 1 if connected, 0 if not
                'timestamp': time.time()
            }

            # Store individual queue metrics
            for queue_name, queue_info in queues_info.items():
                MetricSnapshot.objects.create(
                    metric_type='rabbitmq_queue',
                    name=queue_name,
                    metrics_data=queue_info
                )

            # Store overall RabbitMQ connection metrics
            MetricSnapshot.objects.create(
                metric_type='rabbitmq_connection',
                name='main_connection',
                metrics_data=rabbitmq_metrics
            )

            return rabbitmq_metrics

        except Exception as e:
            logger.error(f"Error collecting RabbitMQ metrics: {e}")
            return {'connection_status': 0, 'error': str(e)}

    def collect_all_metrics(self) -> Dict[str, Any]:
        """Collect all metrics at once"""
        return {
            'system': self.collect_system_metrics(),
            'kafka_broker': self.collect_kafka_broker_metrics(),
            'kafka_topics': self.collect_kafka_topic_metrics(),
            'kafka_consumers': self.collect_kafka_consumer_metrics(),
            'rabbitmq': self.collect_rabbitmq_metrics(),
            'collection_timestamp': time.time()
        }

# Global metrics collector instance
metrics_collector = MetricsCollector()
