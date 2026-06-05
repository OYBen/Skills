package com.example;

public class ExportTemplateController {
    private static final String IMPORT_TEMPLATE_PATH = "template" + java.io.File.separator + "user-import-template.xlsx";

    public String template() {
        return "target-detail.xlsx";
    }
}
