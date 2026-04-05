# SQL Query Debugger

An **OpenEnv**-compliant environment for training and evaluating AI agents on real-world SQL debugging tasks.

## Overview

SQL debugging is a task that developers perform daily. This environment presents agents with broken SQL queries and challenges them to diagnose and fix the issues to produce expected results.

**Why SQL Debugging?**

- **Real-world utility**: Developers spend significant time debugging SQL queries
- **Clear success criteria**: Queries either produce correct results or they don't
- **Graduated difficulty**: From simple typos to complex subquery logic errors
- **Partial progress signals**: Reward for syntactically valid queries, correct row counts, partial matches

## Quick Start

### Local Development

```bash
# Clone and install
git clone https://huggingface.co/spaces/YOUR_USERNAME/sql-query-debugger
cd sql-query-debugger
pip install -r requirements.txt

# Run the server
uvicorn server.main:app --host 0.0.0.0 --port 7860

# In another terminal, run baseline
export HF_TOKEN="your-huggingface-token"
python inference.py
```

### Docker

```bash
# Build and run
docker build -t sql-query-debugger .
docker run -p 7860:7860 sql-query-debugger

# Test the API
curl -X POST http://localhost:7860/reset -H "Content-Type: application/json" -d '{"task_id": "easy_syntax_fix"}'
```

## Tasks

### 1. Easy: Syntax Fix (`easy_syntax_fix`)

**Difficulty**: Easy | **Max Steps**: 10

Fix a query with simple SQL keyword typos. The agent must identify and correct spelling errors like `SELCT` → `SELECT`, `FORM` → `FROM`.

**Broken Query**:

```sql
SELCT name, email FORM customers WERE state = 'CA' ORDERY BY name;
```

**Expected**: Return California customers sorted by name.

---

### 2. Medium: JOIN Logic (`medium_join_logic`)

**Difficulty**: Medium | **Max Steps**: 12

Fix incorrect JOIN conditions and GROUP BY issues. The agent must identify that the JOIN uses the wrong column and understand LEFT vs INNER JOIN behavior.

**Issues**:

- Wrong JOIN column (`o.id` instead of `o.customer_id`)
- LEFT JOIN with WHERE clause filtering
- Missing column in GROUP BY

---

### 3. Hard: Complex Analytics (`hard_complex_analysis`)

**Difficulty**: Hard | **Max Steps**: 15

Fix a complex analytics query with subquery and correlation issues. The agent must understand that finding "latest order per customer" requires a correlated subquery, not a global max.

**Issues**:

- Global MAX instead of per-customer MAX
- Wrong JOIN column in subquery
- Missing correlation in nested query

---

## Action Space

Agents can take three types of actions:

| Action          | Description                                 | Parameters              |
| --------------- | ------------------------------------------- | ----------------------- |
| `submit_fix`    | Submit a corrected SQL query for grading    | `query: str` (required) |
| `execute_query` | Test a query to see results without grading | `query: str` (required) |
| `request_hint`  | Request a hint about what's wrong           | None                    |

**Example Action**:

```json
{
  "action_type": "submit_fix",
  "query": "SELECT name, email FROM customers WHERE state = 'CA' ORDER BY name;"
}
```

## Observation Space

Each observation includes:

| Field                  | Type   | Description                      |
| ---------------------- | ------ | -------------------------------- |
| `task_id`              | `str`  | Current task identifier          |
| `task_description`     | `str`  | What the query should accomplish |
| `schema_ddl`           | `str`  | CREATE TABLE statements          |
| `sample_data`          | `str`  | Table contents as formatted text |
| `broken_query`         | `str`  | The SQL query to fix             |
| `error_message`        | `str?` | Error from last execution        |
| `expected_output_hint` | `str`  | Description of expected results  |
| `attempts_remaining`   | `int`  | Steps left before episode ends   |
| `current_step`         | `int`  | Current step number              |
| `max_steps`            | `int`  | Maximum allowed steps            |
| `last_query_result`    | `str?` | Result from last `execute_query` |
| `hints_used`           | `int`  | Number of hints requested        |

