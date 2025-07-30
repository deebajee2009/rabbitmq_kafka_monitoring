import json
import logging
import pika
import threading
import time
from typing import Dict, Callable, Optional
from django.conf import settings
from prometheus_client import Counter, Histogram, Gauge
from pika.exceptions import AMQPConnectionError, AMQPChannelError

logger = logging.getLogger('rabbitmq')

# Prometheus metrics
rabbitmq_messages_sent = Counter('rabbitmq_messages_sent_total', 'Total messages sent to RabbitMQ', ['queue', 'exchange'])
rabbitmq_messages_received = Counter('rabbitmq_messages_received_total', 'Total messages received from RabbitMQ', ['queue'])
rabbitmq_send_duration = Histogram('rabbitmq_send_duration_seconds', 'Time spent sending messages to RabbitMQ', ['queue'])
rabbitmq_queue_messages = Gauge('rabbitmq_queue_messages', 'Number of messages in RabbitMQ queue', ['queue'])
rabbitmq_queue_consumers = Gauge('rabbitmq_queue_consumers', 'Number of consumers for RabbitMQ queue', ['queue'])
rabbitmq_connection_status = Gauge('rabbitmq_connection_status', 'RabbitMQ connection status')

class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.consumers = {}
        self.running_consumers = {}
        self._connect()

    def _connect(self):
        """Establish connection to RabbitMQ with retry logic"""
        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            try:
                credentials = pika.PlainCredentials(
                    settings.RABBITMQ_CONFIG['username'],
                    settings.RABBITMQ_CONFIG['password']
                )

                parameters = pika.ConnectionParameters(
                    host=settings.RABBITMQ_CONFIG['host'],
                    port=settings.RABBITMQ_CONFIG['port'],
                    virtual_host=settings.RABBITMQ_CONFIG['virtual_host'],
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300,
                )

                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()

                rabbitmq_connection_status.set(1)
                logger.info("Connected to RabbitMQ successfully")
                break

            except AMQPConnectionError as e:
                retry_count += 1
                rabbitmq_connection_status.set(0)
                logger.error(f"Failed to connect to RabbitMQ (attempt {retry_count}): {e}")

                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)  # Exponential backoff
                else:
                    raise

    def _ensure_connection(self):
        """Ensure connection is alive, reconnect if necessary"""
        if not self.connection or self.connection.is_closed:
            self._connect()
        elif not self.channel or self.channel.is_closed:
            self.channel = self.connection.channel()

    def declare_queue(self, queue_name: str, durable: bool = True, **kwargs):
        """Declare a queue with specified parameters"""
        try:
            self._ensure_connection()
            self.channel.queue_declare(queue=queue_name, durable=durable, **kwargs)
            logger.info(f"Queue '{queue_name}' declared successfully")
        except Exception as e:
            logger.error(f"Failed to declare queue '{queue_name}': {e}")
            raise

    def declare_exchange(self, exchange_name: str, exchange_type: str = 'direct', durable: bool = True):
        """Declare an exchange"""
        try:
            self._ensure_connection()
            self.channel.exchange_declare(
                exchange=exchange_name,
                exchange_type=exchange_type,
                durable=durable
            )
            logger.info(f"Exchange '{exchange_name}' declared successfully")
        except Exception as e:
            logger.error(f"Failed to declare exchange '{exchange_name}': {e}")
            raise

    def bind_queue(self, queue_name: str, exchange_name: str, routing_key: str = ''):
        """Bind queue to exchange with routing key"""
        try:
            self._ensure_connection()
            self.channel.queue_bind(
                exchange=exchange_name,
                queue=queue_name,
                routing_key=routing_key
            )
            logger.info(f"Queue '{queue_name}' bound to exchange '{exchange_name}' with key '{routing_key}'")
        except Exception as e:
            logger.error(f"Failed to bind queue '{queue_name}' to exchange '{exchange_name}': {e}")
            raise

    def send_message(self, queue_name: str, message: Dict, exchange: str = '', routing_key: str = None, **kwargs) -> bool:
        """Send message to RabbitMQ queue or exchange"""
        if routing_key is None:
            routing_key = queue_name

        try:
            self._ensure_connection()

            with rabbitmq_send_duration.labels(queue=queue_name).time():
                self.channel.basic_publish(
                    exchange=exchange,
                    routing_key=routing_key,
                    body=json.dumps(message),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # Make message persistent
                        content_type='application/json',
                        **kwargs
                    )
                )

            rabbitmq_messages_sent.labels(queue=queue_name, exchange=exchange).inc()
            logger.info(f"Message sent to queue '{queue_name}' via exchange '{exchange}'")
            return True

        except Exception as e:
            logger.error(f"Failed to send message to queue '{queue_name}': {e}")
            return False

    def start_consumer(self, queue_name: str, callback: Callable, auto_ack: bool = False, prefetch_count: int = 1):
        """Start consuming messages from a queue in a separate thread"""

        def consume_messages():
            try:
                # Create a new connection for this consumer thread
                consumer_connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=settings.RABBITMQ_CONFIG['host'],
                        port=settings.RABBITMQ_CONFIG['port'],
                        virtual_host=settings.RABBITMQ_CONFIG['virtual_host'],
                        credentials=pika.PlainCredentials(
                            settings.RABBITMQ_CONFIG['username'],
                            settings.RABBITMQ_CONFIG['password']
                        )
                    )
                )
                consumer_channel = consumer_connection.channel()
                consumer_channel.basic_qos(prefetch_count=prefetch_count)

                def message_callback(ch, method, properties, body):
                    try:
                        message = json.loads(body.decode('utf-8'))
                        rabbitmq_messages_received.labels(queue=queue_name).inc()

                        # Execute callback
                        callback(message, method, properties)

                        if not auto_ack:
                            ch.basic_ack(delivery_tag=method.delivery_tag)

                    except Exception as e:
                        logger.error(f"Error processing message from queue '{queue_name}': {e}")
                        if not auto_ack:
                            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

                consumer_channel.basic_consume(
                    queue=queue_name,
                    on_message_callback=message_callback,
                    auto_ack=auto_ack
                )

                logger.info(f"Started consuming from queue '{queue_name}'")

                while queue_name in self.running_consumers:
                    consumer_connection.process_data_events(time_limit=1)

            except Exception as e:
                logger.error(f"Consumer error for queue '{queue_name}': {e}")
            finally:
                if 'consumer_connection' in locals() and not consumer_connection.is_closed:
                    consumer_connection.close()
                logger.info(f"Stopped consumer for queue '{queue_name}'")

        if queue_name not in self.running_consumers:
            thread = threading.Thread(target=consume_messages, daemon=True)
            self.running_consumers[queue_name] = thread
            thread.start()
            logger.info(f"Started consumer thread for queue '{queue_name}'")

    def stop_consumer(self, queue_name: str):
        """Stop consuming from a queue"""
        if queue_name in self.running_consumers:
            del self.running_consumers[queue_name]
            logger.info(f"Signaled stop for consumer of queue '{queue_name}'")

    def get_queue_info(self, queue_name: str) -> Dict:
        """Get information about a queue for monitoring"""
        try:
            self._ensure_connection()
            method = self.channel.queue_declare(queue=queue_name, passive=True)

            queue_info = {
                'name': queue_name,
                'messages': method.method.message_count,
                'consumers': method.method.consumer_count,
            }

            # Update Prometheus metrics
            rabbitmq_queue_messages.labels(queue=queue_name).set(method.method.message_count)
            rabbitmq_queue_consumers.labels(queue=queue_name).set(method.method.consumer_count)

            return queue_info

        except Exception as e:
            logger.error(f"Failed to get queue info for '{queue_name}': {e}")
            return {}

    def get_all_queues_info(self) -> Dict:
        """Get information about all queues (requires management plugin in real deployment)"""
        # This is a simplified version - in production you'd use RabbitMQ Management API
        queues_info = {}

        # For demo purposes, we'll track queues we know about
        known_queues = ['task_queue', 'notification_queue', 'analytics_queue']

        for queue_name in known_queues:
            try:
                queue_info = self.get_queue_info(queue_name)
                if queue_info:
                    queues_info[queue_name] = queue_info
            except:
                pass  # Queue might not exist

        return queues_info

    def purge_queue(self, queue_name: str) -> int:
        """Purge all messages from a queue"""
        try:
            self._ensure_connection()
            method = self.channel.queue_purge(queue=queue_name)
            logger.info(f"Purged {method.method.message_count} messages from queue '{queue_name}'")
            return method.method.message_count
        except Exception as e:
            logger.error(f"Failed to purge queue '{queue_name}': {e}")
            return 0

    def close(self):
        """Close all connections and stop consumers"""
        # Stop all running consumers
        for queue_name in list(self.running_consumers.keys()):
            self.stop_consumer(queue_name)

        if self.connection and not self.connection.is_closed:
            self.connection.close()
            rabbitmq_connection_status.set(0)
            logger.info("RabbitMQ connection closed")

# Global RabbitMQ client instance
rabbitmq_client = RabbitMQClient()
