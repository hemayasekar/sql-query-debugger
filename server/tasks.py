"""SQL Query Debugging Tasks with Graders.

Three difficulty levels:
- Easy: Simple syntax errors (typos, missing keywords)
- Medium: Logic errors (wrong joins, incorrect conditions)
- Hard: Complex issues (subquery errors, aggregation bugs, performance issues)
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class TaskDefinition:
    """Definition of a SQL debugging task."""

    task_id: str
    difficulty: str  # easy, medium, hard
    description: str
    schema_ddl: str
    sample_data_sql: str
    broken_query: str
    correct_query: str
    expected_output: list[tuple]
    expected_output_hint: str
    hints: list[str]
    max_steps: int
    error_types: list[str]  # Types of errors in the broken query


# =============================================================================
# EASY TASK: Simple Syntax Errors
# =============================================================================

EASY_TASK = TaskDefinition(
    task_id="easy_syntax_fix",
    difficulty="easy",
    description="Fix a query with simple syntax errors to retrieve all customers from California",
    schema_ddl="""
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at DATE NOT NULL
);
""",
    sample_data_sql="""
INSERT INTO customers VALUES (1, 'Alice Johnson', 'alice@email.com', 'CA', '2024-01-15');
INSERT INTO customers VALUES (2, 'Bob Smith', 'bob@email.com', 'NY', '2024-02-20');
INSERT INTO customers VALUES (3, 'Carol Davis', 'carol@email.com', 'CA', '2024-03-10');
INSERT INTO customers VALUES (4, 'David Wilson', 'david@email.com', 'TX', '2024-01-25');
INSERT INTO customers VALUES (5, 'Eve Brown', 'eve@email.com', 'CA', '2024-04-05');
""",
    broken_query="""
SELCT name, email FORM customers WERE state = 'CA' ORDERY BY name;
""",
    correct_query="""
SELECT name, email FROM customers WHERE state = 'CA' ORDER BY name;
""",
    expected_output=[
        ("Alice Johnson", "alice@email.com"),
        ("Carol Davis", "carol@email.com"),
        ("Eve Brown", "eve@email.com"),
    ],
    expected_output_hint="Should return 3 rows with name and email of California customers, sorted alphabetically",
    hints=[
        "Check the spelling of SQL keywords like SELECT, FROM, WHERE, ORDER BY",
        "The query has 4 misspelled keywords",
        "SELCT→SELECT, FORM→FROM, WERE→WHERE, ORDERY→ORDER",
    ],
    max_steps=10,
    error_types=["syntax_typo"],
)


# =============================================================================
# MEDIUM TASK: Logic Errors with JOINs
# =============================================================================

MEDIUM_TASK = TaskDefinition(
    task_id="medium_join_logic",
    difficulty="medium",
    description="Fix a query that should find total order amounts per customer, but has JOIN and aggregation issues",
    schema_ddl="""
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    tier TEXT NOT NULL
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
""",
    sample_data_sql="""
INSERT INTO customers VALUES (1, 'Acme Corp', 'gold');
INSERT INTO customers VALUES (2, 'Beta Inc', 'silver');
INSERT INTO customers VALUES (3, 'Gamma LLC', 'gold');
INSERT INTO customers VALUES (4, 'Delta Co', 'bronze');

INSERT INTO orders VALUES (1, 1, 500.00, 'completed');
INSERT INTO orders VALUES (2, 1, 300.00, 'completed');
INSERT INTO orders VALUES (3, 2, 150.00, 'completed');
INSERT INTO orders VALUES (4, 2, 200.00, 'cancelled');
INSERT INTO orders VALUES (5, 3, 1000.00, 'completed');
INSERT INTO orders VALUES (6, 3, 250.00, 'completed');
INSERT INTO orders VALUES (7, 1, 100.00, 'pending');
""",
    broken_query="""
SELECT c.name, SUM(o.amount) as total
FROM customers c
LEFT JOIN orders o ON c.id = o.id
WHERE o.status = 'completed'
GROUP BY c.id;
""",
    correct_query="""
