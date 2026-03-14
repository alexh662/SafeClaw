# SafeClaw

A secure, sandboxed AI agent inspired by OpenClaw, built with TypeScript and just-bash to safely execute code in an isolated environment. 

Includes a prompt optimisation pipeline using DSPy MIPROv2, with 20 test cases across four categories: file creation, bug fixing, bash scripting, and multi-step pipelines.

## Tech Stack

- **Agent**: TypeScript, Anthropic API (claude-sonnet-4-6 or haiku-4-5), just-bash
- **Server**: Hono on Node.js
- **Optimizer**: Python, DSPy MIPROv2

## Dev Instructions

### Prerequisites

- Node.js 18+
- Python 3.13
- An Anthropic API key

### Setup

1. Clone the repo and install dependencies:

```bash
git clone <repo-url>
cd SafeClaw
npm install
```

2. Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Required variables:

```
ANTHROPIC_API_KEY=your_key_here
OUTPUT_DIR=/home/user/output
PORT=3000
```

### Running the Agent

**CLI mode:**

```bash
npm start
```

**Server mode:**

```bash
npm start -- --server
```

The server runs on `http://localhost:3000`. Send tasks via POST to `/run`:

```bash
curl -X POST http://localhost:3000/run \
  -H "Content-Type: application/json" \
  -d '{"task": "cresystem_prompt_MIPROv2ate a python script that prints hello world and save it to /home/user/output"}'
```

## Optimizer

The optimizer evaluates and improves the agent system prompt using DSPy MIPROv2.

### Setup

```bash
cd optimizer
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Usage

Run a baseline evaluation:

```bash
python optimizer.py --eval-only
```

Run full optimisation:

```bash
python optimizer.py --candidates 4
```

Restrict to specific categories:

```bash
python optimizer.py --categories bash_scripting multi_step --candidates 4
```

The optimised system prompt is saved to `optimizer/results/system_prompt_MIPROv2.txt`.
