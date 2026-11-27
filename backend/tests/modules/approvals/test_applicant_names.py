from types import SimpleNamespace

from app.modules.approvals.applicant_names import (
    attach_approval_names,
    attach_clearance_names,
    resolve_names,
)


class FakeSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return self

    def mappings(self):
        return self

    def all(self):
        return [
            {"id": 51, "display_name": "Operator A", "username": "user51"},
            {"id": 53, "display_name": " ", "username": "user53"},
        ]


def test_batch_names_and_preserve_identity():
    db = FakeSession()
    data = SimpleNamespace(
        items=[
            SimpleNamespace(applicant_id="51"),
            SimpleNamespace(applicant_id="51"),
            SimpleNamespace(applicant_id="53"),
            SimpleNamespace(applicant_id="99"),
            SimpleNamespace(applicant_id=None),
        ]
    )
    attach_approval_names(db, data)
    assert len(db.calls) == 1
    assert db.calls[0][1] == {"ids": [51, 53, 99]}
    assert [x.applicant_name for x in data.items] == [
        "Operator A",
        "Operator A",
        "user53",
        None,
        None,
    ]
    assert data.items[0].applicant_id == "51"


def test_no_query_for_unverified_ids():
    db = FakeSession()
    assert resolve_names(db, [None, "", "unknown", "0051"]) == {}
    assert db.calls == []


def test_clearance_application_identity_unchanged():
    db = FakeSession()
    data = {"items": [{"applicant_ref": "51", "status": "running"}]}
    attach_clearance_names(db, data)
    assert data["items"][0] == {
        "applicant_ref": "51",
        "applicant_name": "Operator A",
        "status": "running",
    }
