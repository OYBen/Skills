package com.example;

public @interface RetrofitService {
    String host();
    String contextPath() default "";
}
