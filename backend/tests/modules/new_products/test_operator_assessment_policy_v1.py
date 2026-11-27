"""Human verdict is authoritative; grade does not decide pass or fail."""

from app.modules.new_products.evaluation_policy import evaluation_status


def test_final_grade_never_automatically_passes():
    base = dict(listing_date="2026-11-01", first_wfs="2026-11-01", total="9.37", grade="S")
    assert evaluation_status(coverage={}, **base) == "待测评确认"
    assert (
        evaluation_status(coverage={"operator_assessment_v1": {"decision": "passed"}}, **base)
        == "测评通过"
    )
    assert (
        evaluation_status(coverage={"operator_assessment_v1": {"decision": "failed"}}, **base)
        == "测评未通过"
    )
    base["grade"] = "D"
    assert evaluation_status(coverage={}, **base) == "待测评确认"
    assert (
        evaluation_status(coverage={"operator_assessment_v1": {"decision": "passed"}}, **base)
        == "测评通过"
    )
