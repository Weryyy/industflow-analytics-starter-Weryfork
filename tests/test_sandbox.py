"""Unit tests for the read-only aggregation sandbox (pure, no MongoDB needed)."""
import pytest

from industflow_ai.config import MAX_AGGREGATE_RESULTS
from industflow_ai.safety.sandbox import SandboxError, validate_pipeline


def test_rejects_unknown_collection():
    with pytest.raises(SandboxError, match="not readable"):
        validate_pipeline("ai.audit", [{"$match": {}}])


def test_rejects_empty_or_non_list_pipeline():
    with pytest.raises(SandboxError):
        validate_pipeline("products", [])
    with pytest.raises(SandboxError):
        validate_pipeline("products", {"$match": {}})


def test_rejects_multi_key_stage():
    with pytest.raises(SandboxError, match="single-key"):
        validate_pipeline("products", [{"$match": {}, "$limit": 5}])


def test_rejects_disallowed_stage():
    with pytest.raises(SandboxError, match="stage not allowed"):
        validate_pipeline("products", [{"$graphLookup": {}}])


@pytest.mark.parametrize("stage", [
    {"$out": "evil"},
    {"$merge": {"into": "evil"}},
])
def test_rejects_write_stages(stage):
    with pytest.raises(SandboxError):
        validate_pipeline("products", [stage])


def test_rejects_forbidden_operator_nested_in_expression():
    pipeline = [{"$addFields": {"x": {"$function": {"body": "...", "args": [],
                                                    "lang": "js"}}}}]
    with pytest.raises(SandboxError, match=r"forbidden operator: \$function"):
        validate_pipeline("products", pipeline)


def test_rejects_where_inside_match():
    with pytest.raises(SandboxError, match=r"\$where"):
        validate_pipeline("products", [{"$match": {"$where": "true"}}])


def test_lookup_must_target_readable_collection():
    pipeline = [{"$lookup": {"from": "ai.audit", "pipeline": [], "as": "x"}}]
    with pytest.raises(SandboxError, match=r"\$lookup from 'ai.audit'"):
        validate_pipeline("products", pipeline)


def test_lookup_to_readable_collection_passes():
    pipeline = [{"$lookup": {"from": "lines", "localField": "line.$id",
                             "foreignField": "_id", "as": "line"}}]
    out = validate_pipeline("products", pipeline)
    assert out[-1] == {"$limit": MAX_AGGREGATE_RESULTS}


def test_lookup_sub_pipeline_is_validated():
    pipeline = [{"$lookup": {"from": "lines", "as": "x",
                             "pipeline": [{"$out": "evil"}]}}]
    with pytest.raises(SandboxError):
        validate_pipeline("products", pipeline)


def test_facet_sub_pipelines_obey_stage_allow_list():
    pipeline = [{"$facet": {"a": [{"$graphLookup": {}}]}}]
    with pytest.raises(SandboxError, match=r"\$facet\.a"):
        validate_pipeline("products", pipeline)


def test_facet_with_allowed_stages_passes():
    pipeline = [{"$facet": {"counts": [{"$sortByCount": "$status"}],
                            "total": [{"$count": "n"}]}}]
    out = validate_pipeline("products", pipeline)
    assert out[-1] == {"$limit": MAX_AGGREGATE_RESULTS}


def test_appends_limit_when_missing():
    out = validate_pipeline("products", [{"$match": {"deleted": False}}])
    assert out[-1] == {"$limit": MAX_AGGREGATE_RESULTS}


def test_caps_oversized_trailing_limit():
    out = validate_pipeline("products", [{"$match": {}},
                                         {"$limit": 10 * MAX_AGGREGATE_RESULTS}])
    assert out[-1] == {"$limit": MAX_AGGREGATE_RESULTS}


def test_keeps_smaller_trailing_limit():
    out = validate_pipeline("products", [{"$match": {}}, {"$limit": 5}])
    assert out[-1] == {"$limit": 5}


def test_does_not_mutate_input_pipeline():
    pipeline = [{"$match": {}}]
    validate_pipeline("products", pipeline)
    assert pipeline == [{"$match": {}}]
