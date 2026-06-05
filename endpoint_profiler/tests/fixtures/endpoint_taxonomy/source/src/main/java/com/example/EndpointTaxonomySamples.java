package com.example;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.CommandLineRunner;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.EventListener;

public class EndpointTaxonomySamples implements ApplicationListener<OrderChangedEvent>, CommandLineRunner {
    private RabbitTemplate rabbitTemplate;

    @RabbitListener(queues = QueueName.ORDER_CREATED_QUEUE)
    public void consumeOrder(String body) {
    }

    // @RabbitListener(queues = QueueName.IGNORED_QUEUE)
    public void commentedOutListener(String body) {
    }

    @RabbitMqProducerAnnotation(
        producerName = "order sync",
        routingKey = RabbitRoutingKey.ORDER_SYNC_KEY,
        queue = QueueName.ORDER_SYNC_QUEUE
    )
    public void sendOrder(String body) {
    }

    public void sendDirect(String body) {
        rabbitTemplate.convertAndSend("orders.exchange", RabbitRoutingKey.ORDER_SYNC_KEY, body);
    }

    @XxlJob(desc = "refresh order report", cornExpr = "0 0 * * * ?", executeClass = RefreshReportJob.class)
    public void refreshOrderReport() {
    }

    @Cacheable(value = CacheNames.CACHE_5_MINUTES, key = "'Order:'+#id")
    public String cachedOrder(Long id) {
        return "";
    }

    public String loadOrder(Long id) {
        return restGet(KylinPathConsts.ORDER_DETAIL, id);
    }

    public void publishEvent() {
        applicationContext.publishEvent(new OrderChangedEvent());
    }

    @EventListener
    public void onOrderChanged(OrderChangedEvent event) {
    }

    @Override
    public void onApplicationEvent(OrderChangedEvent event) {
    }

    @Override
    public void run(String... args) {
    }

    protected String restGet(String path, Object... args) {
        return "";
    }
}
