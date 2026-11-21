"""Kafka topic management for MyStore."""

from __future__ import annotations

import structlog
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

from app.config import settings
from app.kafka_utils import create_kafka_ssl_context

logger = structlog.stdlib.get_logger(__name__)

# Topics required by MyStore architecture
REQUIRED_TOPICS = [
    "orders.placed",
    "inventory.changed",
    "products.updated",
    "search.events",
    "returns.events",
    "suborder.created",
    "invoice.generated",
    "orders.placed.dlq",
    "inventory.changed.dlq",
    "products.updated.dlq",
    "search.events.dlq",
    "returns.events.dlq",
    "suborder.created.dlq",
    "invoice.generated.dlq",
]


def ensure_kafka_topics(partitions: int = 1, replication_factor: int = 1) -> List[str]:
    """Connect to Aiven Kafka via AdminClient and ensure all topics exist."""
    ssl_context = create_kafka_ssl_context()
    
    admin_client = KafkaAdminClient(
        bootstrap_servers=settings.kafka_broker,
        security_protocol="SASL_SSL",
        sasl_mechanism="PLAIN",
        sasl_plain_username=settings.kafka_user,
        sasl_plain_password=settings.kafka_password,
        ssl_context=ssl_context,
        client_id="mystore-topic-admin",
    )

    try:
        existing_topics = set(admin_client.list_topics())
        new_topics = []
        for topic_name in REQUIRED_TOPICS:
            if topic_name not in existing_topics:
                new_topics.append(NewTopic(
                    name=topic_name,
                    num_partitions=partitions,
                    replication_factor=replication_factor,
                ))

        if new_topics:
            logger.info("creating_kafka_topics", count=len(new_topics), topics=[t.name for t in new_topics])
            try:
                admin_client.create_topics(new_topics=new_topics, validate_only=False)
                logger.info("kafka_topics_created_successfully")
            except TopicAlreadyExistsError:
                pass
        else:
            logger.info("all_kafka_topics_exist")

        return list(admin_client.list_topics())
    finally:
        admin_client.close()

