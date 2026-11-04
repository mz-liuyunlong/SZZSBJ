"""Finance cashflow: statement import and journal review tables.

No account numbers or platform, vendor, institution or bank names here: accounts and rules
that mention them are loaded at deployment time by scripts/finance_cash_deploy_load.py from a
file outside the repository.
"""

# ruff: noqa: E501
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261104_0072_finance_cashflow"
down_revision: str | Sequence[str] | None = "20261102_0071_skill_lib"
branch_labels = None
depends_on = None

INTERNAL = {"T02"}
EXCLUDE = {"X01"}
CATEGORIES = [
    ("G01", "管理费用", "租金水电管理费"),
    ("G02", "管理费用", "办公费"),
    ("G03", "管理费用", "工资"),
    ("G04", "管理费用", "社保"),
    ("G05", "管理费用", "公积金"),
    ("G06", "管理费用", "福利费"),
    ("G07", "管理费用", "工商费用"),
    ("G08", "管理费用", "差旅交通"),
    ("G09", "管理费用", "其他费用"),
    ("F01", "财务费用", "手续费"),
    ("F02", "财务费用", "税费"),
    ("F03", "财务费用", "利息收入"),
    ("C01", "采购成本", "采购货款"),
    ("C02", "采购成本", "辅料包材"),
    ("L01", "物流", "头程运费"),
    ("L02", "物流", "报关费"),
    ("L03", "物流", "海外仓费用"),
    ("S01", "销售费用", "平台广告"),
    ("S02", "销售费用", "测评"),
    ("S03", "销售费用", "店铺与平台费"),
    ("R01", "其他业务收入", "退税收入"),
    ("T01", "往来与资金", "投资款"),
    ("T02", "往来与资金", "内部调拨"),
    ("T03", "往来与资金", "平台回款"),
    ("T04", "往来与资金", "借款与还款"),
    ("X01", "剔除", "非本公司 / 其他部门"),
]
RULES = [
    ("text", "出口退税|退税|电子退库", "R01", 50),
    ("text", "^收费 \\d{4}/\\d{2}/\\d{2}-", "F01", 60),
    ("text", "^收款-", "T03", 70),
    ("text", "专用账户入账", "T03", 80),
    ("text", "Transfer from connected account|资金归集至专用账户", "T02", 90),
    ("text", "Maintenance fee|短信收费|SMSP Service Charge", "F01", 100),
    ("text", "往来款", "T02", 140),
    ("text", "FX向资金账户转账|店铺或资金账户向FX转账", "T02", 150),
    ("text", "个税", "F02", 160),
    ("text", "印花税|增值税|税费|税款|缴税", "F02", 170),
    ("text", "公积金", "G05", 180),
    ("text", "社保", "G04", 190),
    ("text", "薪资|工资|奖金|离职补偿|兼职.*薪|年会奖", "G03", 200),
    ("text", "转账手续费|手续费|汇款费|费率", "F01", 210),
    ("text", "账户维护费|回单管理|短信通知|银行收费|账户管理费|年费", "F01", 220),
    ("text", "结息|利息", "F03", 230),
    ("text", "投资款", "T01", 240),
    ("text", "结汇|换汇|FX向资金账户|向FX转账|汇率\\d+\\.\\d+/(USD|CNY)", "T02", 250),
    ("text", "专用账户入账|归集", "T02", 260),
    ("text", "归集", "T02", 270),
    ("text", "内部调拨|现金支取|提现转入|预转存|转入.*对公|对公转入|提现至", "T02", 280),
    ("text", "(^|\\s)入账(\\s|$)|平台回款|店铺回款", "T03", 290),
    ("text", "账户往来|银行往来", "T02", 300),
    ("text", "备用金", "T04", 310),
    ("text", "兼职|人工费|劳务", "G03", 320),
    ("text", "借款|借支|还款", "T04", 330),
    ("text", "报关", "L02", 340),
    ("text", "头程|海运|空运|运单号|货代", "L01", 350),
    ("text", "海外仓|美东仓|美西仓|仓库费用报销", "L03", 360),
    ("text", "广告", "S01", 370),
    ("text", "测评|礼品卡|返现|测品|返款|评测|自采|代采|直评|\\d{3}-\\d{7}-\\d{7}", "S02", 380),
    ("text", "店铺托管|申述|申诉|账户\\d+个|扣款", "S03", 390),
    ("text", "营业执照|税务罚款|劳动仲裁|劳动诉讼|赔偿|搬仓库|罚款", "G07", 400),
    ("text", "油费|高速|车费|出行", "G08", 410),
    ("text", "工作流|AI 助手|AI助手|通信充值|系统费用|垃圾袋|耗材", "G02", 420),
    (
        "text",
        "店铺租金|店铺注册|店铺申诉|独立站扣费|账号费用|UPC|店铺公司使用费|平台费|虚拟卡",
        "S03",
        430,
    ),
    ("text", "采购退款|采购|货款|供应商|样品款", "C01", 440),
    ("text", "包装|包材|辅料|打包耗材|标签|卡片", "C02", 450),
    ("text", "押金", "G09", 460),
    ("text", "租金|物业|管理费|房租", "G01", 470),
    ("text", "电费|水电|空调|水费", "G01", 480),
    ("text", "电脑租赁|桌椅|电脑|设备|显示器", "G02", 490),
    ("text", "商标", "G07", 510),
    ("text", "注册公司|年审|代理记账|公司注册|工商", "G07", 520),
    ("text", "差旅|打车|加油|通勤|交通|停车|住宿|机票|高铁", "G08", 530),
    ("text", "下午茶|餐费|聚餐|零食|礼品|团建|端午|中秋|年会|福利|体检|茶饮", "G06", 540),
    (
        "text",
        "域名|邮箱|服务器|话费|打印|办公用品|纸巾|线路|软件|会员费|会员|作图|网线|云文档|顾问",
        "G02",
        550,
    ),
]


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        "dim_finance_cash_accounts",
        sa.Column("account_key", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("entity", sa.String(128), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("account_no_last4", sa.String(8), nullable=False, server_default=""),
        sa.Column(
            "identity_hint",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "landing_finance_cashflow_imports",
        sa.Column("import_id", sa.Uuid(), primary_key=True),
        sa.Column("uploader", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="received"),
        sa.Column("request_id", sa.String(128)),
        _created_at(),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", sa.String(255)),
        sa.Column("void_reason", sa.Text()),
    )
    op.create_table(
        "raw_finance_cashflow_files",
        sa.Column("file_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "import_id",
            sa.Uuid(),
            sa.ForeignKey("landing_finance_cashflow_imports.import_id"),
            nullable=False,
        ),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(32)),
        sa.Column(
            "account_keys",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("declared_range_from", sa.Date()),
        sa.Column("declared_range_to", sa.Date()),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reject_reason", sa.Text()),
        _created_at(),
    )
    op.create_index(
        "ix_raw_finance_cashflow_files_sha256", "raw_finance_cashflow_files", ["sha256"]
    )
    op.create_index(
        "ix_raw_finance_cashflow_files_import_id", "raw_finance_cashflow_files", ["import_id"]
    )
    op.create_table(
        "std_finance_cashflow_lines",
        sa.Column("line_uid", sa.String(16), primary_key=True),
        sa.Column(
            "account_key",
            sa.String(64),
            sa.ForeignKey("dim_finance_cash_accounts.account_key"),
            nullable=False,
        ),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("source_time", sa.DateTime(timezone=True)),
        sa.Column("source_timezone", sa.String(64), nullable=False),
        sa.Column("source_time_raw", sa.String(64), nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 4)),
        sa.Column("counterparty_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("counterparty_account_last4", sa.String(8), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("memo", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_ref", sa.String(16), nullable=False, server_default=""),
        sa.Column("dup_ordinal", sa.Integer(), nullable=False),
        sa.Column("statement_row_no", sa.Integer(), nullable=False),
        sa.Column("file_row_order", sa.Integer(), nullable=False),
        sa.Column(
            "first_import_id",
            sa.Uuid(),
            sa.ForeignKey("landing_finance_cashflow_imports.import_id"),
            nullable=False,
        ),
        sa.Column(
            "first_raw_file_id",
            sa.Uuid(),
            sa.ForeignKey("raw_finance_cashflow_files.file_id"),
            nullable=False,
        ),
        sa.Column(
            "last_import_id",
            sa.Uuid(),
            sa.ForeignKey("landing_finance_cashflow_imports.import_id"),
            nullable=False,
        ),
        sa.Column(
            "last_raw_file_id",
            sa.Uuid(),
            sa.ForeignKey("raw_finance_cashflow_files.file_id"),
            nullable=False,
        ),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        _created_at(),
    )
    op.create_index(
        "ix_std_finance_cashflow_lines_account_date",
        "std_finance_cashflow_lines",
        ["account_key", "business_date"],
    )
    op.create_table(
        "std_finance_cashflow_line_occurrences",
        sa.Column(
            "line_uid",
            sa.String(16),
            sa.ForeignKey("std_finance_cashflow_lines.line_uid"),
            primary_key=True,
        ),
        sa.Column(
            "raw_file_id",
            sa.Uuid(),
            sa.ForeignKey("raw_finance_cashflow_files.file_id"),
            primary_key=True,
        ),
        sa.Column(
            "import_id",
            sa.Uuid(),
            sa.ForeignKey("landing_finance_cashflow_imports.import_id"),
            nullable=False,
        ),
        sa.Column("statement_row_no", sa.Integer(), nullable=False),
        sa.Column("file_row_order", sa.Integer(), nullable=False),
        sa.Column("seen_seq", sa.BigInteger(), sa.Identity(), nullable=False),
    )
    op.create_index(
        "ix_std_finance_cashflow_line_occurrences_import",
        "std_finance_cashflow_line_occurrences",
        ["import_id"],
    )
    op.create_table(
        "dq_run_finance_cashflow_import",
        sa.Column(
            "file_id",
            sa.Uuid(),
            sa.ForeignKey("raw_finance_cashflow_files.file_id"),
            primary_key=True,
        ),
        sa.Column("rows_parsed", sa.Integer(), nullable=False),
        sa.Column("rows_new", sa.Integer(), nullable=False),
        sa.Column("rows_duplicate", sa.Integer(), nullable=False),
        sa.Column("balance_chain_ok", sa.Boolean()),
        sa.Column(
            "warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    categories = op.create_table(
        "dim_finance_cash_categories",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("big", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_exclude", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    rules = op.create_table(
        "cfg_finance_cash_classify_rules",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("rule_type", sa.String(16), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column(
            "category_code",
            sa.String(8),
            sa.ForeignKey("dim_finance_cash_categories.code"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
    )
    op.create_table(
        "evt_finance_cash_line_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "line_uid",
            sa.String(16),
            sa.ForeignKey("std_finance_cashflow_lines.line_uid"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("reason", sa.Text()),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(128)),
        sa.Column("idempotency_key", sa.String(128)),
        _created_at(),
    )
    op.create_index(
        "ix_evt_finance_cash_line_reviews_line", "evt_finance_cash_line_reviews", ["line_uid"]
    )
    op.create_index(
        "uq_evt_finance_cash_line_reviews_idempotency",
        "evt_finance_cash_line_reviews",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "mart_finance_cash_line_state",
        sa.Column(
            "line_uid",
            sa.String(16),
            sa.ForeignKey("std_finance_cashflow_lines.line_uid"),
            primary_key=True,
        ),
        sa.Column(
            "manual_category", sa.String(8), sa.ForeignKey("dim_finance_cash_categories.code")
        ),
        sa.Column(
            "refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("exclude_amount", sa.Numeric(18, 4)),
        sa.Column("exclude_reason", sa.Text()),
        sa.Column("stage", sa.String(8), nullable=False, server_default="todo"),
        sa.Column("stage_reason", sa.Text()),
        sa.Column("review_note", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "manual_finance_cash_exclusions",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("entry_key", sa.String(64), nullable=False, unique=True),
        sa.Column("ref", sa.String(32)),
        sa.Column("txn_date", sa.Date()),
        sa.Column("account_key", sa.String(64)),
        sa.Column("summary_contains", sa.Text()),
        sa.Column("amount_cny", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("registered_by", sa.String(255), nullable=False),
        sa.Column("registered_on", sa.Date()),
    )
    op.bulk_insert(
        categories,
        [
            {
                "code": code,
                "big": big,
                "name": name,
                "is_internal": code in INTERNAL,
                "is_exclude": code in EXCLUDE,
                "sort_order": index,
            }
            for index, (code, big, name) in enumerate(CATEGORIES, start=1)
        ],
    )
    op.bulk_insert(
        rules,
        [
            {
                "rule_type": rule_type,
                "pattern": pattern,
                "category_code": category_code,
                "sort_order": sort_order,
                "source": "seed",
            }
            for rule_type, pattern, category_code, sort_order in RULES
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_lines = bind.execute(sa.text("select 1 from std_finance_cashflow_lines limit 1")).first()
    if has_lines is not None:
        raise RuntimeError("std_finance_cashflow_lines has data; refusing to drop finance tables")
    for table in (
        "manual_finance_cash_exclusions",
        "mart_finance_cash_line_state",
        "evt_finance_cash_line_reviews",
        "cfg_finance_cash_classify_rules",
        "dim_finance_cash_categories",
        "dq_run_finance_cashflow_import",
        "std_finance_cashflow_line_occurrences",
        "std_finance_cashflow_lines",
        "raw_finance_cashflow_files",
        "landing_finance_cashflow_imports",
        "dim_finance_cash_accounts",
    ):
        op.drop_table(table)
