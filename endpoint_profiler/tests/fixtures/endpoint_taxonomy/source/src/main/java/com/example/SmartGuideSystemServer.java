package com.example;

import java.util.Map;

public class SmartGuideSystemServer {
    private SmartGuideConfService smartGuideConfService;
    private SmartGuideOkHttpService smartGuideOkHttpService;

    public String generateRedirectUrl(String iconCode, Map<String, Object> params) {
        String urls = smartGuideConfService.getIconUrl();
        String url = (String) JsonUtils.toMap(urls).get(iconCode);
        return smartGuideOkHttpService.responseContentByPost(url, JsonUtils.toJson(params));
    }

    interface SmartGuideConfService {
        String getIconUrl();
    }

    interface SmartGuideOkHttpService {
        String responseContentByPost(String url, String body);
    }

    static class JsonUtils {
        static Map<String, Object> toMap(String value) {
            return Map.of();
        }

        static String toJson(Object value) {
            return "{}";
        }
    }
}
