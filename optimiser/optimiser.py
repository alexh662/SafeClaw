import argparse
import json
import sys
import time
from pathlib import Path
import dspy
import requests
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).parent))

from metric import (
    check_expected_files_exist,
    check_file_contains,
    check_output_contains,
    check_patterns,
    check_run_behaviour,
    reset_output_dir,
    call_agent,
)

# config

env_path = Path(__file__).parent.parent / ".env"
config = dotenv_values(env_path)

ANTHROPIC_API_KEY = config.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in .env")

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

testcases_path = Path(__file__).parent / "test-cases.json"
with open(testcases_path) as f:
    TEST_CASES = json.load(f)

# dspy setup

# lm = dspy.LM("anthropic/claude-sonnet-4-6", api_key=ANTHROPIC_API_KEY)
lm = dspy.LM("anthropic/claude-haiku-4-5", api_key=ANTHROPIC_API_KEY)
dspy.configure(lm=lm)

# starting system prompt for MIPROv2 to build on

class AgentTask(dspy.Signature):
    """You are OpenClaw, an autonomous Linux engineer running inside a secure justbash sandbox.
The user's project files are at your working directory. Always use this as your base for reading project files.
IMPORTANT: The output directory is /home/user/output. It already exists. Always write output files here.
RULES:
1. Use bash for ALL tasks: writing files, running code, chaining commands.
2. After writing any script, ALWAYS immediately run it using the bash tool.
3. If something fails, read the error carefully and self-correct.
4. You are in a Python 3.13 stdlib-only environment. No pip, no external packages. Implement everything using stdlib.
5. Output files go to /home/user/output — never create your own output directory.
6. Always write a final text response after completing all steps. Never end on a tool call.
7. When a task specifies an exact output format, follow it precisely with no extra padding or spacing."""

    task: str = dspy.InputField(desc="the coding or scripting task to perform")
    response: str = dspy.OutputField(desc="summary of what was done including output, file paths, and any errors")

# module

class AgentModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(AgentTask)

    def forward(self, task: str) -> dspy.Prediction:
        # extract the current system prompt from MIPROv2
        system_prompt = self.predict.signature.instructions

        reset_output_dir()
        try:
            response = call_agent(task, system=system_prompt)
        except requests.exceptions.Timeout:
            print("  [AgentModule] timeout")
            response = ""
        except requests.exceptions.HTTPError as e:
            print(f"  [AgentModule] HTTP error: {e.response.status_code}")
            response = ""
        except Exception as e:
            print(f"  [AgentModule] error: {e}")
            response = ""

        return dspy.Prediction(response=response)


# scoring

def score_response(test_case: dict, response: str) -> float:
    if not response:
        return 0.0

    scores = []

    if eoc := test_case.get("expected_output_contains"):
        score, _ = check_output_contains(response, eoc)
        scores.append(score)

    if ef := test_case.get("expected_files"):
        score, _ = check_expected_files_exist(ef)
        scores.append(score)

    if efc := test_case.get("expected_file_contains"):
        score, _ = check_file_contains(efc)
        scores.append(score)

    if ep := test_case.get("expected_patterns"):
        score, _ = check_patterns(response, ep)
        scores.append(score)

    if rb := test_case.get("run_behaviour"):
        score, _ = check_run_behaviour(rb)
        scores.append(score)

    return sum(scores) / len(scores) if scores else 0.0

# dspy metric wrapper

def dspy_metric(example, pred, trace=None, pred_name=None, pred_trace=None):
    test_case = example.test_case
    score = score_response(test_case, pred.response)
    print(f"  score={score:.2f}  [{test_case.get('category', '?')}]  {test_case['task'][:55]}...")
    return score


# build train and dev dataset

def build_dataset(categories: list[str] | None = None):
    cases = TEST_CASES
    if categories:
        cases = [tc for tc in cases if tc.get("category") in categories]
    if not cases:
        raise ValueError(f"No test cases found for categories: {categories}")

    # split cases to 80/20 train/dev
    by_cat: dict[str, list] = {}
    for tc in cases:
        by_cat.setdefault(tc.get("category", "unknown"), []).append(tc)

    train_tcs, dev_tcs = [], []

    for cat_cases in by_cat.values():
        split = max(1, int(len(cat_cases) * 0.8))
        train_tcs.extend(cat_cases[:split])
        dev_tcs.extend(cat_cases[split:])

    def to_examples(tcs):
        return [
            dspy.Example(task=tc["task"], test_case=tc).with_inputs("task")
            for tc in tcs
        ]

    return to_examples(train_tcs), to_examples(dev_tcs)


# MIPROv2 optimisation

