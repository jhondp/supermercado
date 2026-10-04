from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def load(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))  # PyYAML parses the `on` key as True
    return data


def runs(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_weekly_runs_monday_morning_and_on_demand() -> None:
    workflow = load("weekly.yml")
    assert workflow["on"]["schedule"][0]["cron"] == "0 9 * * 1"
    assert "workflow_dispatch" in workflow["on"]


def test_weekly_collects_commits_reports_and_builds() -> None:
    script = runs(load("weekly.yml")["jobs"]["collect"])
    for fragment in (
        "python -m supermercado collect",
        "git add data/prices",
        "python -m supermercado issue-body",
        "gh issue create",
        "python -m supermercado build --out dist",
    ):
        assert fragment in script


def test_deploy_waits_for_collect() -> None:
    assert load("weekly.yml")["jobs"]["deploy"]["needs"] == "collect"


def test_permissions_are_least_privilege_per_job() -> None:
    workflow = load("weekly.yml")
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["collect"]["permissions"] == {"contents": "write", "issues": "write"}
    assert workflow["jobs"]["deploy"]["permissions"] == {"pages": "write", "id-token": "write"}


def test_no_expression_is_interpolated_into_run_scripts() -> None:
    for job in load("weekly.yml")["jobs"].values():
        assert "${{" not in runs(job)


def test_actions_are_pinned_to_a_version() -> None:
    for job in load("weekly.yml")["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert "@v" in step["uses"]


def test_issue_step_passes_body_as_file_and_still_runs_after_failures() -> None:
    steps = load("weekly.yml")["jobs"]["collect"]["steps"]
    issue = next(s for s in steps if "gh issue create" in s.get("run", ""))
    assert issue["if"] == "always()"
    assert "--body-file" in issue["run"]
