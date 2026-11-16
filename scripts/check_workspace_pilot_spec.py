"""Read-only consistency checks for the bounded Batch 7 pilot specification.

This does not run an agent, establish reviewer identity, verify observations or
approve a release. Keep filled records and their evidence outside version control.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/webapp/pilot"
CHECK_IDS = [f"P7-{group}-{number:02d}" for group, count in
             (("UAT", 10), ("OPS", 12), ("REV", 2)) for number in range(1, count + 1)]
FALSE_SCOPE = ("live_data", "paid_models", "external_sharing", "document_intake",
               "team_authentication", "financial_approval", "production_release_approved")


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid pilot specification or evidence record")


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def read_json(path: Path) -> tuple[dict, str]:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= 6_000_000)
    raw = path.read_bytes()
    require(len(raw) <= 6_000_000)
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=lambda _: require(False))
    require(isinstance(value, dict))
    return value, hashlib.sha256(raw).hexdigest()


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None and result.utcoffset() is not None)
    require(result <= datetime.now(timezone.utc))
    return result


def evidence_bytes(root: Path, item: dict) -> bytes:
    """Open confined evidence without following directory or file symlinks."""
    parts = PurePosixPath(item["path"]).parts
    require(parts[0] == "evidence" and all(p not in (".", "..") for p in parts))
    require(not any(re.search(r"(?:^\.|\.(?:key|env|pem|p12|pfx)$|token|password|secret|credential)",
                              p, re.IGNORECASE) for p in parts))
    flags = os.O_RDONLY | os.O_NOFOLLOW
    descriptor = os.open(root, flags | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file_fd = os.open(parts[-1], flags | os.O_NONBLOCK, dir_fd=descriptor)
        try:
            info = os.fstat(file_fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
            require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0)
            require(info.st_size == item["bytes"] <= 20_000_000)
            with os.fdopen(os.dup(file_fd), "rb") as stream:
                raw = stream.read(20_000_001)
            require(len(raw) == item["bytes"])
            require(hashlib.sha256(raw).hexdigest() == item["sha256"])
            return raw
        finally:
            os.close(file_fd)
    finally:
        os.close(descriptor)


def check_spec(spec_dir: Path, matrix_path: Path) -> tuple[dict, dict, str, str]:
    protocol, protocol_hash = read_json(spec_dir / "protocol.json")
    schema, schema_hash = read_json(spec_dir / "record.schema.json")
    Draft202012Validator.check_schema(schema)
    require(protocol["schema_version"] == 1 and protocol["id"] == "webapp-pilot/1")
    require(protocol["kind"] == "keystone.pilot-protocol")
    require(all(protocol["scope"][key] is False for key in FALSE_SCOPE))
    require(protocol["scope"]["classification"] == "synthetic")
    require(protocol["scope"]["network"] == "loopback_only")
    require(protocol["scope"]["analysts"] == 1)
    require(protocol["scope"]["workflows"] == ["research", "monitoring", "events", "news", "close"])
    require(protocol["workload"]["total_calculations"] == 6)
    require(protocol["workload"]["base_calculations"] == 5)
    require(protocol["workload"]["research_replacement_calculations"] == 1)
    require(protocol["workload"]["accepted_input_versions"] == 6)
    require(protocol["workload"]["datasets"] == 5)
    require(protocol["workload"]["concurrency"] == 1)
    require(all(protocol["trial_targets"][key] == 0 for key in
                ("provider_requests", "model_requests", "model_output_tokens")))
    checks = protocol["checks"]
    require([check["id"] for check in checks] == CHECK_IDS)
    for check in checks:
        group = check["id"].split("-")[1]
        require(check["phase"] == {"UAT": "7B", "OPS": "7C", "REV": "7D"}[group])
        expected_actor = "analyst" if group == "UAT" or check["id"] == "P7-REV-02" else "operator"
        require(check["actor"] == expected_actor)
        require(check["title"].strip() and check["pass_condition"].strip())
        require(len(check["production_gates"]) == len(set(check["production_gates"])))
    gates = set(re.findall(r"^\| (V1-[A-Z0-9]+-[0-9]{3}) \|", matrix_path.read_text(), re.M))
    crosswalk = protocol["production_crosswalk"]
    require(len(gates) == 26 and len(crosswalk) == len(gates))
    require({entry["gate"] for entry in crosswalk} == gates)
    for check in checks:
        require(set(check["production_gates"]) <= gates)
    for entry in crosswalk:
        require(entry["disposition"] in ("supporting_only", "blocked_external", "out_of_pilot"))
        require(entry["reason"].strip())
        require(entry["pilot_checks"] == [c["id"] for c in checks if entry["gate"] in c["production_gates"]])
    require({d["id"] for d in protocol["dependencies"]} == {
        "DEP-BACKUP", "DEP-KEYS", "DEP-DR", "DEP-RIGHTS", "DEP-FPA",
        "DEP-NEWS", "DEP-ACCESSIBILITY", "DEP-CAPACITY"})
    require(len(protocol["dependencies"]) == 8)
    require(all(d["status"] in ("deferred", "blocked", "not_assessed") and
                d["detail"].strip() for d in protocol["dependencies"]))
    return protocol, schema, protocol_hash, schema_hash


def validate_record(record_path: Path, spec_dir: Path = SPEC,
                    matrix_path: Path = ROOT / "docs/production/v1/acceptance-matrix.md") -> dict:
    protocol, schema, protocol_hash, schema_hash = check_spec(spec_dir, matrix_path)
    record, _ = read_json(record_path)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    require(record["protocol_sha256"] == protocol_hash and record["schema_sha256"] == schema_hash)
    require([r["check_id"] for r in record["results"]] == CHECK_IDS)
    candidate = record["candidate"]
    assigned = candidate["state"] == "frozen"
    require(all((value is not None) == assigned for key, value in candidate.items() if key != "state"))
    frozen_at = instant(candidate["frozen_at"]) if assigned else None
    has_attempts = any(row["attempts"] for row in record["results"])
    if assigned or has_attempts:
        info = record_path.lstat()
        parent = record_path.parent.stat()
        require(info.st_uid == parent.st_uid == os.getuid() and info.st_nlink == 1)
        require(info.st_mode & 0o077 == 0 and parent.st_mode & 0o077 == 0)
    attempt_ids, evidence_seen = set(), {}
    for row, check in zip(record["results"], protocol["checks"]):
        attempts = row["attempts"]
        require((row["status"] == "not_assessed") == (len(attempts) == 0))
        previous_end = frozen_at
        for attempt in attempts:
            require(assigned and attempt["id"] not in attempt_ids)
            attempt_ids.add(attempt["id"])
            start, end = instant(attempt["started_at"]), instant(attempt["finished_at"])
            require(previous_end <= start <= end)
            previous_end = end
            require((attempt["assistance"] == "none") == (attempt["assistance_detail"] is None))
            require((attempt["outcome"] == "blocked") == (attempt["blocking_reason"] is not None))
            require(attempt["observed"].strip() and attempt["actor"]["label"].strip())
            require(all(value is None or value.strip() for value in
                        (attempt["assistance_detail"], attempt["blocking_reason"])))
            require(attempt["outcome"] != "passed" or bool(attempt["evidence"]))
            for item in attempt["evidence"]:
                identity = (item["sha256"], item["bytes"])
                require(item["path"] not in evidence_seen or evidence_seen[item["path"]] == identity)
                if item["path"] not in evidence_seen:
                    evidence_bytes(record_path.parent.resolve(), item)
                    evidence_seen[item["path"]] = identity
                    require(sum(size for _, size in evidence_seen.values()) <= 50_000_000)
        if row["status"] in ("passed", "failed", "blocked"):
            require(attempts[-1]["outcome"] == row["status"])
        if row["status"] == "passed":
            require(attempts[-1]["assistance"] == "none")
            require(attempts[-1]["actor"]["role"] == check["actor"])
    return {
        "status": "specification_consistent",
        "candidate_state": candidate["state"],
        "checks": len(record["results"]),
        "result_counts": dict(Counter(row["status"] for row in record["results"])),
        "readiness": "not_assessed" if not has_attempts else "requires_human_evidence_review",
        "financial_approval": False,
        "production_release_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, default=SPEC / "record.template.json")
    args = parser.parse_args(argv)
    try:
        summary = validate_record(args.record)
    except Exception:
        # Do not echo untrusted observations, reviewer names, paths or schema values.
        print(json.dumps({"status": "pilot_spec_invalid", "readiness": "not_assessed",
                          "financial_approval": False, "production_release_approved": False}))
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