SELECT c.name, SUM(o.amount) as total
FROM customers c
INNER JOIN orders o ON c.id = o.customer_id
WHERE o.status = 'completed'
GROUP BY c.id, c.name
ORDER BY total DESC;
""",
    expected_output=[
        ("Gamma LLC", 1250.00),
        ("Acme Corp", 800.00),
        ("Beta Inc", 150.00),
    ],
    expected_output_hint="Should return 3 customers with completed orders and their totals, ordered by total descending",
    hints=[
        "Check the JOIN condition - what column should orders be joined on?",
        "The LEFT JOIN becomes problematic with the WHERE clause filtering",
        "JOIN should be ON c.id = o.customer_id, consider using INNER JOIN for filtering",
    ],
    max_steps=12,
    error_types=["wrong_join_column", "join_type_issue", "missing_group_by_column"],
)


# =============================================================================
# HARD TASK: Complex Subquery and Window Function Issues
# =============================================================================

HARD_TASK = TaskDefinition(
    task_id="hard_complex_analysis",
    difficulty="hard",
    description="Fix a complex analytics query that should find customers whose latest order exceeds their average order amount",
    schema_ddl="""
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    segment TEXT NOT NULL
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    order_date DATE NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
""",
    sample_data_sql="""
INSERT INTO customers VALUES (1, 'TechStart', 'enterprise');
INSERT INTO customers VALUES (2, 'SmallBiz', 'smb');
INSERT INTO customers VALUES (3, 'MegaCorp', 'enterprise');
INSERT INTO customers VALUES (4, 'LocalShop', 'smb');

INSERT INTO orders VALUES (1, 1, 100.00, '2024-01-01');
INSERT INTO orders VALUES (2, 1, 200.00, '2024-02-01');
INSERT INTO orders VALUES (3, 1, 500.00, '2024-03-01');
INSERT INTO orders VALUES (4, 2, 50.00, '2024-01-15');
INSERT INTO orders VALUES (5, 2, 75.00, '2024-02-15');
INSERT INTO orders VALUES (6, 2, 60.00, '2024-03-15');
INSERT INTO orders VALUES (7, 3, 1000.00, '2024-01-10');
INSERT INTO orders VALUES (8, 3, 2000.00, '2024-02-10');
INSERT INTO orders VALUES (9, 3, 1500.00, '2024-03-10');
INSERT INTO orders VALUES (10, 4, 25.00, '2024-01-20');
INSERT INTO orders VALUES (11, 4, 30.00, '2024-02-20');
INSERT INTO orders VALUES (12, 4, 100.00, '2024-03-20');
""",
    broken_query="""
SELECT c.name, c.segment, latest.amount as latest_order, avg_order.avg_amount
FROM customers c
JOIN (
    SELECT customer_id, amount
    FROM orders
    WHERE order_date = (SELECT MAX(order_date) FROM orders)
) latest ON c.id = latest.customer_id
JOIN (
    SELECT customer_id, AVG(amount) as avg_amount
    FROM orders
    GROUP BY customer_id
) avg_order ON c.id = avg_order.id
WHERE latest.amount > avg_order.avg_amount;
""",
    correct_query="""
