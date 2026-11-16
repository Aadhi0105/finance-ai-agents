"""The pilot register must not turn preparation or assistance into acceptance."""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import check_workspace_pilot_spec as pilot


@pytest.fixture
def record(tmp_path):
    tmp_path.chmod(0o700)
    value = json.loads((pilot.SPEC / "record.template.json").read_text())
    candidate = value["candidate"]
    candidate.update(state="frozen", commit="a" * 40, frozen_at="2026-01-01T00:00:00Z",
                     environment={"platform": "Darwin", "architecture": "arm64",
                                  "python": "3.11.9", "os_version": "test-only",
                                  "node": "24.0.0", "pnpm": "11.25.0"})
    for key in candidate:
        if key.endswith("_sha256"):
            candidate[key] = "b" * 64
    path = tmp_path / "record.json"
    evidence = tmp_path / "evidence"
    evidence.mkdir(mode=0o700)
    receipt = evidence / "observation.txt"
    receipt.write_text("Synthetic test evidence, not a real analyst answer.\n")
    receipt.chmod(0o600)
    raw = receipt.read_bytes()
    attempt = {
        "id": "attempt-" + "c" * 32,
        "actor": {"role": "analyst", "label": "Synthetic test actor",
                  "identity_verification": "local_unverified"},
        "outcome": "passed", "started_at": "2026-01-01T00:01:00Z",
        "finished_at": "2026-01-01T00:02:00Z",
        "observed": "Test observation only", "assistance": "none",
        "assistance_detail": None, "blocking_reason": None,
        "evidence": [{"path": "evidence/observation.txt", "bytes": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest()}],
    }
    value["results"][0].update(status="passed", attempts=[attempt])
    return path, value


def save(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)


def check(record):
    path, value = record
    save(path, value)
    return pilot.validate_record(path)


def test_shipped_template_is_unassessed_and_checker_has_no_write_side_effects(capsys):
    paths = list(pilot.SPEC.iterdir())
    before = {p.name: p.read_bytes() for p in paths}
    assert pilot.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["candidate_state"] == "unassigned"
    assert result["result_counts"] == {"not_assessed": 24}
    assert result["readiness"] == "not_assessed"
    assert result["financial_approval"] is False
    assert result["production_release_approved"] is False
    assert {p.name: p.read_bytes() for p in paths} == before


def test_valid_local_evidence_still_requires_human_review(record):
    result = check(record)
    assert result["result_counts"] == {"passed": 1, "not_assessed": 23}
    assert result["readiness"] == "requires_human_evidence_review"
    assert result["production_release_approved"] is False


@pytest.mark.parametrize("mutation", [
    lambda r: r["candidate"].update(state="unassigned"),
    lambda r: r["candidate"].update(commit=None),
    lambda r: r["candidate"].update(frozen_at="2026-01-02T00:00:00Z"),
    lambda r: r["candidate"]["environment"].update(platform="Linux"),
    lambda r: r.update(protocol_sha256="0" * 64),
    lambda r: r.update(schema_sha256="0" * 64),
    lambda r: r["results"][0].update(check_id="P7-UAT-99"),
    lambda r: r["results"][1].update(check_id="P7-UAT-01"),
    lambda r: r["results"][0].update(status="not_assessed"),
    lambda r: r["results"][1].update(status="passed"),
    lambda r: r["results"][0]["attempts"][0].update(evidence=[]),
    lambda r: r["results"][0]["attempts"][0].update(outcome="failed"),
    lambda r: r["results"][0]["attempts"][0]["actor"].update(role="operator"),
    lambda r: r["results"][0]["attempts"][0]["actor"].update(identity_verification="authenticated"),
    lambda r: r["results"][0]["attempts"][0].update(finished_at="2025-01-01T00:00:00Z"),
    lambda r: r["results"][0]["attempts"][0].update(finished_at="2999-01-01T00:00:00Z"),
    lambda r: r["results"][0]["attempts"][0].update(started_at="2026-01-01T00:01:00"),
    lambda r: r["results"][0]["attempts"][0].update(observed="   "),
    lambda r: r["decision"].update(financial_approval=True),
    lambda r: r["decision"].update(production_release_approved=True),
    lambda r: r["decision"].update(pilot_acceptance="approved"),
    lambda r: r.update(unknown_field=True),
])
def test_rejects_premature_stale_or_promoted_claims(record, mutation):
    mutation(record[1])
    with pytest.raises(Exception):
        check(record)


