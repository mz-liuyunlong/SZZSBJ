from typing import cast

from sqlalchemy import DateTime, Identity, Table
from sqlalchemy.dialects.postgresql import JSONB

from app.models.raw_lingxing_api import RawLingxingApi


def test_raw_model_matches_approved_l2_shape_and_uses_nonunique_hash_index() -> None:
    table = cast(Table, RawLingxingApi.__table__)

    assert isinstance(table.c.id.server_default, Identity)
    assert isinstance(table.c.request_params_json.type, JSONB)
    assert isinstance(table.c.request_body_json.type, JSONB)
    assert isinstance(table.c.response_json.type, JSONB)
    assert isinstance(table.c.extra_json.type, JSONB)
    assert isinstance(table.c.pulled_at.type, DateTime)
    assert table.c.pulled_at.type.timezone is True
    assert table.c.raw_hash.unique is not True
    constraint_names = [constraint.name for constraint in table.constraints]
    assert set(constraint_names) >= {
        "ck_raw_lingxing_api_api_path",
        "ck_raw_lingxing_api_request_method",
        "ck_raw_lingxing_api_source_system",
        "pk_raw_lingxing_api",
    }
    assert constraint_names.count("ck_raw_lingxing_api_api_path") == 1
    indexes = {str(index.name): index for index in table.indexes}
    assert set(indexes) == {"ix_raw_lingxing_api_raw_hash"}
    assert indexes["ix_raw_lingxing_api_raw_hash"].unique is False
