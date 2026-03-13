import json
import re
import os
import shutil
import subprocess
import requests
from pathlib import Path
from dotenv import dotenv_values

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
    
    missing = [item for item in expected if item not in response]
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

