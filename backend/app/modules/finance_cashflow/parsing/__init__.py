"""银行 / 平台流水文件解析：按内容识别账户，解析成标准化流水。纯函数，不碰数据库。"""

PARSER_VERSION = "finance_cashflow/3"  # 2：邮箱不再打码；3：PingPong 付款手续费写进备注、中行多段