def run_optimiser(trainset, num_candidates: int = 8) -> AgentModule:
    # try:
    #     optimiser = dspy.GEPA(
    #         metric=dspy_metric,
    #         max_full_evals=num_candidates,
    #         num_threads=1,
    #         reflection_lm=lm,
    #     )
    # except AttributeError:
    #     print("gepa not available using MIPROv2 instead")
    #     optimiser = dspy.MIPROv2(
    #         metric=dspy_metric,
    #         num_candidates=num_candidates,
    #         max_bootstrapped_demos=0,
    #         max_labeled_demos=0,
    #         num_threads=1,
    #         verbose=True,
    #     )
    optimiser = dspy.MIPROv2(
        metric=dspy_metric,
        auto=None,
        num_candidates=num_candidates,
        max_bootstrapped_demos=0,
        max_labeled_demos=0,
        num_threads=1,
        verbose=True,
    )

    program = AgentModule()
    return optimiser.compile(program, trainset=trainset, num_trials=int(num_candidates * 1.5), minibatch_size=min(12, len(trainset)))


# evaluation

def evaluate(program: AgentModule, dataset, label: str = "eval") -> float:
    print(f"\n{'='*60}\n{label}\n{'='*60}")

    by_category: dict[str, list[float]] = {}
    skipped = 0

    for example in dataset:
        tc = example.test_case
        try:
            pred = program(task=tc["task"])
            score = score_response(tc, pred.response)
        except requests.exceptions.Timeout:
            print(f"skipped (timeout): {tc['task'][:55]}...")
            skipped += 1
            continue
        except requests.exceptions.HTTPError as e:
            if e.response.status_code >= 500:
                print(f"skipped (server error): {tc['task'][:55]}...")
                skipped += 1
                continue
            score = 0.0

        cat = tc.get("category", "unknown")
        by_category.setdefault(cat, []).append(score)
        status = "PASS" if score >= 0.8 else ("PARTIAL" if score >= 0.5 else "FAIL")
        print(f"[{status}] {score:.2f} [{cat}] {tc['task'][:55]}...")
        time.sleep(3)

    all_scores = [s for scores in by_category.values() for s in scores]
    if not all_scores:
        print("No scores recorded")
        return 0.0

    overall = sum(all_scores) / len(all_scores)

    print(f"\nBy category:")
    for cat, scores in sorted(by_category.items()):
        avg = sum(scores) / len(scores)
        print(f"{cat:<20} {avg:.2f} ({len(scores)} cases)")

    print(f"\nOverall: {overall:.2f}  ({len(all_scores)} scored, {skipped} skipped)")
    return overall


# saved optimised results to optimisor/results

def save(program: AgentModule):
    state_path = RESULTS_DIR / "optimised_MIPROv2.json"
    prompt_path = RESULTS_DIR / "system_prompt_MIPROv2.txt"

    program.save(str(state_path))
    system_prompt = program.predict.signature.instructions
    prompt_path.write_text(system_prompt, encoding="utf-8")

    print(f"\nProgram state saved to: {state_path}")
    print(f"System prompt saved to: {prompt_path}")
    print(f"\n{'='*60}\nOptimised system prompt:\n{'='*60}")
    print(system_prompt)

# load saved optimised programs from optimisor/result

def load() -> AgentModule:
    state_path = RESULTS_DIR / "optimised_MIPROv2.json"
    if not state_path.exists():
        raise FileNotFoundError(f"No saved program at {state_path} — run optimisation first")
    program = AgentModule()
    program.load(str(state_path))
    print(f"Loaded from {state_path}")
    
    return program


# handle arguments

def parse_args():
    p = argparse.ArgumentParser(description="SafeClaw MIPROv2 optimizer")
    p.add_argument("--eval-only", action="store_true", help="skip optimisation, just evaluate")
    p.add_argument("--load", action="store_true", help="load previously saved optimised program")
    p.add_argument("--candidates", type=int, default=8, help="number of candidate prompts (default: 8)")
    p.add_argument("--categories", nargs="*", metavar="CAT", help="restrict to categories: file_creation bug_fixing bash_scripting multi_step")
    
    return p.parse_args()


def main():
    args = parse_args()
    trainset, devset = build_dataset(categories=args.categories)
    print(f"Dataset: {len(trainset)} train, {len(devset)} dev  (categories: {args.categories or 'all'})")

    if args.load:
        program = load()
        evaluate(program, devset, label="loaded (optimised MIPROv2)')")
        return

    if args.eval_only:
        evaluate(AgentModule(), trainset + devset, label="baseline")
        return

    # baseline
    print("\nBaseline evaluation...")
    baseline = evaluate(AgentModule(), devset, label="baseline")

    # optimise
    print(f"\nRunning MIPROv2 ({args.candidates} candidates)...")
    optimised = run_optimiser(trainset, num_candidates=args.candidates)

    # save optimised result
    save(optimised)

    # post optimisation evaluation
    print("\nPost optimisation evaluation...")
    final = evaluate(optimised, devset, label="optimised MIPROv2")

    delta = final - baseline
    direction = "UP" if delta > 0 else ("DOWN" if delta < 0 else "NO CHANGE")
    print(f"\n{'='*60}")
    print(f"Baseline:  {baseline:.2f}")
    print(f"Optimised: {final:.2f}  {direction} {delta:+.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
