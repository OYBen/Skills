package com.example;

class CdpModelAccess {
    private DataApiService dataApiService;
    private EventProducer eventProducer;
    private MetaDataApiService metaDataApiService;

    void queryOltp() {
        String sql = "select id from data.mdm.CohortMeta where id = :id";
        dataApiService.commonSqlExecute(sql, Map.of("id", "1"));
    }

    void queryAnalytics() {
        String sql = "SELECT bitmap_iterate(serialNumBitmap) AS serialNum FROM data.cdp.calc.SegmentTaskTarget WHERE originId = :originId";
        dataApiService.queryByStream(sql, Map.of("originId", "tag-1"), rows -> {}, 5000);
    }

    void mergeCategory() {
        dataApiService.batchMergeModel("data.mdm.TagCategory", java.util.List.of("id", "name"), java.util.List.of(java.util.Map.of("id", "1", "name", "A")));
    }

    void publishEvent() {
        eventProducer.publishBatchSync(PublishOptions.of("event.cdp.ImportExportNotify", BodySerializer.map()), java.util.List.of(Event.of("event.cdp.ImportExportNotify", "1", Map.of())));
    }

    void createRuntimeModel() {
        metaDataApiService.createModel("data.cdp.calc.RuleMultiValueTagFqnMapping", "rule mapping", "cdp", "OLAP", false, java.util.List.of());
    }
}
