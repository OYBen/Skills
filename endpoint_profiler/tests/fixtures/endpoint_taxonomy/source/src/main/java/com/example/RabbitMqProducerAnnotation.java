package com.example;

public @interface RabbitMqProducerAnnotation {
    String producerName() default "";
    String exchange() default "orders.exchange";
    String routingKey() default "";
    String queue() default "";
}
