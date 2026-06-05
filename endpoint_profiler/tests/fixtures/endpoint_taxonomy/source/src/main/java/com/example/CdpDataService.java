package com.example;

import java.util.List;

public class CdpDataService {
    private CdpApiConfig cdpApiConfig;
    private CdpOkHttpService cdpOkHttpService;

    public List<String> queryOccIdsByMemberIds(CdpQueryOccIdsByMemberIdsRequest request) {
        String url = cdpApiConfig.getApiUrl(CdpApiPathConsts.CdpData.MEMBER_POST_QUERY_OCC_ID);
        return cdpOkHttpService.responseContentByPost(url, request);
    }

    static class CdpApiPathConsts {
        static class CdpData {
            public static final String MEMBER_POST_QUERY_OCC_ID = "/data/query/occIds";
        }
    }

    interface CdpApiConfig {
        String getApiUrl(String path);
    }

    interface CdpOkHttpService {
        List<String> responseContentByPost(String url, Object body);
    }

    static class CdpQueryOccIdsByMemberIdsRequest {
    }
}