def test_assistance_needs_separate_unaided_retest_and_retains_previous_attempt(record):
    row = record[1]["results"][0]
    attempt = row["attempts"][0]
    attempt.update(assistance="developer_intervention", assistance_detail="Explained the answer")
    with pytest.raises(ValueError):
        check(record)
    row["status"] = "in_progress"
    assert check(record)["result_counts"]["in_progress"] == 1
    retest = copy.deepcopy(attempt)
    retest.update(id="attempt-" + "d" * 32, started_at="2026-01-01T00:03:00Z",
                  finished_at="2026-01-01T00:04:00Z", assistance="none", assistance_detail=None)
    row["attempts"].append(retest)
    row["status"] = "passed"
    assert check(record)["result_counts"]["passed"] == 1
    row["attempts"].reverse()
    with pytest.raises(ValueError):
        check(record)


def test_blocked_requires_reason_but_is_not_acceptance(record):
    row = record[1]["results"][0]
    row.update(status="blocked")
    row["attempts"][0].update(outcome="blocked", evidence=[])
    with pytest.raises(ValueError):
        check(record)
    row["attempts"][0]["blocking_reason"] = "Cannot access the selected test workspace"
    assert check(record)["result_counts"]["blocked"] == 1


def test_duplicate_attempt_ids_are_refused(record):
    record[1]["results"][1].update(status="in_progress",
                                  attempts=copy.deepcopy(record[1]["results"][0]["attempts"]))
    with pytest.raises(ValueError):
        check(record)


@pytest.mark.parametrize("reference", ["evidence/../private.txt", "evidence/.env",
                                       "evidence/access-token.key", "evidence/secret.txt",
                                       "/tmp/observation.txt"])
def test_refuses_unsafe_evidence_reference(record, reference):
    record[1]["results"][0]["attempts"][0]["evidence"][0]["path"] = reference
    with pytest.raises(Exception):
        check(record)


@pytest.mark.parametrize("damage", ["tamper", "size", "symlink", "parent_symlink", "hardlink", "public"])
def test_evidence_requires_exact_private_regular_bytes(record, tmp_path, damage):
    receipt = tmp_path / "evidence/observation.txt"
    if damage == "tamper":
        receipt.write_text("changed")
    elif damage == "size":
        record[1]["results"][0]["attempts"][0]["evidence"][0]["bytes"] += 1
    elif damage == "symlink":
        receipt.rename(tmp_path / "original.txt")
        receipt.symlink_to(tmp_path / "original.txt")
    elif damage == "parent_symlink":
        (tmp_path / "evidence").rename(tmp_path / "elsewhere")
        (tmp_path / "evidence").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    elif damage == "hardlink":
        os.link(receipt, tmp_path / "another.txt")
    else:
        receipt.chmod(0o644)
    with pytest.raises(Exception):
        check(record)


@pytest.mark.parametrize("target", ["directory", "record"])
def test_filled_records_must_be_private(record, target):
    path, value = record
    save(path, value)
    (path.parent if target == "directory" else path).chmod(0o755 if target == "directory" else 0o644)
    with pytest.raises(ValueError):
        pilot.validate_record(path)


@pytest.mark.parametrize("mutation", [
    lambda p: p["production_crosswalk"].pop(),
    lambda p: p["production_crosswalk"][0].update(gate="V1-UNKNOWN-999"),
    lambda p: p["production_crosswalk"][0].update(disposition="passed"),
    lambda p: p["production_crosswalk"][0].update(pilot_checks=[]),
    lambda p: p["checks"][0].update(actor="operator"),
    lambda p: p["scope"].update(live_data=True),
    lambda p: p["dependencies"][0].update(status="passed"),
    lambda p: p["workload"].update(base_calculations=4),
])
def test_production_crosswalk_and_scope_cannot_silently_drift(tmp_path, mutation):
    for file in pilot.SPEC.iterdir():
        (tmp_path / file.name).write_bytes(file.read_bytes())
    protocol = json.loads((tmp_path / "protocol.json").read_text())
    mutation(protocol)
    (tmp_path / "protocol.json").write_text(json.dumps(protocol))
    with pytest.raises(ValueError):
        pilot.check_spec(tmp_path, pilot.ROOT / "docs/production/v1/acceptance-matrix.md")


def test_cli_refusal_never_echoes_private_content(record, capsys):
    path, value = record
    value["results"][0]["attempts"][0]["observed"] = "PRIVATE-NAME-AND-SECRET"
    value["decision"]["production_release_approved"] = True
    save(path, value)
    assert pilot.main(["--record", str(path)]) == 2
    output = capsys.readouterr().out
    assert "PRIVATE" not in output and str(path) not in output
    assert json.loads(output)["status"] == "pilot_spec_invalid"


def test_duplicate_json_keys_are_rejected(tmp_path):
    path = tmp_path / "record.json"
    path.write_text('{"schema_version": 1, "schema_version": 1}')
    with pytest.raises(ValueError):
        pilot.read_json(path)
