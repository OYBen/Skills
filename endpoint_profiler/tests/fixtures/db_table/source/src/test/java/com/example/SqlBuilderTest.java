package com.example;

import org.junit.jupiter.api.Assertions;

public class SqlBuilderTest {
    void expectedSqlTextIsNotAnEndpoint() {
        Assertions.assertEquals("INSERT INTO t_user AS t0 (id) VALUES (1)", "ignored");
    }
}
