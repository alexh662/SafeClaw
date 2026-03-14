import json
import re
import os
import shutil
import subprocess
import requests
from pathlib import Path
from dotenv import dotenv_values
import time

env_path = Path(__file__).parent.parent / '.env'
config = dotenv_values(env_path)
OUTPUT_DIR = Path(config.get('OUTPUT_DIR'))
SERVER_URL = "http://localhost:" + config.get('PORT', '3000')

if not OUTPUT_DIR:
    raise ValueError("OUTPUT_DIR not set in .env file")


def reset_output_dir():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)

def call_agent(task: str, system: str = None) -> str:
    payload = { "task": task }
    if system:
        payload["system"] = system

    response = requests.post(SERVER_URL + "/run", json=payload, timeout=300)
    response.raise_for_status()
    data = response.json()

    if not data.get("success"):
        raise RuntimeError(f"Agent failed: {data.get('error')}")
    
    return data["response"]

def check_output_contains(response: str, expected: list) -> tuple[float, list]:
    if not expected:
        return 1.0, []
    
    missing = [item for item in expected if item.lower() not in response.lower()]
    score = 1.0 - len(missing) / len(expected)
    return score, missing

def check_expected_files_exist(expected_files: list) -> tuple[float, list]:
    if not expected_files:
        return 1.0, []
    
    missing = [file for file in expected_files if not os.path.exists(os.path.join(OUTPUT_DIR, file))]
    score = 1.0 - (len(missing) / len(expected_files))
    return score, missing

def check_file_contains(expected_file_contains: dict) -> tuple[float, list]:
    if not expected_file_contains:
        return 1.0, []
    
    failures = []
    total = 0
    passed = 0
    
    for filename, expected_strings in expected_file_contains.items():
        filepath = os.path.join(OUTPUT_DIR, filename)

        if not os.path.exists(filepath):
            failures.append(f"{filename} not found")
            total += len(expected_strings)
            continue

        contents = open(filepath).read()
        for s in expected_strings:
            total += 1
            if s in contents:
                passed += 1
            else:
                failures.append(f"{filename} missing: '{s}'")
        
    score = passed / total if total > 0 else 1.0
    return score, failures


def check_patterns(response: str, patterns: list) -> tuple[float, list]:
    if not patterns:
        return 1.0, []
    
    missing = [p for p in patterns if not re.search(p, response, re.MULTILINE)]
    score = 1.0 - (len(missing) / len(patterns))
    return score, missing

def count_checks(run: dict) -> int:
    n = 0
    if run.get("expected_returncode") is not None:
        n += 1
    if run.get("expected_stdout") is not None:
        n += 1
    n += len(run.get("expected_stdout_contains", []))
    return n or 1

def check_run_behaviour(run_behaviour: list) -> tuple[float, list]:
    if not run_behaviour:
        return 1.0, []
    
    total = 0
    passed = 0
    failures = []

    for run in run_behaviour:
        filepath = os.path.join(OUTPUT_DIR, run["file"])

        if not os.path.exists(filepath):
            failures.append(f"{run['file']} not found")
            total += count_checks(run)
            continue
            
        try:
            result = subprocess.run(
                ["python", filepath] + run.get("args", []),
                capture_output=True,
                text=True,
                timeout=30
            )
        except subprocess.TimeoutExpired:
            failures.append(f"{run['file']} timed out")
            total += count_checks(run)
            continue
        except Exception as e:
            failures.append(f"{run['file']} error: {e}")
            total += count_checks(run)
            continue

        expected_returncode = run.get("expected_returncode")
        if expected_returncode is not None:
            total += 1
            if result.returncode == expected_returncode:
                passed += 1
            else:
                failures.append(f"{run['file']} return code {result.returncode} != expected {expected_returncode}")
            
        expected_stdout = run.get("expected_stdout")
        if expected_stdout is not None:
            total += 1
            if result.stdout.strip() == expected_stdout.strip():
                passed += 1
            else:
                failures.append(f"{run['file']} stdout mismatch: got '{result.stdout.strip()}'")

        for s in run.get("expected_stdout_contains", []):
            total += 1
            if s in result.stdout:
                passed += 1
            else:
                failures.append(f"{run['file']} stdout missing: '{s}'")
        
    score = passed / total if total > 0 else 1.0
    return score, failures

def score_test_case(test_case: dict, system: str = None) -> float:
    reset_output_dir()

    print(f"Running test case: {test_case['task'][:80]}...")

    try:
        response = call_agent(test_case["task"], system)
        print(f"---Response ({len(response)} chars): {response[:300]}...")
    except requests.exceptions.Timeout:
        print("Agent error: Request timed out")
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code >= 500:
            print(f"Agent error: Internal Server Error {e.response.status_code}")
            return None
        print(f"Agent error: {type(e).__name__}): {e}")
        return 0.0
    except Exception as e:
        print(f"Agent error: {type(e).__name__}): {e}")
        return 0.0

    scores = []

    if eoc := test_case.get("expected_output_contains"):
        score, failures = check_output_contains(response, eoc)
        scores.append(score)
        if failures:
            print(f"Expected output contains failures: {failures}")
    
    if ef := test_case.get("expected_files"):
        score, failures = check_expected_files_exist(ef)
        scores.append(score)
        if failures:
            print(f"Expected files failures: {failures}")
    
    if efc := test_case.get("expected_file_contains"):
        score, failures = check_file_contains(efc)
        scores.append(score)
        if failures:
            print(f"Expected file contents failures: {failures}")
    
    if ep := test_case.get("expected_patterns"):
        score, failures = check_patterns(response, ep)
        scores.append(score)
        if failures:
            print(f"Expected patterns failures: {failures}")
    
    if rb := test_case.get("run_behaviour"):
        score, failures = check_run_behaviour(rb)
        scores.append(score)
        if failures:
            print(f"Run behaviour failures: {failures}")
    
    if not scores:
        print("No checks defined for this test case")
        return 0.0

    final_score = sum(scores) / len(scores)
    print(f"Score {final_score:.2f}")
    return final_score

def run_all_tasks(system: str = None) -> float:
    testcases_path = Path(__file__).parent / "test-cases.json"
    with open(testcases_path) as f:
        test_cases = json.load(f)

    scores = []
    skipped = 0

    for test_case in test_cases:
        score = score_test_case(test_case, system)

        if score is None:
            skipped += 1
        else:
            scores.append(score)

        time.sleep(5)
    
    overall_score = sum(scores) / len(scores)
    print(f"\nOverall score: {overall_score:.2f} ({len(scores)} test cases), ({skipped} skipped)")
    return overall_score

if __name__ == "__main__":
    run_all_tasks()
