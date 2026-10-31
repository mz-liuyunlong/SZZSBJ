from app.modules.iam.feishu_directory_service import FeishuDirectoryService


def test_department_structure_preserves_stable_ids(monkeypatch):
    service = FeishuDirectoryService(
        base_url="https://open.feishu.cn", app_id="dummy", app_secret="dummy"
    )
    monkeypatch.setattr(service, "_fetch_tenant_access_token", lambda: "stub")

    def paged(path, params, token, *, item_keys):
        assert path.endswith("/departments/0/children")
        assert token == "stub"
        return [
            {"open_department_id": "od-a", "name": "运营部", "parent_department_id": "0"},
            {"open_department_id": "od-b", "name": "一组", "parent_department_id": "od-a"},
        ]

    monkeypatch.setattr(service, "_get_paged_items", paged)
    rows = service.list_visible_departments()
    assert {row["department_id"]: row["parent_department_id"] for row in rows} == {
        "od-a": "0",
        "od-b": "od-a",
    }


def test_missing_department_identity_is_skipped(monkeypatch):
    service = FeishuDirectoryService(
        base_url="https://open.feishu.cn", app_id="dummy", app_secret="dummy"
    )
    monkeypatch.setattr(service, "_fetch_tenant_access_token", lambda: "stub")
    monkeypatch.setattr(service, "_get_paged_items", lambda *_args, **_kwargs: [{"name": "no id"}])
    assert service.list_visible_departments() == ()