SELECT c.name, c.segment, latest.amount as latest_order, avg_order.avg_amount
FROM customers c
JOIN (
    SELECT o1.customer_id, o1.amount
    FROM orders o1
    INNER JOIN (
        SELECT customer_id, MAX(order_date) as max_date
        FROM orders
        GROUP BY customer_id
    ) o2 ON o1.customer_id = o2.customer_id AND o1.order_date = o2.max_date
) latest ON c.id = latest.customer_id
JOIN (
    SELECT customer_id, AVG(amount) as avg_amount
    FROM orders
    GROUP BY customer_id
) avg_order ON c.id = avg_order.customer_id
WHERE latest.amount > avg_order.avg_amount
ORDER BY c.name;
""",
    expected_output=[
        ("LocalShop", "smb", 100.00, 51.666666666666664),
        ("TechStart", "enterprise", 500.00, 266.6666666666667),
    ],
    expected_output_hint="Should return 2 customers (LocalShop and TechStart) whose most recent order exceeds their historical average",
    hints=[
        "The latest order subquery finds the global max date, not per-customer max date",
        "The avg_order subquery has a join condition bug - check the column name",
        "For per-customer latest, you need to group by customer_id when finding max date",
    ],
    max_steps=15,
    error_types=["incorrect_subquery_logic", "wrong_join_column", "missing_correlation"],
)


# =============================================================================
# Task Registry
# =============================================================================

TASKS: dict[str, TaskDefinition] = {
    "easy_syntax_fix": EASY_TASK,
    "medium_join_logic": MEDIUM_TASK,
    "hard_complex_analysis": HARD_TASK,
}


def get_task(task_id: str) -> TaskDefinition:
    """Get a task by ID."""
    if task_id not in TASKS:
        raise ValueError(f"Unknown task: {task_id}. Available: {list(TASKS.keys())}")
    return TASKS[task_id]


def list_tasks() -> list[str]:
    """List all available task IDs."""
    return list(TASKS.keys())


# =============================================================================
# Graders
# =============================================================================


class SQLGrader:
    """Grades SQL query fixes against expected results."""

    def __init__(self, task: TaskDefinition):
        self.task = task
        self.conn: Optional[sqlite3.Connection] = None

    def setup_database(self) -> sqlite3.Connection:
        """Create an in-memory database with the task schema and data."""
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        # Execute schema DDL
        for statement in self.task.schema_ddl.strip().split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)

        # Insert sample data
        for statement in self.task.sample_data_sql.strip().split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)

        conn.commit()
        self.conn = conn
        return conn

    def execute_query(self, query: str) -> tuple[bool, Optional[list[tuple]], Optional[str]]:
        """
        Execute a query and return (success, results, error_message).
        """
        if self.conn is None:
            self.setup_database()

        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            return True, results, None
        except sqlite3.Error as e:
            return False, None, str(e)

    def grade(self, submitted_query: str) -> tuple[float, str, dict[str, float]]:
        """
        Grade a submitted query fix.

        Returns:
            - score: float between 0.0 and 1.0
            - reason: explanation of the score
            - partial_scores: breakdown of scoring components
        """
        partial_scores = {}

        # Component 1: Syntactic validity (0.2)
        success, results, error = self.execute_query(submitted_query)
        if not success:
            partial_scores["syntax_valid"] = 0.0
            return 0.0, f"Query failed to execute: {error}", partial_scores

        partial_scores["syntax_valid"] = 0.2

        # Component 2: Returns correct number of rows (0.2)
        expected_rows = len(self.task.expected_output)
        actual_rows = len(results) if results else 0

        if actual_rows == expected_rows:
            partial_scores["row_count"] = 0.2
        elif actual_rows > 0:
            # Partial credit for being close
            ratio = min(actual_rows, expected_rows) / max(actual_rows, expected_rows)
            partial_scores["row_count"] = 0.2 * ratio
        else:
            partial_scores["row_count"] = 0.0

        # Component 3: Column count matches (0.1)
        if results and self.task.expected_output:
            expected_cols = len(self.task.expected_output[0])
            actual_cols = len(results[0]) if results else 0
            if actual_cols == expected_cols:
                partial_scores["column_count"] = 0.1
            else:
                partial_scores["column_count"] = 0.0
        else:
            partial_scores["column_count"] = 0.0

        # Component 4: Data correctness (0.5)
        if results:
            # Normalize results for comparison (handle float precision)
            def normalize_row(row):
                return tuple(
                    round(v, 2) if isinstance(v, float) else v
                    for v in row
                )

            normalized_results = set(normalize_row(r) for r in results)
            normalized_expected = set(normalize_row(r) for r in self.task.expected_output)

            if normalized_results == normalized_expected:
                partial_scores["data_correct"] = 0.5
            else:
                # Partial credit for overlapping results
                intersection = normalized_results & normalized_expected
                union = normalized_results | normalized_expected
                if union:
                    jaccard = len(intersection) / len(union)
                    partial_scores["data_correct"] = 0.5 * jaccard
                else:
                    partial_scores["data_correct"] = 0.0
        else:
            partial_scores["data_correct"] = 0.0

        total_score = sum(partial_scores.values())

        # Clamp to strictly between 0 and 1 (validators reject exact 0.0 and 1.0)
        total_score = max(0.001, min(0.999, total_score))

        # Generate reason
        if total_score >= 0.99:
            reason = "Query is correct - returns exact expected results"
        elif total_score >= 0.7:
            reason = "Query executes and returns similar results, but with some differences"
        elif total_score >= 0.4:
            reason = "Query executes but results differ significantly from expected"
        elif total_score >= 0.2:
            reason = "Query executes but returns incorrect or no matching data"
        else:
            reason = "Query failed to execute or has critical issues"

        return round(total_score, 4), reason, partial_scores

    def cleanup(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None


def grade_task(task_id: str, submitted_query: str) -> tuple[float, str, dict[str, float]]:
    """
    Grade a submitted query for a specific task.

    Args:
        task_id: The task identifier
        submitted_query: The SQL query submitted by the agent

    Returns:
        - score: float between 0.0 and 1.0
        - reason: explanation of the score
        - partial_scores: breakdown of scoring components
    """
    task = get_task(task_id)
    grader = SQLGrader(task)
    try:
        score, reason, partial_scores = grader.grade(submitted_query)
        return score, reason, partial_scores
    finally:
        grader.cleanup()