## Reward Function

Rewards are dense and composed of multiple signals:

| Component      | Weight | Description                          |
| -------------- | ------ | ------------------------------------ |
| `syntax_valid` | 0.2    | Query executes without syntax errors |
| `row_count`    | 0.2    | Returns correct number of rows       |
| `column_count` | 0.1    | Returns correct number of columns    |
| `data_correct` | 0.5    | Returns exact expected data          |

**Reward Shaping**:

- **Improvement bonus**: Extra reward for scores that improve on previous attempts
- **Efficiency bonus**: Solving with fewer steps yields bonus reward
- **Hint penalty**: Small penalty (-0.02) for requesting hints
- **Invalid action penalty**: Small penalty (-0.05) for invalid actions

**Score Range**: All final scores are normalized to [0.0, 1.0]

## API Endpoints

| Endpoint                     | Method | Description                                            |
| ---------------------------- | ------ | ------------------------------------------------------ |
| `/reset`                     | POST   | Reset environment with optional `task_id`              |
| `/step`                      | POST   | Execute action with `action_type` and optional `query` |
| `/state`                     | GET    | Get current environment state                          |
| `/health`                    | GET    | Health check                                           |
| `/tasks`                     | GET    | List available tasks                                   |
| `/openenv/info`              | GET    | OpenEnv metadata                                       |
| `/openenv/observation_space` | GET    | Observation schema                                     |
| `/openenv/action_space`      | GET    | Action schema                                          |

## Baseline Scores

Expected baseline scores with Qwen2.5-72B-Instruct:

| Task                    | Expected Score | Notes                                 |
| ----------------------- | -------------- | ------------------------------------- |
| `easy_syntax_fix`       | 0.85-1.0       | Should solve reliably                 |
| `medium_join_logic`     | 0.6-0.85       | Requires understanding JOIN semantics |
| `hard_complex_analysis` | 0.3-0.6        | Complex subquery reasoning needed     |

**Average**: ~0.65

## Environment Variables

| Variable                | Required | Default                            | Description             |
| ----------------------- | -------- | ---------------------------------- | ----------------------- |
| `HF_TOKEN` or `API_KEY` | Yes      | -                                  | API key for LLM service |
| `API_BASE_URL`          | No       | `https://router.huggingface.co/v1` | LLM API endpoint        |
| `MODEL_NAME`            | No       | `Qwen/Qwen2.5-72B-Instruct`        | Model to use            |
| `ENV_BASE_URL`          | No       | `http://localhost:7860`            | Environment server URL  |

## Project Structure

```
sql-query-debugger/
├── openenv.yaml           # OpenEnv specification
├── Dockerfile             # Container definition
├── requirements.txt       # Python dependencies
├── inference.py           # Baseline inference script
├── README.md              # This file
├── server/
│   ├── __init__.py        # Package exports
│   ├── main.py            # FastAPI server
│   ├── environment.py     # Environment implementation
│   ├── models.py          # Pydantic models
│   └── tasks.py           # Task definitions & graders
└── tests/
    └── test_env.py        # Unit tests
```

## Grading Criteria

The graders are **deterministic** and based on exact result matching:

1. Execute the submitted query against an in-memory SQLite database
2. Compare results to expected output with tolerance for float precision
3. Compute partial scores for syntax validity, row count, column count, and data correctness
4. Return final score as weighted sum

## Validation

Run the OpenEnv validation script before submitting:

```bash
# Install openenv-core
pip install openenv-core

# Validate spec compliance
openenv validate

# Test Docker build
docker build -t sql-query-debugger .
docker run -p 7860:7860 sql-query-debugger
curl -X POST http://localhost:7860/reset
```

## License

MIT License

## Contributing

Contributions welcome! Please open an issue or PR on the HuggingFace Space repository.
