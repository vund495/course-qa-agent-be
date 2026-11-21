"""Global Skill Taxonomy, Skill Groups, and Class Skills Association.

Revision ID: 0053_global_skill_taxonomy
Revises: 0052_merge_email_outbox_consent
Create Date: 2026-11-19
"""

import sqlalchemy as sa

from alembic import op

revision = "0053_global_skill_taxonomy"
down_revision = "0052_merge_email_outbox_consent"
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _seed_sql(sql: str) -> None:
    """Run the PostgreSQL-only data statements, skipping SQLite.

    The statements below rely on gen_random_uuid(), now(), ON CONFLICT,
    UPDATE ... FROM and DELETE ... USING, which SQLite does not implement.
    Production runs PostgreSQL, so the data migration still runs there
    unchanged; SQLite is only used by the migration-graph tests, which assert
    the schema, not the seeded rows.
    """
    if not _is_sqlite():
        op.execute(sql)


def upgrade() -> None:
    # 1. Create skill_group table (top-level topics: Java, Python, SQL...)
    op.create_table(
        "skill_group",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_skill_group_code"),
    )
    op.create_index("ix_skill_group_code", "skill_group", ["code"])

    # 2. Create class_skill association table (many-to-many between class and skill)
    op.create_table(
        "class_skill",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("class_id", sa.Uuid(), sa.ForeignKey("class.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skill.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("class_id", "skill_id", name="uq_class_skill"),
    )
    op.create_index("ix_class_skill_class_id", "class_skill", ["class_id"])
    op.create_index("ix_class_skill_skill_id", "class_skill", ["skill_id"])

    # 3. Add group_id and metadata columns to skill table and make class_id nullable
    with op.batch_alter_table("skill") as batch:
        batch.add_column(sa.Column("group_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("display_id", sa.String(50), nullable=True))
        batch.add_column(sa.Column("domain", sa.String(100), nullable=True))
        batch.add_column(sa.Column("sub_domain", sa.String(100), nullable=True))
        batch.add_column(sa.Column("skill_family", sa.String(100), nullable=True))
        batch.add_column(sa.Column("classification", sa.String(50), nullable=True))
        batch.alter_column("class_id", existing_type=sa.Uuid(), nullable=True)

    if not _is_sqlite():
        op.create_foreign_key(
            "fk_skill_group_id",
            "skill",
            "skill_group",
            ["group_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.create_index("ix_skill_group_id", "skill", ["group_id"])
    op.create_index("ix_skill_display_id", "skill", ["display_id"])

    # 4. Migrate existing class skills into class_skill table
    _seed_sql("""
        INSERT INTO class_skill (id, class_id, skill_id, created_at)
        SELECT gen_random_uuid(), s.class_id, s.id, now()
        FROM skill s
        WHERE s.class_id IS NOT NULL
        ON CONFLICT (class_id, skill_id) DO NOTHING;
    """)

    # 5. Drop old class-scoped unique constraint if exists, deduplicate codes, and add global unique constraint on code
    try:
        op.drop_constraint("uq_skill_class_code", "skill", type_="unique")
    except Exception:  # noqa: BLE001, S110
        pass

    # Deduplicate codes if any class created duplicate codes
    _seed_sql("""
        WITH ranked_skills AS (
            SELECT id, code,
                   ROW_NUMBER() OVER (PARTITION BY code ORDER BY created_at ASC, id ASC) as rn,
                   FIRST_VALUE(id) OVER (PARTITION BY code ORDER BY created_at ASC, id ASC) as canonical_id
            FROM skill
        )
        UPDATE quiz_question qq
        SET skill_id = rs.canonical_id
        FROM ranked_skills rs
        WHERE qq.skill_id = rs.id AND rs.rn > 1;
    """)
    _seed_sql("""
        WITH ranked_skills AS (
            SELECT id, code,
                   ROW_NUMBER() OVER (PARTITION BY code ORDER BY created_at ASC, id ASC) as rn
            FROM skill
        )
        DELETE FROM skill_level_rubric slr
        USING ranked_skills rs
        WHERE slr.skill_id = rs.id AND rs.rn > 1;
    """)
    _seed_sql("""
        WITH ranked_skills AS (
            SELECT id, code,
                   ROW_NUMBER() OVER (PARTITION BY code ORDER BY created_at ASC, id ASC) as rn
            FROM skill
        )
        DELETE FROM skill s
        USING ranked_skills rs
        WHERE s.id = rs.id AND rs.rn > 1;
    """)

    try:
        op.create_unique_constraint("uq_skill_code", "skill", ["code"])
    except Exception:  # noqa: BLE001, S110
        pass

    # 6. Seed initial Skill Groups (English content matching system)
    _seed_sql("""
        INSERT INTO skill_group (id, code, name, description, created_at, updated_at)
        VALUES
            ('a0000000-0000-0000-0000-000000000001', 'JAVA', 'Java Ecosystem', 'Core Java programming, Object-Oriented principles, and enterprise frameworks.', now(), now()),
            ('a0000000-0000-0000-0000-000000000002', 'PYTHON', 'Python Ecosystem', 'Python development, algorithms, scripting, and backend workflows.', now(), now()),
            ('a0000000-0000-0000-0000-000000000003', 'SQL', 'Database & SQL Engineering', 'Relational database architecture, queries, transactions, and indexing.', now(), now())
        ON CONFLICT (code) DO NOTHING;
    """)

    # 7. Seed initial Sub-skills (with sequential ID 1..6)
    _seed_sql("""
        INSERT INTO skill (id, display_id, group_id, code, name, domain, sub_domain, skill_family, classification, category, description, created_at, updated_at)
        VALUES
            ('b0000000-0000-0000-0000-000000000001', '1', 'a0000000-0000-0000-0000-000000000001', 'JAVA_OOP', 'Object-Oriented Programming in Java', 'Information Technology', 'Software Engineering', 'Programming Languages', 'Technical Skill', 'JAVA', 'Encapsulation, inheritance, polymorphism, abstract classes, and interfaces.', now(), now()),
            ('b0000000-0000-0000-0000-000000000002', '2', 'a0000000-0000-0000-0000-000000000001', 'JAVA_COLLECTIONS', 'Java Collections Framework', 'Information Technology', 'Software Engineering', 'Programming Languages', 'Technical Skill', 'JAVA', 'Working with List, Set, Map, Queue, generics, and iterable structures.', now(), now()),
            ('b0000000-0000-0000-0000-000000000003', '3', 'a0000000-0000-0000-0000-000000000002', 'PY_DATA_TYPES', 'Python Data Structures', 'Information Technology', 'Software Engineering', 'Programming Languages', 'Technical Skill', 'PYTHON', 'Primitive data types, lists, dictionaries, tuples, and memory references.', now(), now()),
            ('b0000000-0000-0000-0000-000000000004', '4', 'a0000000-0000-0000-0000-000000000002', 'PY_OOP', 'Object-Oriented Python', 'Information Technology', 'Software Engineering', 'Programming Languages', 'Technical Skill', 'PYTHON', 'Classes, instances, inheritance, dunder methods, and OOP architecture.', now(), now()),
            ('b0000000-0000-0000-0000-000000000005', '5', 'a0000000-0000-0000-0000-000000000003', 'SQL_QUERY_JOIN', 'SQL Querying & Joins', 'Information Technology', 'Database Systems', 'Database Engineering', 'Technical Skill', 'SQL', 'Complex queries, filtering, aggregations, INNER, LEFT, and RIGHT joins.', now(), now()),
            ('b0000000-0000-0000-0000-000000000006', '6', 'a0000000-0000-0000-0000-000000000003', 'SQL_INDEX_OPT', 'Indexing & Query Optimization', 'Information Technology', 'Database Systems', 'Database Engineering', 'Technical Skill', 'SQL', 'B-Tree indexes, composite keys, query plan analysis, and execution tuning.', now(), now())
        ON CONFLICT (code) DO NOTHING;
    """)

    # 8. Seed 5 Dreyfus Rubrics for each seeded skill
    rubrics_data = [
        # JAVA_OOP
        ('b0000000-0000-0000-0000-000000000001', 'NOVICE', 'Identifies basic class syntax, field declarations, and simple methods in Java.', 80),
        ('b0000000-0000-0000-0000-000000000001', 'BEGINNER', 'Creates classes, initializes objects with constructors, and applies encapsulation.', 75),
        ('b0000000-0000-0000-0000-000000000001', 'COMPETENT', 'Applies inheritance (extends) and polymorphism (method overriding and overloading).', 70),
        ('b0000000-0000-0000-0000-000000000001', 'PROFICIENT', 'Utilizes interfaces and abstract classes to design modular, loosely-coupled systems.', 65),
        ('b0000000-0000-0000-0000-000000000001', 'MASTER', 'Architects enterprise systems leveraging SOLID design principles and patterns.', 60),

        # JAVA_COLLECTIONS
        ('b0000000-0000-0000-0000-000000000002', 'NOVICE', 'Declares and iterates through basic ArrayList elements in Java.', 80),
        ('b0000000-0000-0000-0000-000000000002', 'BEGINNER', 'Distinguishes between List, Set, and Map structures and their basic operations.', 75),
        ('b0000000-0000-0000-0000-000000000002', 'COMPETENT', 'Implements HashMap and HashSet with appropriate equals() and hashCode() contracts.', 70),
        ('b0000000-0000-0000-0000-000000000002', 'PROFICIENT', 'Applies Generics, wildcards, and Java Streams API to manipulate collections.', 65),
        ('b0000000-0000-0000-0000-000000000002', 'MASTER', 'Selects optimal data structures for time/space complexity and handles concurrency.', 60),

        # PY_DATA_TYPES
        ('b0000000-0000-0000-0000-000000000003', 'NOVICE', 'Recognizes primitive types (int, float, str, bool) in Python programs.', 80),
        ('b0000000-0000-0000-0000-000000000003', 'BEGINNER', 'Manipulates lists, tuples, and dicts, understanding mutable vs immutable semantics.', 75),
        ('b0000000-0000-0000-0000-000000000003', 'COMPETENT', 'Demonstrates understanding of references, shallow vs deep copying, and slicing.', 70),
        ('b0000000-0000-0000-0000-000000000003', 'PROFICIENT', 'Uses list/dict comprehensions, generators, and memory-efficient iterators.', 65),
        ('b0000000-0000-0000-0000-000000000003', 'MASTER', 'Analyzes CPython memory allocation, reference counting, and garbage collection.', 60),

        # PY_OOP
        ('b0000000-0000-0000-0000-000000000004', 'NOVICE', 'Defines a basic class with __init__ and instance attributes.', 80),
        ('b0000000-0000-0000-0000-000000000004', 'BEGINNER', 'Uses instance methods, class methods, and static methods appropriately.', 75),
        ('b0000000-0000-0000-0000-000000000004', 'COMPETENT', 'Applies single inheritance, super(), and clean object composition.', 70),
        ('b0000000-0000-0000-0000-000000000004', 'PROFICIENT', 'Implements custom dunder methods (__str__, __repr__, __eq__) and properties.', 65),
        ('b0000000-0000-0000-0000-000000000004', 'MASTER', 'Architects systems using multiple inheritance, MRO resolution, and metaclasses.', 60),

        # SQL_QUERY_JOIN
        ('b0000000-0000-0000-0000-000000000005', 'NOVICE', 'Writes basic SELECT, WHERE, and ORDER BY queries on single tables.', 80),
        ('b0000000-0000-0000-0000-000000000005', 'BEGINNER', 'Uses aggregate functions (COUNT, SUM, AVG) with GROUP BY and HAVING clauses.', 75),
        ('b0000000-0000-0000-0000-000000000005', 'COMPETENT', 'Combines multi-table relational data using accurate INNER and LEFT JOINs.', 70),
        ('b0000000-0000-0000-0000-000000000005', 'PROFICIENT', 'Constructs subqueries, Common Table Expressions (WITH CTE), and outer joins.', 65),
        ('b0000000-0000-0000-0000-000000000005', 'MASTER', 'Applies window functions (ROW_NUMBER, RANK, OVER) for advanced data queries.', 60),

        # SQL_INDEX_OPT
        ('b0000000-0000-0000-0000-000000000006', 'NOVICE', 'Understands the concept of indexes and their role in lookup performance.', 80),
        ('b0000000-0000-0000-0000-000000000006', 'BEGINNER', 'Creates single-column indexes and distinguishes clustered vs non-clustered.', 75),
        ('b0000000-0000-0000-0000-000000000006', 'COMPETENT', 'Designs composite indexes adhering to the leftmost prefix rule.', 70),
        ('b0000000-0000-0000-0000-000000000006', 'PROFICIENT', 'Analyzes query execution plans (EXPLAIN) and resolves sequential scan bottlenecks.', 65),
        ('b0000000-0000-0000-0000-000000000006', 'MASTER', 'Architects index partitioning strategies, covering indexes, and tuning.', 60),
    ]

    for s_id, lvl, desc, th in rubrics_data:
        _seed_sql(f"""
            INSERT INTO skill_level_rubric (id, skill_id, level, description, threshold_pct, created_at, updated_at)
            VALUES (gen_random_uuid(), '{s_id}', '{lvl}', '{desc}', {th}, now(), now())
            ON CONFLICT (skill_id, level) DO NOTHING;
        """)


def downgrade() -> None:
    op.drop_index("ix_skill_group_id", table_name="skill")
    op.drop_index("ix_skill_display_id", table_name="skill")
    op.drop_table("class_skill")
    with op.batch_alter_table("skill") as batch:
        if not _is_sqlite():
            batch.drop_constraint("fk_skill_group_id", type_="foreignkey")
        batch.drop_column("group_id")
        batch.drop_column("display_id")
        batch.drop_column("domain")
        batch.drop_column("sub_domain")
        batch.drop_column("skill_family")
        batch.drop_column("classification")
    op.drop_table("skill_group")
