# 🚀 Enterprise Message Broker Platform & Monitoring
## Django DRF + Kafka + RabbitMQ + Prometheus + Grafana

## 🎯 Project Overview
این پروژه یک سامانه مبتنی بر Kafka است که به منظور مدیریت پیام‌ها و ارتباط بین سرویس‌ها در معماری مایکروسرویس طراحی شده است. در این سامانه، از Kafka برای ارسال و دریافت پیام‌ها به صورت بلادرنگ (Real-time) استفاده شده و با استفاده از ابزارهایی مانند Prometheus، مانیتورینگ دقیق مصرف‌کنندگان (Consumers) و میزان تأخیر آن‌ها (Consumer Lag) انجام می‌شود.

- **ویژگی‌های اصلی پروژه:**
- استفاده از Kafka به عنوان سیستم صف پیام (Message Queue)
- پیاده‌سازی تولیدکننده (Producer) و مصرف‌کننده (Consumer) با استفاده از kafka-python
- امکان مدیریت موضوعات (Topics) با استفاده از Kafka AdminClient
- مانیتورینگ شاخص‌های کلیدی مانند تعداد پیام‌های ارسالی و مصرف‌شده، مدت زمان ارسال پیام، و میزان تأخیر مصرف‌کننده با استفاده از Prometheus
- پشتیبانی از کلید در پیام‌ها برای حفظ ترتیب و تعیین پارتیشن‌ها
- طراحی ماژولار و قابل توسعه مناسب برای پروژه‌های مقیاس‌پذیر و مایکروسرویسی

این پروژه می‌تواند به عنوان یک پایه برای سیستم‌های توزیع‌شده، سرویس‌های لاگ‌گیری، صف‌های پیام یا هر نوع پردازش رویداد (Event-Driven Architecture) مورد استفاده قرار گیرد.

- **Kafka and RabbitMQ Monitoring:**
- Infrastructure Monitoring (Kafka + JMX exporter, RabbitMQ with metrics plugin)
- Application-level Monitoring

## 🏗️ Architecture Deep Dive
### Message Flow Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Django    │───▶│    Kafka     │───▶│  Consumer   │
│     API     │    │   Topics     │    │   Groups    │
└─────────────┘    └──────────────┘    └─────────────┘
       │                                       │
       ▼                                       ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  RabbitMQ   │───▶│   Exchanges  │───▶│   Queue     │
│   Queues    │    │ & Bindings   │    │ Consumers   │  
└─────────────┘    └──────────────┘    └─────────────┘
       │                                       │
       ▼                                       ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│ Prometheus  │───▶│   Grafana    │───▶│   Alerts    │
│   Metrics   │    │ Dashboards   │    │ & Reports   │
└─────────────┘    └──────────────┘    └─────────────┘
```

## 🏗️ Architecture Highlights

- 🔄 Data Streaming: Real-time message processing with Kafka topics and consumer groups
- 📨 Message Queuing: Reliable message delivery with RabbitMQ exchanges and queues
- 📊 Enterprise Monitoring: Complete observability stack with Prometheus metrics and Grafana dashboards
- 🎨 Design Patterns: Implementation of Singleton, Observer, Factory, and Circuit Breaker patterns
- ⚡ Async Processing: Celery integration for background task processing
- 🐳 Containerization: Full Docker Compose development environment
