"""Register new product and launch-tracking RBAC catalog entries (no automatic grants).

Revision ID: 20261030_0069_new_product_rbac_catalog
Revises: 20261029_0068_walmart_remote_jobs
"""
from __future__ import annotations
from alembic import op
from sqlalchemy import text
from app.modules.iam.permission_catalog_v2 import PERMISSION_DEFINITIONS

revision = "20261030_0069_new_product_rbac_catalog"
down_revision = "20261029_0068_walmart_remote_jobs"
branch_labels = None
depends_on = None

PAGE_KEYS = ("products_new_product_analysis", "products_launch_tracking")

def upgrade() -> None:
    bind = op.get_bind()
    for definition in PERMISSION_DEFINITIONS:
        if definition.page_key not in PAGE_KEYS:
            continue
        bind.execute(text("""
            INSERT INTO app_permissions
              (permission_key,name,group_key,description,permission_type,module_key,
               page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
            VALUES
              (:permission_key,:name,:module_key,:description,:permission_type,:module_key,
               :page_key,:action_key,:field_key,:risk_level,:sort_order,true,now(),now())
            ON CONFLICT (permission_key) DO UPDATE SET
              name=excluded.name,description=excluded.description,
              permission_type=excluded.permission_type,module_key=excluded.module_key,
              page_key=excluded.page_key,action_key=excluded.action_key,
              field_key=excluded.field_key,risk_level=excluded.risk_level,
              sort_order=excluded.sort_order,is_active=true,updated_at=now()
        """), {
            "permission_key": definition.permission_key, "name": definition.name,
            "module_key": definition.module_key, "description": definition.description,
            "permission_type": definition.permission_type, "page_key": definition.page_key,
            "action_key": definition.action_key, "field_key": definition.field_key,
            "risk_level": definition.risk_level, "sort_order": definition.sort_order,
        })

def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("""
        DELETE FROM app_role_permissions WHERE permission_key IN (
            SELECT permission_key FROM app_permissions WHERE page_key IN
            ('products_new_product_analysis','products_launch_tracking')
        )
    """))
    bind.execute(text("""
        DELETE FROM app_permissions WHERE page_key IN
        ('products_new_product_analysis','products_launch_tracking')
        AND permission_key <> 'page:products:new-product-analysis:view'
    """))
