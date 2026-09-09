# Cache and Derived Data Boundary Rules

## Required Rules

- Cache、snapshot、MART/read model、搜索索引、向量和 AI 输出都是派生数据，不是权威真源。
- 每个派生对象必须说明来源、grain、刷新触发、freshness/TTL、writer/readers、lineage、重建和删除传播。
- Cache key 不得包含 secret；过期或缺失时不得静默 fallback 到未批准来源。
- Read model 只能由获批来源重建，不接受前端或人工直接写入。
- Snapshot 必须记录声明时点和版本；不得与短期 cache 混用。
- 派生结果异常时修复来源/规则并重建，不得反向覆盖权威层。

## Stop Conditions

无法说明权威来源、重建方法、新鲜度或权限时，不得新增 cache/read model。
