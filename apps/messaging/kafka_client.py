import json
import logging
import threading
import time
from typing import Dict, List, Optional, Callable
from kafka import KafkaProducer, KafkaConsumer, KafkaAdminClient
from kafka.admin import ConfigResource, ConfigResourceType
from kafka.errors import KafkaError
from django.conf import settings
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger('kafka')

# Prometheus metrics
kafka_messages_sent = Counter('kafka_messages_sent_total', 'Total messages sent to Kafka', ['topic'])
kafka_messages_received = Counter('kafka_messages_received_total', 'Total messages received from Kafka', ['topic', 'consumer_group'])
kafka_send_duration = Histogram('kafka_send_duration_seconds', 'Time spent sending messages to Kafka', ['topic'])
kafka_consumer_lag = Gauge('kafka_consumer_lag', 'Consumer lag for Kafka topics', ['topic', 'partition', 'consumer_group'])
kafka_broker_status = Gauge('kafka_broker_status', 'Kafka broker status', ['broker_id'])
kafka_topic_partitions = Gauge('kafka_topic_partitions', 'Number of partitions per topic', ['topic'])

class KafkaClient:
    def __init__(self):
        self.producer = None
        self.consumers = {}
        self.admin_client = None
        self._initialize_clients()
        self.running_consumers = {}

    def _initialize_clients(self):
        """Initialize Kafka clients with error handling"""
        try:
            self.producer = KafkaProducer(
                **settings.KAFKA_CONFIG['producer_config'],
                bootstrap_servers=settings.KAFKA_CONFIG['bootstrap_servers'],
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None
            )

            self.admin_client = KafkaAdminClient(
                bootstrap_servers=settings.KAFKA_CONFIG['bootstrap_servers']
            )

            logger.info("Kafka clients initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka clients: {e}")
            raise

    def send_message(self, topic: str, message: Dict, key: Optional[str] = None) -> bool:
        """Send message to Kafka topic with metrics"""
        if not self.producer:
            logger.error("Kafka producer not initialized")
            return False

        try:
            with kafka_send_duration.labels(topic=topic).time():
                future = self.producer.send(topic, value=message, key=key)
                record_metadata = future.get(timeout=10)

            kafka_messages_sent.labels(topic=topic).inc()

            logger.info(f"Message sent to topic {topic}, partition {record_metadata.partition}, offset {record_metadata.offset}")
            return True

        except KafkaError as e:
            logger.error(f"Failed to send message to topic {topic}: {e}")
            return False

    def create_consumer(self, topics: List[str], consumer_group: str = None) -> KafkaConsumer:
        """Create a Kafka consumer for specified topics"""
        consumer_config = settings.KAFKA_CONFIG['consumer_config'].copy()
        if consumer_group:
            consumer_config['group_id'] = consumer_group

        try:
            consumer = KafkaConsumer(
                *topics,
                **consumer_config,
                bootstrap_servers=settings.KAFKA_CONFIG['bootstrap_servers'],
                value_deserializer=lambda m: json.loads(m.decode('utf-8')) if m else None
            )

            consumer_id = f"{consumer_group or 'default'}_{'-'.join(topics)}"
            self.consumers[consumer_id] = consumer

            logger.info(f"Consumer created for topics {topics} with group {consumer_group}")
            return consumer

        except Exception as e:
            logger.error(f"Failed to create consumer: {e}")
            raise

    def start_consumer(self, topics: List[str], callback: Callable, consumer_group: str = None):
        """Start consuming messages in a separate thread"""
        consumer = self.create_consumer(topics, consumer_group)
        consumer_id = f"{consumer_group or 'default'}_{'-'.join(topics)}"

        def consume_messages():
            try:
                for message in consumer:
                    if consumer_id not in self.running_consumers:
                        break

                    kafka_messages_received.labels(
                        topic=message.topic,
                        consumer_group=consumer_group or 'default'
                    ).inc()

                    try:
                        callback(message)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")

            except Exception as e:
                logger.error(f"Consumer error: {e}")
            finally:
                consumer.close()

        thread = threading.Thread(target=consume_messages, daemon=True)
        self.running_consumers[consumer_id] = thread
        thread.start()

        logger.info(f"Started consumer thread for topics {topics}")

    def stop_consumer(self, topics: List[str], consumer_group: str = None):
        """Stop a running consumer"""
        consumer_id = f"{consumer_group or 'default'}_{'-'.join(topics)}"

        if consumer_id in self.running_consumers:
            del self.running_consumers[consumer_id]
            logger.info(f"Stopped consumer for topics {topics}")

    def get_topic_metadata(self) -> Dict:
        """Get metadata about Kafka topics for monitoring"""
        try:
            metadata = self.producer.bootstrap_connected()
            cluster_metadata = self.admin_client.describe_cluster()

            topics_metadata = self.admin_client.list_topics()

            result = {
                'cluster_id': cluster_metadata.cluster_id if hasattr(cluster_metadata, 'cluster_id') else 'unknown',
                'topics': {},
                'brokers': []
            }

            # Update topic partitions metric
            for topic in topics_metadata:
                topic_metadata = self.admin_client.describe_topics([topic])
                if topic in topic_metadata:
                    partitions_count = len(topic_metadata[topic].partitions)
                    kafka_topic_partitions.labels(topic=topic).set(partitions_count)
                    result['topics'][topic] = {
                        'partitions': partitions_count,
                        'replication_factor': len(topic_metadata[topic].partitions[0].replicas) if topic_metadata[topic].partitions else 0
                    }

            return result

        except Exception as e:
            logger.error(f"Failed to get topic metadata: {e}")
            return {}

    def get_consumer_lag(self, consumer_group: str) -> Dict:
        """Get consumer lag information for monitoring"""
        try:
            # This is a simplified version - in production you'd use Kafka's consumer group API
            lag_info = {}

            # For demonstration, we'll return mock data structure
            # In real implementation, you'd query Kafka's consumer group metadata
            consumer = KafkaConsumer(
                group_id=consumer_group,
                bootstrap_servers=settings.KAFKA_CONFIG['bootstrap_servers']
            )

            # Get committed offsets for the consumer group
            committed = consumer.committed(consumer.assignment())

            for tp in consumer.assignment():
                high_water_mark = consumer.highwater(tp)
                committed_offset = committed.get(tp, 0)
                lag = high_water_mark - committed_offset

                kafka_consumer_lag.labels(
                    topic=tp.topic,
                    partition=tp.partition,
                    consumer_group=consumer_group
                ).set(lag)

                lag_info[f"{tp.topic}-{tp.partition}"] = lag

            consumer.close()
            return lag_info

        except Exception as e:
            logger.error(f"Failed to get consumer lag: {e}")
            return {}

    def close(self):
        """Close all Kafka connections"""
        if self.producer:
            self.producer.close()

        for consumer in self.consumers.values():
            consumer.close()

        # Stop all running consumers
        for consumer_id in list(self.running_consumers.keys()):
            self.stop_consumer(consumer_id.split('_')[1:], consumer_id.split('_')[0])

# Global Kafka client instance
kafka_client = KafkaClient()
