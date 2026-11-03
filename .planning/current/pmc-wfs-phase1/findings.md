# Findings

- 到仓日沿用 8088 到仓链路（`arrival_rules.py`）：有实际签收为“实际”（`eta_source=real`），否则按区域经验天数（`region`）或计划日（`plan`）估算。来源标签即使没有日期也要保留（8088 `etaSrcL` 行为）。
- 可售日 = 首批上架（Walmart Receipt 流水）日期；没有上架时按到仓 + 10 天预估，并标为预估。
- 产品维度按 店铺 × Item ID 聚合，Item ID 需要 `dim_walmart_listings`。回放库里这张表没有数据，所以产品维度和 Item ID 在上线环境要先确认维表有数据。
- 规则日期必须用数据日，不能用运行日，否则分段和天数会漂移。8088 是 `TODAY = 数据日`；看板读取时用当前发布版本的 `as_of`，异常检测默认跟看板一致。
- 异常去重按 货件 × 规则族；三个申诉类型合并为 `appeal_deadline` 一个规则族。
- 测试货件（`PMC-TEST-`）不建异常案件，与 8088 一致。
- 打包完成天数按 Asia/Shanghai 日历日计算。
