# Verifier Result

## Commands

```powershell
python -m py_compile C:\Users\apoll\.agents\skills\endpoint_profiler\scripts\endpoint_profiler.py C:\Users\apoll\.agents\skills\endpoint_profiler\scripts\verify_endpoint_profiler.py
python C:\Users\apoll\.agents\skills\endpoint_profiler\scripts\endpoint_profiler.py C:\Users\apoll\.agents\skills\endpoint_profiler\tests\fixtures\endpoint_taxonomy\source --out C:\Users\apoll\.agents\skills\endpoint_profiler\tests\fixtures\endpoint_taxonomy\out
python C:\Users\apoll\.agents\skills\endpoint_profiler\scripts\verify_endpoint_profiler.py C:\Users\apoll\.agents\skills\endpoint_profiler\tests\fixtures\endpoint_taxonomy\out
python C:\Users\apoll\.agents\skills\endpoint_profiler\scripts\endpoint_profiler.py D:\kylin_product_repo\Kylin导购\siyu-develop --graphify-index D:\kylin_product_repo\Kylin导购\siyu-develop-graphify-out\graphify-out\graph.json --out D:\kylin_product_repo\Kylin导购\siyu-develop-graphify-out\endpoints-out
python C:\Users\apoll\.agents\skills\endpoint_profiler\scripts\verify_endpoint_profiler.py D:\kylin_product_repo\Kylin导购\siyu-develop-graphify-out\endpoints-out
```

## Final Result

- Fixture verifier: PASS.
- Full siyu-develop verifier: PASS.
- Full endpoint count: 1932.
- Services: 6.
- HTTP_CALL count: 190.

## Output

- Aggregate JSON:
  `D:\kylin_product_repo\Kylin导购\siyu-develop-graphify-out\endpoints-out\endpoints.json`
- Aggregate HTML:
  `D:\kylin_product_repo\Kylin导购\siyu-develop-graphify-out\endpoints-out\endpoints_result.html`
