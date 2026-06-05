package com.example;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("cem")
public class CemController {
    @PostMapping("event")
    public String event(@RequestBody String request) {
        return "success";
    }
}
