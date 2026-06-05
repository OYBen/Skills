package com.example;

public class ConfigBaseUrlClient {
    private KyLinApiConfig kyLinApiConfig;
    private KylinOkHttpService kylinOkHttpService;

    public String registerWechat(Object request) {
        String url = kyLinApiConfig.getMbspApiUrl(KyLinMbspApiPathConsts.Member.MEMBER_POST_REGISTER_WECHAT);
        return kylinOkHttpService.responseContentByPost(url, request);
    }

    public String guideDataReport(Object request) {
        String url = kyLinApiConfig.getCustomerUrl(KyLinApiPathConsts.DataReport.GUIDE_DATA_REPORT);
        return kylinOkHttpService.responseContentByGet(url);
    }

    interface KyLinApiConfig {
        String getMbspApiUrl(String path);
        String getCustomerUrl(String path);
    }

    interface KylinOkHttpService {
        String responseContentByPost(String url, Object body);
        String responseContentByGet(String url);
    }

    static class KyLinMbspApiPathConsts {
        static class Member {
            public static final String MEMBER_POST_REGISTER_WECHAT = "/member/register/wechat";
        }
    }

    static class KyLinApiPathConsts {
        static class DataReport {
            public static final String GUIDE_DATA_REPORT = "/data/report/guide";
        }
    }
}
