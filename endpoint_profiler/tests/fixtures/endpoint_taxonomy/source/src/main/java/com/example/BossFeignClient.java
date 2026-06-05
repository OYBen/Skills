package com.example;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "boss", url = "${boss.api}")
public interface BossFeignClient {
    @GetMapping("/boss/oauth/token?appid={appId}&code={code}")
    String token(String appId, String code);
}
