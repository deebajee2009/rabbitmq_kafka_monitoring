from django.db import models

class MetricSnapshot(models.Model):
    METRIC_TYPES = [
        ('kafka_broker', 'Kafka Broker'),
        ('kafka_topic', 'Kafka Topic'),
        ('kafka_consumer', 'Kafka Consumer'),
        ('rabbitmq_queue', 'RabbitMQ Queue'),
        ('rabbitmq_connection', 'RabbitMQ Connection'),
    ]

    metric_type = models.CharField(max_length=50, choices=METRIC_TYPES)
    name = models.CharField(max_length=255)  # broker_id, topic_name, queue_name, etc.
    metrics_data = models.JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['metric_type', 'name', 'timestamp']),
        ]
