"""Comprehensive Skill Bank Data Catalog.

Contains 7 top-level domains, 56 differentiated technical skills and tools,
and complete, well-balanced Dreyfus (0..4) evaluation rubrics with Bloom cognitive keywords.
"""

import uuid

# Fixed deterministic UUIDs for Groups
GROUP_PYTHON_ID = uuid.UUID("a0000000-0000-0000-0000-000000000002")
GROUP_JAVA_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
GROUP_DATABASE_ID = uuid.UUID("a0000000-0000-0000-0000-000000000008")
GROUP_SYSTEMS_ID = uuid.UUID("a0000000-0000-0000-0000-000000000004")
GROUP_DEVOPS_ID = uuid.UUID("a0000000-0000-0000-0000-000000000005")
GROUP_FRONTEND_ID = uuid.UUID("a0000000-0000-0000-0000-000000000006")
GROUP_AIML_ID = uuid.UUID("a0000000-0000-0000-0000-000000000007")

SKILL_GROUPS = [
    {
        "id": GROUP_PYTHON_ID,
        "code": "PYTHON",
        "name": "Python Ecosystem & Data Engineering",
        "description": "Comprehensive competencies in Python programming, scientific computing, workflow orchestration, and AI model integration.",
    },
    {
        "id": GROUP_JAVA_ID,
        "code": "JAVA",
        "name": "Java Enterprise & Distributed Systems",
        "description": "Enterprise software engineering with Java, Spring Boot microservices, high-performance collections, and JVM concurrency.",
    },
    {
        "id": GROUP_DATABASE_ID,
        "code": "DATABASE",
        "name": "Database Architecture & SQL Engineering",
        "description": "Relational schema design, complex SQL querying, B-Tree index optimization, transaction isolation, and database migration tooling.",
    },
    {
        "id": GROUP_SYSTEMS_ID,
        "code": "SYSTEMS",
        "name": "C/C++ & Low-Level Systems Programming",
        "description": "Native systems architecture, deterministic memory management, smart pointers, RAII, and standard container performance.",
    },
    {
        "id": GROUP_DEVOPS_ID,
        "code": "DEVOPS",
        "name": "Cloud Infrastructure & DevOps Tooling",
        "description": "Container virtualization, version control workflows, automated CI/CD deployment pipelines, and scalable service orchestration.",
    },
    {
        "id": GROUP_FRONTEND_ID,
        "code": "WEB_FRONTEND",
        "name": "Modern Web & Frontend Engineering",
        "description": "Component-driven user interfaces, state management architectures, type-safe full-stack web frameworks, and automated client testing.",
    },
    {
        "id": GROUP_AIML_ID,
        "code": "AI_ML",
        "name": "Artificial Intelligence & Machine Learning",
        "description": "Deep learning tensor graphs, transformer architectures, computer vision pipelines, retrieval-augmented generation (RAG), and MLOps lifecycle.",
    },
]

def skill_uuid(code: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"skills.faca.edu.vn/{code}")

SKILLS_BANK = [
    {
        "id": uuid.UUID("fc1a3f5d-7f15-488b-9c2b-3a6cda631232"),
        "code": "PY_PANDAS",
        "name": "Pandas (Python Package)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        "domain": "Information Technology",
        "sub_domain": "Media and Communications",
        "skill_family": "Data Science",
        "classification": "Technical Skill",
        "description": (
            "Pandas provides high-performance, flexible data structures and data analysis tools for the Python programming language. This competency specifies operational proficiency in managing Series and DataFrame structures, memory alignment, missing data imputation, and vectorized data transformations. Practitioners utilize indexing, slicing, multi-key grouping via groupby(), hierarchical indexing, and merging operations to clean and aggregate raw structured datasets into analytical pipelines."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Pandas (Python Package), including Series, DataFrames, indexing, and basic vectorization. Able to perform routine tasks such as reading CSV files via pd.read_csv(), selecting columns, filtering rows, and computing basic summary statistics under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Pandas (Python Package) in everyday development. Independently handles cleaning datasets, handling missing values with fillna(), grouping data with groupby().agg(), and merging tables, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Pandas (Python Package). Independently implements complex solutions such as vectorized calculations avoiding slow loops, optimizing memory with categorical dtypes, and time-series resampling, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Pandas (Python Package). Capable of solving intricate architectural challenges (designing high-throughput analytical ETL pipelines, writing custom extensions, and establishing data manipulation standards), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("716639d7-2fed-4757-910e-cab790df9949"),
        "code": "PY_LUIGI",
        "name": "Luigi (Python Package)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Luigi is a Python package engineered to build complex pipelines of batch jobs. It handles dependency resolution, workflow management, visualization, handling failures, command line integration, and much more. This competency evaluates the ability to construct directed acyclic graphs (DAGs) of batch tasks, manage input/output targets on local and distributed filesystems, and monitor automated task execution via the central scheduler."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Luigi (Python Package), including Target outputs, Task DAG dependencies, and the central scheduler daemon. Able to perform routine tasks such as defining simple Task classes with requires() and run() methods, configuring local file targets, and running CLI pipelines under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Luigi (Python Package) in everyday development. Independently handles authoring multi-stage data pipelines, managing parameters between tasks, resolving failures, and monitoring on the visual dashboard, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Luigi (Python Package). Independently implements complex solutions such as implementing custom Target classes for cloud storage (S3/GCS), configuring distributed workers, and tuning task retries, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Luigi (Python Package). Capable of solving intricate architectural challenges (architecting enterprise batch orchestration backbones, authoring custom scheduler extensions, and ensuring automated self-healing), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("91bcfeaf-2858-4871-b84d-0ce0e4df6007"),
        "code": "PY_DATA_ANALYSIS",
        "name": "Python For Data Analysis",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        "domain": "Information Technology",
        "sub_domain": "Media and Communications",
        "skill_family": "Data Analysis",
        "classification": "Technical Skill",
        "description": (
            "Python for Data Analysis represents the holistic application of algorithmic computing, statistical computation, and exploratory analysis. This competency covers NumPy n-dimensional arrays, vectorized broadcasting, exploratory data analysis (EDA), data wrangling, statistical summaries, and visual storytelling with Matplotlib and Seaborn to extract actionable insights from raw data."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Python For Data Analysis, including NumPy arrays, vectorized broadcasting, exploratory data analysis (EDA), and visualization libraries. Able to perform routine tasks such as loading datasets, computing central tendencies (mean, median, standard deviation), and plotting basic charts under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Python For Data Analysis in everyday development. Independently handles conducting comprehensive EDA, cleaning outliers, analyzing correlation matrices, and creating diagnostic visual plots, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Python For Data Analysis. Independently implements complex solutions such as performing statistical modeling, feature engineering, and optimizing high-dimensional matrix computations with NumPy, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Python For Data Analysis. Capable of solving intricate architectural challenges (formulating institutional analytics methodologies, architecting discovery platforms, and leading organizational data strategy), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("c2f25a07-0cfd-43cf-9b5b-ae95be3821d2"),
        "code": "PY_IPYTHON",
        "name": "IPython (Python Package)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Scripting",
        "classification": "Tool",
        "description": (
            "IPython provides a rich toolkit to help maximize developer productivity in interactive Python computing. This competency includes mastery of interactive shells, Jupyter notebook kernels, magic commands (%timeit, %debug, %run), dynamic object introspection, shell integration, and interactive debugging utilities."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of IPython (Python Package), including interactive shells, Jupyter kernels, line/cell magic commands, and dynamic introspection. Able to perform routine tasks such as executing code cells, using tab-completion, inspecting docstrings with ?, and running basic magic commands like %time under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing IPython (Python Package) in everyday development. Independently handles leveraging interactive debugging with %debug, profiling execution speed via %timeit, and managing custom profiles, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in IPython (Python Package). Independently implements complex solutions such as authoring custom magic commands, profiling heap memory with %memit, and configuring multi-kernel environments, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in IPython (Python Package). Capable of solving intricate architectural challenges (architecting multi-tenant JupyterHub cloud environments, authoring custom execution kernels, and building analytical tooling), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("ccd2076d-5c8d-4d99-be1c-1cfdb657adde"),
        "code": "PY_LANGCHAIN",
        "name": "LangChain with Python",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        "domain": "Information Technology",
        "sub_domain": "Artificial Intelligence",
        "skill_family": "Artificial Intelligence and Machine Learning (AI/ML)",
        "classification": "Functional Skill",
        "description": (
            "LangChain is a framework for developing applications powered by large language models (LLMs). This competency covers prompt engineering templates, chainable sequential pipelines (LCEL), conversational memory persistence, retrieval-augmented generation (RAG) integrated with vector stores, and multi-tool autonomous agent orchestration in Python."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of LangChain with Python, including prompt templates, LangChain Expression Language (LCEL), conversational memory, and vector store retrievers. Able to perform routine tasks such as initializing model wrappers, composing basic PromptTemplates, and executing simple chain invocations under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing LangChain with Python in everyday development. Independently handles building end-to-end RAG pipelines, connecting vector stores with document loaders, and persisting chat history, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in LangChain with Python. Independently implements complex solutions such as authoring custom LCEL Runnable pipelines, implementing ReAct agents with dynamic tools, and optimizing token latency, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in LangChain with Python. Capable of solving intricate architectural challenges (architecting enterprise multi-agent cognitive systems, designing self-reflective retrieval, and enforcing production LLM guardrails), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("0ba92858-5b5e-507e-979a-9225417463a2"),
        "code": "PY_FASTAPI",
        "name": "FastAPI (Python Framework)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Web Frameworks",
        "classification": "Technical Skill",
        "description": (
            "FastAPI is a modern, fast (high-performance) web framework for building APIs with Python based on standard type hints and Starlette. This competency evaluates asynchronous request handling (async/await), Pydantic request/response validation schemas, dependency injection systems (Depends), OAuth2 security flows, background tasks, and automated OpenAPI documentation generation."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of FastAPI (Python Framework), including asynchronous event handling (async/await), Pydantic schemas, dependency injection (Depends), and OpenAPI routing. Able to perform routine tasks such as declaring basic GET/POST endpoints, binding path and query parameters, and returning dictionary JSON responses under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing FastAPI (Python Framework) in everyday development. Independently handles authoring layered APIs with Pydantic validation, creating reusable dependencies for auth and database sessions, and handling HTTP errors, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in FastAPI (Python Framework). Independently implements complex solutions such as architecting asynchronous database transactions with AsyncSession, implementing JWT bearer authentication, and managing WebSockets, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in FastAPI (Python Framework). Capable of solving intricate architectural challenges (architecting high-throughput microservice ecosystems, eliminating async blocking bottlenecks, and setting enterprise API standards), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("42439b90-c54f-5fe3-ae43-a979375cb9b5"),
        "code": "PY_PYTEST",
        "name": "Pytest (Python Testing Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Pytest is a mature, feature-rich testing framework that makes it easy to write small, readable tests in Python. This competency covers test fixtures with dependency injection, parameterized testing (@pytest.mark.parametrize), mocking external dependencies using unittest.mock / pytest-mock, async test runners, and test coverage reporting."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Pytest (Python Testing Tool), including test fixtures, dependency injection, parameterized testing matrices, and assertion introspection. Able to perform routine tasks such as writing simple assert statements, following pytest file discovery conventions, and running tests from the CLI under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Pytest (Python Testing Tool) in everyday development. Independently handles creating modular fixtures with scope controls, parameterizing test cases with @pytest.mark.parametrize, and testing exceptions, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Pytest (Python Testing Tool). Independently implements complex solutions such as mocking complex external database and network boundaries, testing async endpoints, and enforcing CI coverage thresholds, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Pytest (Python Testing Tool). Capable of solving intricate architectural challenges (developing custom pytest plugins and reporting hooks, designing contract testing harnesses, and driving team TDD standards), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000001"),
        "code": "JAVA_OOP",
        "name": "Object-Oriented Programming (Java)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Programming Languages",
        "classification": "Technical Skill",
        "description": (
            "Object-Oriented Programming in Java represents the foundational architecture for scalable enterprise software. This competency encompasses encapsulation, inheritance hierarchies, runtime polymorphism through method overriding and dynamic dispatch, and abstraction using interfaces and abstract classes. It emphasizes clean class design, immutable value objects, and SOLID principles."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Object-Oriented Programming (Java), including encapsulation, inheritance hierarchies, runtime polymorphism, abstract classes, interfaces, and SOLID principles. Able to perform routine tasks such as declaring classes and attributes, writing constructors, defining getters/setters, and applying access modifiers under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Object-Oriented Programming (Java) in everyday development. Independently handles designing clean inheritance hierarchies with extends and implements, applying method overriding, and avoiding tight coupling, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Object-Oriented Programming (Java). Independently implements complex solutions such as applying classical GoF design patterns (Factory, Strategy, Observer), using abstract classes, and adhering to SOLID rules, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Object-Oriented Programming (Java). Capable of solving intricate architectural challenges (architecting large-scale domain-driven design (DDD) enterprise models, authoring extensible frameworks, and eliminating architectural debt), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000013"),
        "code": "JAVA_SPRING_BOOT",
        "name": "Spring Boot (Java Framework)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Enterprise Frameworks",
        "classification": "Technical Skill",
        "description": (
            "Spring Boot makes it easy to create stand-alone, production-grade Spring-based applications. This competency covers auto-configuration, starter dependencies, Inversion of Control (IoC), Dependency Injection (DI), REST controller architecture, Spring Data JPA repository management, application properties profiles, and production monitoring via Actuator."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Spring Boot (Java Framework), including Inversion of Control (IoC), Dependency Injection, starter dependencies, and Spring Data JPA repositories. Able to perform routine tasks such as bootstrapping applications using Spring Initializr, creating simple @RestController endpoints, and configuring application.properties under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Spring Boot (Java Framework) in everyday development. Independently handles implementing layered @Service and @Repository architectures, validating DTOs with Bean Validation, and managing @Transactional methods, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Spring Boot (Java Framework). Independently implements complex solutions such as authoring custom auto-configurations, securing endpoints with Spring Security and JWT, and building custom Actuator health indicators, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Spring Boot (Java Framework). Capable of solving intricate architectural challenges (architecting enterprise cloud-native microservices with Spring Cloud, optimizing JVM memory usage, and setting corporate architecture blueprints), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000007"),
        "code": "JAVA_MAVEN",
        "name": "Apache Maven (Java Build Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Apache Maven is a software project management and comprehension tool. Based on the concept of a Project Object Model (POM), Maven manages project builds, reporting, dependency resolution, plugin executions, and release documentation from a central configuration."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Apache Maven (Java Build Tool), including Project Object Model (POM), standard build lifecycles (clean, compile, test, package), and dependency coordinates. Able to perform routine tasks such as declaring external dependencies in pom.xml, running standard build goals from the terminal, and resolving simple versions under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Apache Maven (Java Build Tool) in everyday development. Independently handles managing dependency scopes (compile, test, provided), resolving transitive dependency conflicts with exclusions, and configuring plugins, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Apache Maven (Java Build Tool). Independently implements complex solutions such as architecting multi-module Maven parent/child projects, managing centralized dependencyManagement, and deploying to private artifact repositories, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Apache Maven (Java Build Tool). Capable of solving intricate architectural challenges (developing custom Maven build plugins, optimizing build caching and parallel compilation in CI/CD, and establishing corporate build standards), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("066e2d5f-f020-4c32-bbc1-44e0bfd70304"),
        "code": "JAVA_CONCURRENCY",
        "name": "JVM Concurrency & Multithreading (Java)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "domain": "Information Technology",
        "sub_domain": "Systems Engineering",
        "skill_family": "Enterprise Architecture",
        "classification": "Technical Skill",
        "description": (
            "JVM Concurrency & Multithreading addresses parallel execution, memory consistency, and thread synchronization in Java. This competency covers the Java Memory Model (JMM), happens-before guarantees, synchronized locks, java.util.concurrent abstractions (ExecutorService, CompletableFuture, ReentrantLock, ConcurrentHashMap), atomic primitives, and virtual threads (Project Loom)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of JVM Concurrency & Multithreading (Java), including the Java Memory Model (JMM), thread lifecycles, synchronized blocks, and java.util.concurrent abstractions. Able to perform routine tasks such as instantiating threads with Runnable and Thread, starting threads, and understanding the basic need for synchronization under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing JVM Concurrency & Multithreading (Java) in everyday development. Independently handles utilizing ExecutorService thread pools, applying atomic variables (AtomicInteger), and using ConcurrentHashMap safely, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in JVM Concurrency & Multithreading (Java). Independently implements complex solutions such as authoring asynchronous non-blocking pipelines with CompletableFuture, utilizing ReentrantReadWriteLock, and tuning thread pool queues, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in JVM Concurrency & Multithreading (Java). Capable of solving intricate architectural challenges (authoring lock-free concurrent data structures using CAS operations, optimizing high-concurrency systems with virtual threads (Project Loom), and diagnosing thread deadlocks), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("bfe28d65-0ca1-51bd-abc7-ea5c73ecccaa"),
        "code": "JAVA_HIBERNATE",
        "name": "Hibernate & JPA (Java ORM Framework)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Data Persistence",
        "classification": "Technical Skill",
        "description": (
            "Hibernate is an Object/Relational Mapping (ORM) solution for Java environments. This competency covers entity mapping annotations (@Entity, @Table, @OneToMany, @ManyToMany), entity lifecycle states (transient, persistent, detached), lazy loading vs. eager fetching, solving the N+1 select problem, first/second-level caching, and JPQL/Criteria queries."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Hibernate & JPA (Java ORM Framework), including Object-Relational Mapping (ORM), entity lifecycle states, lazy vs eager fetching, and JPQL queries. Able to perform routine tasks such as annotating POJOs with @Entity and @Id, mapping basic column attributes, and executing basic CRUD via JpaRepository under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Hibernate & JPA (Java ORM Framework) in everyday development. Independently handles mapping relational associations (@OneToMany, @ManyToOne) with cascading, handling orphan removal, and writing JPQL queries, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Hibernate & JPA (Java ORM Framework). Independently implements complex solutions such as diagnosing and resolving N+1 query bottlenecks using EntityGraphs and join fetch, managing optimistic locking (@Version), and configuring second-level cache, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Hibernate & JPA (Java ORM Framework). Capable of solving intricate architectural challenges (architecting enterprise multi-tenant database partitioning with Hibernate, tuning JDBC batch insertions, and optimizing persistence performance), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("2906bf7e-8631-5843-9558-a0e40fc0670a"),
        "code": "JAVA_KAFKA",
        "name": "Apache Kafka with Java (Enterprise Messaging)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Distributed Systems",
        "classification": "Functional Skill",
        "description": (
            "Apache Kafka is a distributed event store and stream-processing platform. This competency evaluates building event-driven Java applications using Spring Kafka and Kafka Clients, managing producer idempotency, consumer group partitions, offset commit strategies, dead-letter topics, and event schema evolution with Avro."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Apache Kafka with Java (Enterprise Messaging), including event-driven architecture, distributed log partitions, consumer groups, offset commits, and idempotent producers. Able to perform routine tasks such as configuring basic Kafka producer/consumer properties in Spring Boot and sending/receiving simple string messages under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Apache Kafka with Java (Enterprise Messaging) in everyday development. Independently handles managing partition keys for message ordering, configuring consumer concurrency, serializing JSON DTOs, and handling rebalances, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Apache Kafka with Java (Enterprise Messaging). Independently implements complex solutions such as implementing reliable error handling with Dead Letter Queues (DLQ), configuring exactly-once processing (EOS), and managing schema evolution, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Apache Kafka with Java (Enterprise Messaging). Capable of solving intricate architectural challenges (architecting enterprise event streaming backbones, designing event-sourcing and CQRS topologies, and tuning broker throughput), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000014"),
        "code": "SQL_POSTGRES_QUERY",
        "name": "PostgreSQL Querying & Joins (SQL)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000008"),
        "domain": "Information Technology",
        "sub_domain": "Database Systems",
        "skill_family": "Database Management",
        "classification": "Technical Skill",
        "description": (
            "PostgreSQL Querying & Joins addresses relational data querying using ANSI SQL within the PostgreSQL engine. This competency encompasses multi-table relational joins (INNER, LEFT, RIGHT, FULL OUTER), filtering predicates, aggregate grouping, subqueries, Common Table Expressions (WITH CTE), window functions, and JSONB document querying."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of PostgreSQL Querying & Joins (SQL), including ANSI SQL syntax, relational joins (INNER, LEFT, RIGHT), aggregate grouping, and subqueries. Able to perform routine tasks such as writing SELECT statements with WHERE filtering, sorting with ORDER BY, limiting results, and calculating aggregates with COUNT and SUM under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing PostgreSQL Querying & Joins (SQL) in everyday development. Independently handles writing multi-table INNER and LEFT JOINs, utilizing GROUP BY with HAVING conditions, formulating subqueries, and querying JSONB fields, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in PostgreSQL Querying & Joins (SQL). Independently implements complex solutions such as authoring analytical queries utilizing window functions (ROW_NUMBER, RANK, LAG, LEAD), recursive CTEs, and optimizing join evaluation order, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in PostgreSQL Querying & Joins (SQL). Capable of solving intricate architectural challenges (formulating high-concurrency analytical queries across tens of millions of records, authoring complex PL/pgSQL stored procedures, and eliminating lock contention), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000015"),
        "code": "SQL_INDEX_PERF",
        "name": "Indexing & Query Optimization (Database)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000008"),
        "domain": "Information Technology",
        "sub_domain": "Database Systems",
        "skill_family": "Database Administration",
        "classification": "Technical Skill",
        "description": (
            "Indexing & Query Optimization centers on database internals, storage engine access methods, and execution plan analysis. This competency covers B-Tree, Hash, GIN, and GiST indexes, composite index design adhering to the leftmost prefix rule, reading EXPLAIN ANALYZE execution trees, mitigating sequential scan overhead, and managing table bloat through autovacuum tuning."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Indexing & Query Optimization (Database), including B-Tree, Hash, and GIN indexes, composite index column ordering, and EXPLAIN ANALYZE execution cost trees. Able to perform routine tasks such as creating single-column indexes using CREATE INDEX, identifying index presence, and recognizing the lookup purpose of indexing under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Indexing & Query Optimization (Database) in everyday development. Independently handles designing composite indexes adhering to the leftmost prefix rule, reading EXPLAIN query plans to verify index usage, and resolving slow queries, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Indexing & Query Optimization (Database). Independently implements complex solutions such as analyzing EXPLAIN (ANALYZE, BUFFERS) statistics, designing partial and covering indexes (INCLUDE), and diagnosing index fragmentation, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Indexing & Query Optimization (Database). Capable of solving intricate architectural challenges (architecting table partitioning schemes, tuning shared_buffers and work_mem engine parameters, and eliminating I/O bottlenecks in large databases), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000008"),
        "code": "DB_FLYWAY",
        "name": "Flyway (Database Migration Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000008"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Flyway is an open-source database migration tool strongly favored for its simplicity and conventions. This competency evaluates version-controlled schema evolution, managing repeatable and versioned SQL migration scripts, maintaining schema history tables, and automating database migrations across CI/CD deployment pipelines."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Flyway (Database Migration Tool), including schema versioning, versioned migration scripts (V__), repeatable migrations (R__), and schema history tables. Able to perform routine tasks such as authoring incremental SQL migration files following the V1__init.sql naming convention and running flyway migrate under guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Flyway (Database Migration Tool) in everyday development. Independently handles integrating Flyway into application startup pipelines, handling baseline migrations, and resolving checksum mismatches with flyway repair, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Flyway (Database Migration Tool). Independently implements complex solutions such as architecting backward-compatible zero-downtime database migrations, managing repeatable change scripts, and configuring out-of-order execution, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Flyway (Database Migration Tool). Capable of solving intricate architectural challenges (designing automated multi-tenant database migration pipelines in CI/CD, establishing database governance, and ensuring safe zero-downtime rollouts), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000009"),
        "code": "DB_DATA_MODELING",
        "name": "Relational Data Modeling (Database)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000008"),
        "domain": "Information Technology",
        "sub_domain": "Database Systems",
        "skill_family": "Data Modeling",
        "classification": "Functional Skill",
        "description": (
            "Relational Data Modeling addresses the conceptual, logical, and physical design of database schemas to support business applications. This competency evaluates Entity-Relationship Diagrams (ERDs), normal forms (1NF, 2NF, 3NF, BCNF), referential integrity constraints, cardinality rules, and strategic denormalization for analytical workloads."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Relational Data Modeling (Database), including Entity-Relationship Diagrams (ERD), normal forms (1NF, 2NF, 3NF), and referential integrity constraints. Able to perform routine tasks such as identifying primary keys and foreign keys, mapping entities and attributes, and recognizing one-to-one and one-to-many relationships under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Relational Data Modeling (Database) in everyday development. Independently handles designing normalized 3NF relational schemas, defining cascading constraints (ON DELETE CASCADE), and modeling many-to-many junction tables, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Relational Data Modeling (Database). Independently implements complex solutions such as architecting complex transactional schemas, balancing normalization against analytical query speed, and implementing audit logging patterns, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Relational Data Modeling (Database). Capable of solving intricate architectural challenges (establishing organizational enterprise data models, architecting hybrid OLTP/OLAP architectures, and leading enterprise data governance), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("c0fcabb2-8caa-54b0-bd7d-655b9782b517"),
        "code": "DB_REDIS",
        "name": "Redis (In-Memory Database Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000008"),
        "domain": "Information Technology",
        "sub_domain": "Database Systems",
        "skill_family": "NoSQL & Caching",
        "classification": "Tool",
        "description": (
            "Redis is an in-memory data structure store used as a distributed cache, message broker, and database. This competency evaluates key eviction policies (LRU/LFU), complex data structures (Hashes, Sets, Sorted Sets, Bitmaps, HyperLogLogs), TTL expiration management, Redis Sentinel high-availability, Redis Cluster sharding, and distributed lock patterns."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Redis (In-Memory Database Tool), including in-memory data structures (Strings, Hashes, Sets, Sorted Sets), TTL expiration, and eviction policies (LRU/LFU). Able to perform routine tasks such as connecting via redis-cli, executing basic GET, SET, DEL, and EXPIRE commands, and inspecting keys with guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Redis (In-Memory Database Tool) in everyday development. Independently handles implementing application caching patterns (Cache-Aside, Write-Through), working with Hashes and Sorted Sets, and managing key expiration, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Redis (In-Memory Database Tool). Independently implements complex solutions such as implementing distributed locking (Redlock), pipelining batched commands, configuring Pub/Sub messaging, and managing Redis Sentinel failover, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Redis (In-Memory Database Tool). Capable of solving intricate architectural challenges (architecting multi-node Redis Cluster sharding topologies, tuning RDB/AOF persistence trade-offs, and optimizing memory allocation to eliminate fragmentation), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("ebac1214-45ac-5ff1-840e-4d8e753bba1b"),
        "code": "DB_TRANSACTIONS",
        "name": "Database Transactions & ACID Isolation (SQL)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000008"),
        "domain": "Information Technology",
        "sub_domain": "Database Systems",
        "skill_family": "Database Engineering",
        "classification": "Technical Skill",
        "description": (
            "Database Transactions & ACID Isolation explores multi-user concurrency control and data integrity guarantees. This competency covers transaction isolation levels (READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ, SERIALIZABLE), concurrency anomalies (dirty read, non-repeatable read, phantom read, serialization failure), row-level locking (SELECT FOR UPDATE), and Two-Phase Commit (2PC)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Database Transactions & ACID Isolation (SQL), including ACID properties, transaction isolation levels (Read Committed, Repeatable Read, Serializable), and row-level locking. Able to perform routine tasks such as wrapping related SQL statements within BEGIN, COMMIT, and ROLLBACK blocks to ensure atomic execution under guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Database Transactions & ACID Isolation (SQL) in everyday development. Independently handles managing transaction rollbacks upon application errors, setting transaction isolation levels, and applying row locking with SELECT FOR UPDATE, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Database Transactions & ACID Isolation (SQL). Independently implements complex solutions such as diagnosing and resolving deadlocks using pg_locks, tuning lock timeouts, and implementing optimistic concurrency control using version columns, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Database Transactions & ACID Isolation (SQL). Capable of solving intricate architectural challenges (architecting distributed transaction patterns (Saga pattern, Two-Phase Commit), designing high-concurrency systems, and guaranteeing zero-loss consistency), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("39092449-c9b7-4b6c-a6df-c7f73f965000"),
        "code": "CPP_POINTERS_MEMORY",
        "name": "Pointers & Dynamic Memory (C++)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000004"),
        "domain": "Information Technology",
        "sub_domain": "Systems Engineering",
        "skill_family": "Programming Languages",
        "classification": "Technical Skill",
        "description": (
            "Pointers & Dynamic Memory in C++ represents the critical foundation for deterministic resource management and low-level computing. This competency details pointer arithmetic, dereferencing, reference variables, stack vs. heap memory allocation, and RAII (Resource Acquisition Is Initialization). It emphasizes modern C++ smart pointers (std::unique_ptr, std::shared_ptr, std::weak_ptr) to prevent memory leaks, dangling pointers, and double-free vulnerabilities."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Pointers & Dynamic Memory (C++), including pointer arithmetic, dereferencing, stack vs heap allocation, RAII, and smart pointers (unique_ptr, shared_ptr). Able to perform routine tasks such as declaring raw pointers, using the address-of (&) and dereference (*) operators, and allocating/deallocating heap memory with new and delete under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Pointers & Dynamic Memory (C++) in everyday development. Independently handles implementing RAII in custom classes, preventing memory leaks through proper destructors, and utilizing std::unique_ptr for exclusive ownership, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Pointers & Dynamic Memory (C++). Independently implements complex solutions such as managing shared resource ownership with std::shared_ptr and std::weak_ptr avoiding cyclic references, and writing custom deleters, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Pointers & Dynamic Memory (C++). Capable of solving intricate architectural challenges (authoring custom memory allocators (pool, arena, slab), analyzing CPU cache line alignment and false sharing, and architecting ultra-low-latency native systems), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b970701f-f301-4a27-bc83-d7e6a407de7a"),
        "code": "CPP_STL",
        "name": "Standard Template Library (C++ STL)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000004"),
        "domain": "Information Technology",
        "sub_domain": "Systems Engineering",
        "skill_family": "Programming Languages",
        "classification": "Technical Skill",
        "description": (
            "The Standard Template Library (STL) provides generic, reusable, high-performance algorithms and container data structures in C++. This competency covers sequence containers (std::vector, std::deque, std::list), associative containers (std::map, std::set), hash-based unordered containers (std::unordered_map), iterators, lambda expressions, and standard algorithms (std::sort, std::find_if, std::transform)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Standard Template Library (C++ STL), including standard sequence containers (vector, list), associative containers (map, set), iterators, and standard algorithms. Able to perform routine tasks such as instantiating std::vector, pushing elements, and iterating through items using range-based for loops with guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Standard Template Library (C++ STL) in everyday development. Independently handles selecting appropriate containers based on time/space complexity, utilizing iterators, and applying standard algorithms like std::sort and std::find_if, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Standard Template Library (C++ STL). Independently implements complex solutions such as authoring custom comparators and hash functions, leveraging emplace semantics to eliminate copies, and managing iterator invalidation rules, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Standard Template Library (C++ STL). Capable of solving intricate architectural challenges (authoring STL-compliant custom generic containers and iterators, benchmarking memory locality, and optimizing inner loops with template metaprogramming), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("6be2ceba-670e-446e-895b-54af33900d50"),
        "code": "CPP_VALGRIND",
        "name": "Valgrind & GDB (C++ Debugging Tools)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000004"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Valgrind and GNU Debugger (GDB) are essential diagnostic and profiling tools for compiled C++ software. This competency evaluates memory leak detection (Memcheck), analyzing invalid heap reads/writes, setting breakpoints and watchpoints in GDB, inspecting stack backtraces, and diagnosing segmentation faults in native applications."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Valgrind & GDB (C++ Debugging Tools), including memory leak detection (Memcheck), invalid heap read/write analysis, GDB breakpoints, and segmentation fault diagnosis. Able to perform routine tasks such as running an executable under GDB, inspecting basic crash points with backtrace (bt), and invoking Valgrind Memcheck with guided commands under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Valgrind & GDB (C++ Debugging Tools) in everyday development. Independently handles setting conditional breakpoints and watchpoints in GDB, inspecting variable values across stack frames, and interpreting Valgrind logs to fix leaks, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Valgrind & GDB (C++ Debugging Tools). Independently implements complex solutions such as debugging multithreaded native applications in GDB, performing core dump post-mortem analyses, and diagnosing data races using Valgrind Helgrind, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Valgrind & GDB (C++ Debugging Tools). Capable of solving intricate architectural challenges (authoring custom GDB Python automation scripts, conducting non-intrusive binary profiling, and diagnosing complex undefined behavior challenges), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("30c3ae6c-e4f7-46b4-bea3-dd2a445a2f51"),
        "code": "CPP_CMAKE",
        "name": "CMake (C++ Build Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000004"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "CMake is an open-source, cross-platform family of tools designed to build, test, and package C++ software. This competency evaluates writing CMakeLists.txt files, defining executable and library targets, managing target_link_libraries, handling compiler flags and standards (C++17/20), and configuring external dependencies via FetchContent."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of CMake (C++ Build Tool), including meta-build systems, CMakeLists.txt syntax, targets (executables, libraries), target_link_libraries, and compiler standards. Able to perform routine tasks such as writing basic CMakeLists.txt files with cmake_minimum_required, project(), and add_executable() to compile single-file programs under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing CMake (C++ Build Tool) in everyday development. Independently handles authoring modern target-based CMake scripts, structuring projects with static and shared libraries, and enforcing compiler standards (C++17/20), resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in CMake (C++ Build Tool). Independently implements complex solutions such as integrating external third-party dependencies using find_package() and FetchContent, configuring install targets, and organizing CTest suites, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in CMake (C++ Build Tool). Capable of solving intricate architectural challenges (architecting modular enterprise CMake build toolchains, designing cross-compilation toolchain files for embedded targets, and optimizing CI/CD parallel builds), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("1732e28b-2a9f-4eeb-89e8-df424e7592bc"),
        "code": "CPP_OOP_PILLARS",
        "name": "Object-Oriented Systems Design (C++)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000004"),
        "domain": "Information Technology",
        "sub_domain": "Systems Engineering",
        "skill_family": "Software Engineering",
        "classification": "Technical Skill",
        "description": (
            "Object-Oriented Systems Design in C++ addresses native class architecture, lifetime invariants, and the Rule of Five/Zero. This competency encompasses abstract base classes, pure virtual interfaces, runtime dynamic dispatch via vtables, custom copy/move constructors, copy/move assignment operators, and composition over deep inheritance hierarchies."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Object-Oriented Systems Design (C++), including Rule of Three/Five/Zero, abstract interfaces, pure virtual functions, dynamic dispatch via vtables, and move semantics. Able to perform routine tasks such as declaring classes and structs with public and private members, writing basic constructors, and instantiating objects on stack or heap under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Object-Oriented Systems Design (C++) in everyday development. Independently handles implementing polymorphic interfaces with virtual methods and virtual destructors, and writing standard Rule of Three copy constructors, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Object-Oriented Systems Design (C++). Independently implements complex solutions such as implementing the Rule of Five with move semantics (move constructors, move assignment), applying the Non-Virtual Interface pattern, and ensuring exception safety, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Object-Oriented Systems Design (C++). Capable of solving intricate architectural challenges (architecting zero-overhead native object hierarchies, optimizing virtual method dispatch layout, and mentoring engineering teams on systems design), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("f46fe5f1-1491-5e0e-9842-fc167fef8e3c"),
        "code": "SYS_LINUX_CLI",
        "name": "Linux Shell & System Calls (Systems Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000004"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Operating Systems",
        "classification": "Tool",
        "description": (
            "Linux Shell & System Calls covers interaction with POSIX operating system kernels. This competency evaluates bash scripting, standard file descriptors (stdin, stdout, stderr), process management (fork, execve, waitpid), file permissions (chmod, chown), signal handling, and diagnosing resource usage with top, strace, and htop."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Linux Shell & System Calls (Systems Tool), including POSIX operating system architecture, standard streams (stdin, stdout, stderr), pipes, processes, signals, and permissions. Able to perform routine tasks such as navigating filesystems with basic terminal commands (cd, ls, grep, find, cat), inspecting files, and changing permissions with chmod under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Linux Shell & System Calls (Systems Tool) in everyday development. Independently handles authoring robust bash scripts with error handling, managing background jobs and daemon processes with nohup/&, and diagnosing process states with ps and top, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Linux Shell & System Calls (Systems Tool). Independently implements complex solutions such as tracing kernel system calls using strace, managing process signals in native services, authoring systemd service units, and configuring networking with iptables, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Linux Shell & System Calls (Systems Tool). Capable of solving intricate architectural challenges (tuning Linux kernel sysctl parameters for extreme network/disk throughput, managing cgroups and namespace isolation, and resolving OS-level resource contention), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000010"),
        "code": "DEVOPS_DOCKER",
        "name": "Docker (DevOps Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000005"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Docker is an open platform for developing, shipping, and running applications inside lightweight, isolated containers. This competency covers authoring optimized Dockerfiles, multi-stage builds, managing container networking, volume mounting, Docker Compose multi-service orchestration, and container security best practices."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Docker (DevOps Tool), including container virtualization, OCI image layers, Dockerfiles, multi-stage builds, container networking, and Docker Compose. Able to perform routine tasks such as pulling public images from Docker Hub, starting/stopping containers (docker run, docker ps, docker stop), and writing basic single-stage Dockerfiles under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Docker (DevOps Tool) in everyday development. Independently handles authoring optimized multi-stage Dockerfiles to minimize image attack surfaces and sizes, managing named volumes, and running multi-service topologies with Docker Compose, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Docker (DevOps Tool). Independently implements complex solutions such as implementing non-root user execution, custom bridge networks, container health checks, multi-architecture image builds (buildx), and vulnerability scanning with Trivy, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Docker (DevOps Tool). Capable of solving intricate architectural challenges (architecting enterprise container platform governance, tuning rootless Docker daemon configurations, and designing container security baselines for mission-critical systems), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("5b47f839-aae8-4257-92bd-29d28ec869d4"),
        "code": "DEVOPS_GIT",
        "name": "Git & GitHub (Software Development Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000005"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Git is a distributed version control system designed to handle everything from small to very large projects with speed and efficiency. This competency covers branch management, commit histories, merging vs. rebasing, interactive rebase, resolving merge conflicts, pull request code review workflows, and GitHub Actions automation."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Git & GitHub (Software Development Tool), including distributed version control, Git object models (blobs, trees, commits), branching workflows, and conflict resolution. Able to perform routine tasks such as cloning repositories, creating feature branches, staging files, committing changes, and pushing commits to remote repositories (git add, git commit, git push) under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Git & GitHub (Software Development Tool) in everyday development. Independently handles managing team branching workflows (GitFlow, GitHub Flow), resolving merge conflicts cleanly, stashing temporary work, and opening well-documented pull requests, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Git & GitHub (Software Development Tool). Independently implements complex solutions such as executing interactive rebases (git rebase -i) to tidy commit histories, cherry-picking commits, identifying regression commits with git bisect, and managing repository hooks, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Git & GitHub (Software Development Tool). Capable of solving intricate architectural challenges (establishing organizational trunk-based development workflows, designing custom Git server hooks, recovering corrupted repository states via the reflog, and managing large monorepos), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000011"),
        "code": "DEVOPS_CICD",
        "name": "CI/CD Pipeline Automation (DevOps)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000005"),
        "domain": "Information Technology",
        "sub_domain": "Cloud & DevOps",
        "skill_family": "DevOps Engineering",
        "classification": "Functional Skill",
        "description": (
            "Continuous Integration and Continuous Delivery (CI/CD) automates software build, testing, and deployment cycles to deliver code rapidly and reliably. This competency evaluates pipeline-as-code scripting (GitHub Actions, GitLab CI), automated testing stages, artifact packaging, environment secret management, and zero-downtime deployment strategies (blue-green, canary)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of CI/CD Pipeline Automation (DevOps), including continuous integration, continuous delivery, pipeline-as-code (GitHub Actions, GitLab CI), automated testing stages, and secret management. Able to perform routine tasks such as viewing pipeline execution logs, triggering manual pipeline runs, and understanding the core benefits of automated continuous testing with guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing CI/CD Pipeline Automation (DevOps) in everyday development. Independently handles authoring declarative YAML pipeline workflows to automate linting, unit testing, and building container images upon code push and pull requests, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in CI/CD Pipeline Automation (DevOps). Independently implements complex solutions such as architecting matrix build pipelines, managing environment secrets, configuring automated release tagging, and implementing zero-downtime blue-green or canary deployments, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in CI/CD Pipeline Automation (DevOps). Capable of solving intricate architectural challenges (architecting enterprise release engineering platforms with GitOps, enforcing automated compliance and security gates, and optimizing continuous integration build cycle velocities), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b0000000-0000-0000-0000-000000000012"),
        "code": "DEVOPS_KUBERNETES",
        "name": "Kubernetes Orchestration (DevOps Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000005"),
        "domain": "Information Technology",
        "sub_domain": "Cloud & DevOps",
        "skill_family": "Infrastructure Engineering",
        "classification": "Tool",
        "description": (
            "Kubernetes is an open-source container orchestration system for automating application deployment, scaling, and management. This competency evaluates deploying Pods, Deployments, ReplicaSets, and Services (ClusterIP, NodePort, LoadBalancer), managing Ingress controllers, persistent volume claims (PVC), ConfigMaps, Secrets, and rolling zero-downtime updates."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Kubernetes Orchestration (DevOps Tool), including container orchestration, Pods, Deployments, ReplicaSets, Services (ClusterIP, NodePort, LoadBalancer), and Ingress controllers. Able to perform routine tasks such as inspecting cluster nodes and pods using kubectl (kubectl get pods, kubectl describe), viewing container logs, and restarting pods with supervision under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Kubernetes Orchestration (DevOps Tool) in everyday development. Independently handles writing declarative YAML manifests for Deployments and Services, injecting configuration via ConfigMaps and Secrets, and verifying rolling application updates, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Kubernetes Orchestration (DevOps Tool). Independently implements complex solutions such as configuring Ingress routing with TLS termination, implementing Horizontal Pod Autoscaling (HPA), setting readiness/liveness probes, and managing persistent volumes (PVC), optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Kubernetes Orchestration (DevOps Tool). Capable of solving intricate architectural challenges (architecting multi-cluster enterprise Kubernetes platforms, developing custom Kubernetes Operators with Custom Resource Definitions (CRDs), and designing disaster recovery plans), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("f73f7972-8399-5713-8556-1c4f4578485d"),
        "code": "DEVOPS_TERRAFORM",
        "name": "Terraform (Infrastructure as Code Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000005"),
        "domain": "Information Technology",
        "sub_domain": "Cloud & DevOps",
        "skill_family": "Cloud Automation",
        "classification": "Tool",
        "description": (
            "Terraform is an open-source infrastructure as code (IaC) software tool that enables operators to safely and predictably create, change, and improve cloud infrastructure. This competency covers HCL syntax, provider configurations, resource declarations, remote state backends (S3/DynamoDB locks), reusable modules, and plan/apply workflows."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Terraform (Infrastructure as Code Tool), including Infrastructure as Code (IaC), HashiCorp Configuration Language (HCL), providers, resources, remote state, and state locking. Able to perform routine tasks such as running terraform init, terraform plan, and terraform apply on existing configurations, and understanding the declarative nature of infrastructure code under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Terraform (Infrastructure as Code Tool) in everyday development. Independently handles provisioning cloud infrastructure resources (VPCs, compute instances, databases), managing input variables and outputs, and securing remote state with S3 and DynamoDB locks, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Terraform (Infrastructure as Code Tool). Independently implements complex solutions such as authoring modular reusable Terraform modules, managing state drift, applying dynamic blocks and for_each expressions, and integrating into CI/CD deployment pipelines, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Terraform (Infrastructure as Code Tool). Capable of solving intricate architectural challenges (architecting multi-cloud enterprise landing zones, authoring custom Terraform providers, and enforcing automated infrastructure compliance using Sentinel and Open Policy Agent (OPA)), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("53eedb7e-7c41-5ece-a0fd-3cffe4c96261"),
        "code": "DEVOPS_PROMETHEUS",
        "name": "Prometheus & Grafana (Monitoring Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000005"),
        "domain": "Information Technology",
        "sub_domain": "Cloud & DevOps",
        "skill_family": "Site Reliability Engineering (SRE)",
        "classification": "Tool",
        "description": (
            "Prometheus and Grafana provide end-to-end metrics collection, alerting, and interactive data visualization for cloud systems. This competency evaluates time-series metrics scrapers, PromQL query syntax (rate, histogram_quantile), Alertmanager notification routing, and building diagnostic Grafana operational dashboards."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Prometheus & Grafana (Monitoring Tool), including time-series metrics, PromQL query language (rate, histogram_quantile), Alertmanager notification routing, and Grafana dashboards. Able to perform routine tasks such as viewing pre-built Grafana operational dashboards, recognizing triggered alert states, and understanding core metrics terminology (CPU, memory, disk I/O) under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Prometheus & Grafana (Monitoring Tool) in everyday development. Independently handles writing basic PromQL queries, authoring custom dashboard panels in Grafana, and configuring Prometheus scraping targets via static configurations and exporters, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Prometheus & Grafana (Monitoring Tool). Independently implements complex solutions such as calculating latency percentiles (p95, p99) using histogram_quantile, authoring Service Level Objective (SLO) alert rules in Alertmanager, and handling label optimization, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Prometheus & Grafana (Monitoring Tool). Capable of solving intricate architectural challenges (architecting enterprise distributed observability backbones with Thanos/Cortex, defining organizational SRE error budget policies, and designing automated incident remediation), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("374c4d6d-6039-54a0-b2e3-d734c7b3fb26"),
        "code": "FE_REACT",
        "name": "React (Frontend UI Library)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000006"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Web Development",
        "classification": "Technical Skill",
        "description": (
            "React is an open-source front-end JavaScript library for building component-driven user interfaces. This competency covers declarative JSX, virtual DOM reconciliation, component lifecycles, built-in hooks (useState, useEffect, useMemo, useCallback, useRef), custom hooks development, Context API state propagation, and React Server Components (RSC)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of React (Frontend UI Library), including declarative JSX, Virtual DOM reconciliation, component lifecycle, built-in hooks (useState, useEffect, useMemo, useCallback), and custom hooks. Able to perform routine tasks such as building functional components, passing props, and managing basic local state using the useState hook under guided assistance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing React (Frontend UI Library) in everyday development. Independently handles handling side-effects and data fetching with useEffect, managing complex form states, and authoring reusable custom hooks to encapsulate component logic, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in React (Frontend UI Library). Independently implements complex solutions such as eliminating unnecessary re-renders using React.memo and useCallback, implementing code-splitting with React.lazy and Suspense, and designing scalable Context state architectures, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in React (Frontend UI Library). Capable of solving intricate architectural challenges (architecting enterprise design system component libraries, mastering React Fiber internals and concurrent rendering features (useTransition), and establishing frontend engineering guidelines), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("9b519dfd-46df-55a4-8341-e30002fa3eb6"),
        "code": "FE_TYPESCRIPT",
        "name": "TypeScript (Programming Language)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000006"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Programming Languages",
        "classification": "Technical Skill",
        "description": (
            "TypeScript is a strongly typed programming language that builds on JavaScript, giving better tooling at any scale. This competency covers static type checking, type inference, interfaces vs. type aliases, union & intersection types, generics, utility types (Partial, Pick, Omit), conditional types, mapped types, and strict compiler flag configuration."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of TypeScript (Programming Language), including static type systems, type inference, interfaces vs type aliases, union/intersection types, generics, and utility types (Partial, Pick, Omit). Able to perform routine tasks such as annotating primitive types, typing function signatures, and declaring basic interfaces for API response objects with guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing TypeScript (Programming Language) in everyday development. Independently handles utilizing union types with type guards, authoring reusable generic functions, and applying standard utility types without resorting to the 'any' type escape hatch, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in TypeScript (Programming Language). Independently implements complex solutions such as authoring advanced conditional types with infer, mapped types, template literal types, and ensuring end-to-end type safety between client components and backend APIs, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in TypeScript (Programming Language). Capable of solving intricate architectural challenges (authoring complex type-level metaprogramming libraries, designing publishable open-source typed packages, and establishing enterprise-wide type architecture standards), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("78f52d14-0b5c-5300-98fe-113a9ed7bbef"),
        "code": "FE_NEXTJS",
        "name": "Next.js App Router (Full-Stack Framework)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000006"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Web Frameworks",
        "classification": "Technical Skill",
        "description": (
            "Next.js is a React framework for building full-stack web applications. This competency evaluates the App Router paradigm, Server Components vs. Client Components ('use client'), nested layouts, Server Actions, dynamic routing, streaming UI with Suspense, Incremental Static Regeneration (ISR), and Edge middleware."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Next.js App Router (Full-Stack Framework), including App Router architecture, React Server Components vs Client Components ('use client'), nested layouts, Server Actions, and streaming with Suspense. Able to perform routine tasks such as creating new routes using the file-based routing convention (page.tsx), linking between pages with next/link, and creating basic layouts with guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Next.js App Router (Full-Stack Framework) in everyday development. Independently handles implementing form submissions with Server Actions, fetching data directly in Server Components, and structuring nested route layouts with loading and error boundaries, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Next.js App Router (Full-Stack Framework). Independently implements complex solutions such as optimizing full-stack rendering using streaming Suspense boundaries, configuring cache revalidation (revalidatePath, revalidateTag), and writing Edge middleware for auth verification, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Next.js App Router (Full-Stack Framework). Capable of solving intricate architectural challenges (architecting high-scale enterprise Next.js full-stack web applications, optimizing Core Web Vitals (LCP, CLS, INP), and designing global edge-deployment architectures), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("97556659-0403-54d2-a5ec-d854fe29644a"),
        "code": "FE_TAILWIND",
        "name": "Tailwind CSS (Frontend Styling Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000006"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Frontend Tooling",
        "classification": "Tool",
        "description": (
            "Tailwind CSS is a utility-first CSS framework packed with classes that can be composed to build any design directly in markup. This competency covers responsive breakpoints, flexbox/grid layouts, color palette customization, dark mode toggles, authoring reusable component classes via clsx/tailwind-merge, and CSS bundle optimization."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Tailwind CSS (Frontend Styling Tool), including utility-first styling, responsive breakpoints (sm, md, lg, xl), flexbox and grid utilities, dark mode, and component encapsulation with clsx/tailwind-merge. Able to perform routine tasks such as applying utility classes for padding, margin, typography, and colors to style basic buttons and cards with guided assistance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Tailwind CSS (Frontend Styling Tool) in everyday development. Independently handles building fully responsive user interfaces using responsive prefixes, implementing flexbox/grid alignments, and configuring dark mode transitions, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Tailwind CSS (Frontend Styling Tool). Independently implements complex solutions such as customizing design tokens in tailwind.config.ts, building reusable headless component wrappers with tailwind-merge, and eliminating CSS bundle bloat, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Tailwind CSS (Frontend Styling Tool). Capable of solving intricate architectural challenges (architecting corporate multi-brand design systems with Tailwind CSS, authoring custom Tailwind plugins, and ensuring strict web accessibility (WCAG a11y) visual compliance), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("afa5a759-1800-5be8-9764-871371d2298e"),
        "code": "FE_PLAYWRIGHT",
        "name": "Playwright (End-to-End Testing Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000006"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Quality Assurance Tools",
        "classification": "Tool",
        "description": (
            "Playwright is an open-source automation framework for end-to-end testing across modern web browsers (Chromium, Firefox, WebKit). This competency evaluates writing resilient test locators (getByRole, getByText), handling asynchronous navigation and auto-waiting, visual regression testing, network request interception/mocking, and multi-browser matrix execution in CI."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Playwright (End-to-End Testing Tool), including cross-browser automation (Chromium, Firefox, WebKit), resilient locators (getByRole, getByText), auto-waiting, Page Object Models (POM), and network mocking. Able to perform routine tasks such as recording and running simple click-and-type test scripts using the Playwright Test Generator under guided supervision under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Playwright (End-to-End Testing Tool) in everyday development. Independently handles authoring structured End-to-End (E2E) test suites using Page Object Models, asserting UI states with expect locators, and testing authentication flows with stored state, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Playwright (End-to-End Testing Tool). Independently implements complex solutions such as intercepting and mocking network API responses, conducting visual regression snapshot comparisons, and configuring parallel browser test execution in CI/CD pipelines, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Playwright (End-to-End Testing Tool). Capable of solving intricate architectural challenges (architecting enterprise distributed automated testing grids, designing cross-platform test harnesses, and driving continuous deployment quality gates across engineering teams), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("5e8f76b0-7fb8-593c-8382-f3c062a412f7"),
        "code": "AI_PYTORCH",
        "name": "PyTorch (Deep Learning Framework)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000007"),
        "domain": "Information Technology",
        "sub_domain": "Artificial Intelligence",
        "skill_family": "Deep Learning",
        "classification": "Technical Skill",
        "description": (
            "PyTorch is an optimized tensor library for deep learning using GPUs and CPUs. This competency covers dynamic computational graphs (autograd), tensor manipulation, custom neural network modules (nn.Module), loss functions, optimizers (AdamW, SGD), Dataset and DataLoader batching pipelines, GPU memory acceleration (CUDA), and model checkpointing."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of PyTorch (Deep Learning Framework), including dynamic computation graphs (autograd), tensors, custom neural network modules (nn.Module), loss functions, optimizers, and DataLoader pipelines. Able to perform routine tasks such as creating tensors, performing basic tensor arithmetic, defining simple linear layers, and executing forward passes under supervision under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing PyTorch (Deep Learning Framework) in everyday development. Independently handles constructing custom nn.Module classes, authoring complete training and validation loops, computing gradients with loss.backward(), and updating weights with optimizers, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in PyTorch (Deep Learning Framework). Independently implements complex solutions such as implementing deep convolutional and transformer architectures, managing mixed-precision training (torch.cuda.amp), and fine-tuning pretrained vision/NLP models, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in PyTorch (Deep Learning Framework). Capable of solving intricate architectural challenges (architecting multi-node DistributedDataParallel (DDP) training clusters, authoring custom C++/CUDA autograd kernels, and optimizing inference with TorchScript and TensorRT), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("9b7b4161-52f5-5839-8b98-4fc8c47789b8"),
        "code": "AI_SCIKIT_LEARN",
        "name": "Scikit-Learn (Machine Learning Package)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000007"),
        "domain": "Information Technology",
        "sub_domain": "Artificial Intelligence",
        "skill_family": "Machine Learning",
        "classification": "Technical Skill",
        "description": (
            "Scikit-Learn is a widely used Python library for classical machine learning algorithms. This competency evaluates supervised and unsupervised learning algorithms (Linear/Logistic Regression, Decision Trees, Random Forests, SVM, K-Means), data preprocessing (StandardScaler, OneHotEncoder), cross-validation, hyperparameter tuning (GridSearchCV), and evaluation metrics (ROC-AUC, F1-Score)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Scikit-Learn (Machine Learning Package), including supervised and unsupervised learning algorithms, data preprocessing (StandardScaler, OneHotEncoder), Pipeline abstractions, and cross-validation. Able to perform routine tasks such as loading datasets, instantiating linear/logistic regression models, and executing fit() and predict() methods under guided supervision under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Scikit-Learn (Machine Learning Package) in everyday development. Independently handles building end-to-end preprocessing and modeling Pipelines, performing train-test splitting, and evaluating models with confusion matrices, precision, recall, and F1-score, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Scikit-Learn (Machine Learning Package). Independently implements complex solutions such as tuning hyperparameters using GridSearchCV and cross-validation, handling imbalanced datasets (SMOTE/class weights), and analyzing feature importances, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Scikit-Learn (Machine Learning Package). Capable of solving intricate architectural challenges (architecting enterprise machine learning modeling platforms, designing complex ensemble voting/stacking pipelines, and setting rigorous statistical validation standards), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("c15634b1-55a6-5000-bb2d-2cbe13c9c909"),
        "code": "AI_HUGGINGFACE",
        "name": "Hugging Face Transformers (AI Library)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000007"),
        "domain": "Information Technology",
        "sub_domain": "Artificial Intelligence",
        "skill_family": "Natural Language Processing",
        "classification": "Tool",
        "description": (
            "Hugging Face Transformers provides thousands of pretrained models to perform tasks on texts, images, and audio. This competency covers tokenization pipelines (AutoTokenizer), model loading (AutoModelForCausalLM), pipeline abstractions, parameter-efficient fine-tuning (PEFT, LoRA, QLoRA), and model quantization (bitsandbytes)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Hugging Face Transformers (AI Library), including pretrained transformer models, AutoTokenizer, AutoModelForCausalLM, pipeline abstractions, and Parameter-Efficient Fine-Tuning (PEFT, LoRA). Able to perform routine tasks such as loading pretrained pipelines for sentiment analysis or text classification, and generating outputs with default parameters under guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Hugging Face Transformers (AI Library) in everyday development. Independently handles tokenizing text with attention masks and padding, generating text completions with custom generation parameters (temperature, top_p), and saving model checkpoints, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Hugging Face Transformers (AI Library). Independently implements complex solutions such as implementing LoRA/QLoRA parameter-efficient fine-tuning using SFTTrainer, quantizing models to 4-bit precision, and evaluating validation loss curves, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Hugging Face Transformers (AI Library). Capable of solving intricate architectural challenges (architecting enterprise high-throughput LLM serving infrastructure with vLLM/TGI, optimizing KV-cache memory utilization, and leading foundation model adaptation strategy), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("adcd110f-384b-5ddd-9ffc-30d6cc5f2b84"),
        "code": "AI_RAG_PIPELINE",
        "name": "Retrieval-Augmented Generation (RAG Architecture)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000007"),
        "domain": "Information Technology",
        "sub_domain": "Artificial Intelligence",
        "skill_family": "Generative AI",
        "classification": "Functional Skill",
        "description": (
            "Retrieval-Augmented Generation (RAG) optimizes the output of large language models by referencing authoritative knowledge bases. This competency evaluates document chunking strategies, vector embeddings generation, vector database indexing (Milvus, Qdrant, Chroma, PGVector), hybrid semantic/keyword search (BM25), cross-encoder reranking, and hallucination reduction."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Retrieval-Augmented Generation (RAG Architecture), including Retrieval-Augmented Generation, document chunking, dense vector embeddings, vector databases (PGVector, Qdrant), and hybrid search (BM25 + vector). Able to perform routine tasks such as understanding how external knowledge prevents LLM hallucinations and querying a simple vector store under guided assistance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Retrieval-Augmented Generation (RAG Architecture) in everyday development. Independently handles chunking raw text documents, generating vector embeddings, executing similarity search in vector databases, and injecting retrieved passages into prompt contexts, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Retrieval-Augmented Generation (RAG Architecture). Independently implements complex solutions such as implementing hybrid search combining BM25 keyword matching with dense embeddings, integrating cross-encoder neural rerankers, and applying metadata filtering, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Retrieval-Augmented Generation (RAG Architecture). Capable of solving intricate architectural challenges (architecting enterprise multi-modal RAG systems, designing agentic self-reflective retrieval pipelines, and establishing quantitative evaluation metrics with RAGAS), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("2069dfce-a786-5f25-a546-649d7cbf9cbb"),
        "code": "AI_MLOPS_MLFLOW",
        "name": "MLflow (MLOps Model Lifecycle Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000007"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "AI Engineering Tools",
        "classification": "Tool",
        "description": (
            "MLflow is an open-source platform for managing the end-to-end machine learning lifecycle. This competency evaluates tracking experiments (parameters, metrics, artifacts), model packaging with standard flavors, managing the central Model Registry (staging, production versions), and deploying models as scalable REST inference microservices."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of MLflow (MLOps Model Lifecycle Tool), including experiment tracking, parameter and metric logging, artifact stores, model packaging (MLmodel), and central Model Registry. Able to perform routine tasks such as logging parameters and training metrics with mlflow.log_param() and mlflow.log_metric() under guided supervision under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing MLflow (MLOps Model Lifecycle Tool) in everyday development. Independently handles tracking multi-run training experiments, saving model artifacts and plots, and comparing run performance metrics on the MLflow web UI, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in MLflow (MLOps Model Lifecycle Tool). Independently implements complex solutions such as managing model lifecycle transitions (Staging, Production) in the Model Registry, packaging projects with reproducible conda/docker environments, and deploying serving endpoints, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in MLflow (MLOps Model Lifecycle Tool). Capable of solving intricate architectural challenges (architecting enterprise-scale automated continuous retraining pipelines, establishing model drift monitoring and governance, and deploying high-availability model inference clusters), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("a8a8c56e-02b8-5bea-b89a-900a833a8161"),
        "code": "PY_CELERY",
        "name": "Celery (Python Distributed Task Queue)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Celery is an asynchronous task queue/job queue based on distributed message passing. This competency evaluates configuring Celery workers with Redis/RabbitMQ brokers, task retries with exponential backoff, task canvas workflows (chains, chords, groups), Celery Beat periodic scheduling, and monitoring worker saturation."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Celery (Python Distributed Task Queue), including distributed message queues, Redis/RabbitMQ brokers, worker pools, and task serialization. Able to perform routine tasks such as defining simple tasks with @app.task, invoking asynchronous executions with .delay(), and inspecting worker logs under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Celery (Python Distributed Task Queue) in everyday development. Independently handles configuring message brokers, handling task retries with automatic backoff, and scheduling periodic tasks with Celery Beat, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Celery (Python Distributed Task Queue). Independently implements complex solutions such as composing workflow canvases (chains, chords, groups), routing tasks across custom queues, and tuning worker prefetch limits, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Celery (Python Distributed Task Queue). Capable of solving intricate architectural challenges (architecting resilient distributed task execution clusters, handling broker failover with zero loss, and autoscaling workers), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("f5e992d0-cd27-5cff-80eb-02d7b8f1fc69"),
        "code": "JAVA_GRADLE",
        "name": "Gradle (Java Build Automation Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Gradle is a build automation tool known for its flexibility and performance using Groovy or Kotlin DSL. This competency covers build.gradle.kts configuration, dependency configurations (implementation, api, testImplementation), custom Gradle tasks, incremental build caching, and multi-project build modularization."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Gradle (Java Build Automation Tool), including Groovy/Kotlin DSL build scripts, task execution graphs, incremental builds, and dependency configurations. Able to perform routine tasks such as navigating build.gradle files, declaring external dependencies, and running standard tasks using the Gradle wrapper under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Gradle (Java Build Automation Tool) in everyday development. Independently handles managing dependency resolution strategies, configuring test logging, and authoring custom tasks with doLast actions, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Gradle (Java Build Automation Tool). Independently implements complex solutions such as modularizing multi-project builds with settings.gradle, authoring incremental tasks with declared inputs/outputs, and optimizing build scans, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Gradle (Java Build Automation Tool). Capable of solving intricate architectural challenges (authoring custom corporate Gradle plugins, implementing remote build cache infrastructure, and accelerating CI build speeds), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("e1d5820a-ddd7-5967-a146-cc87c5edf47e"),
        "code": "JAVA_SECURITY",
        "name": "Spring Security & OAuth2 (Java Framework)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Enterprise Frameworks",
        "classification": "Technical Skill",
        "description": (
            "Spring Security is a powerful and highly customizable authentication and access-control framework for Java. This competency evaluates SecurityFilterChain configuration, JWT token validation, Role-Based Access Control (@PreAuthorize), OAuth2 Resource Server integration, password hashing (BCrypt), and CSRF/CORS security policies."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Spring Security & OAuth2 (Java Framework), including SecurityFilterChain, authentication vs authorization, JWT token parsing, method-level security (@PreAuthorize), and OAuth2. Able to perform routine tasks such as configuring basic HTTP authentication, defining in-memory users, and securing specific URL patterns with permitAll() under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Spring Security & OAuth2 (Java Framework) in everyday development. Independently handles implementing stateless JWT authentication filters, validating bearer tokens, and enforcing role-based access control (RBAC), resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Spring Security & OAuth2 (Java Framework). Independently implements complex solutions such as integrating OAuth2 Authorization Server and OpenID Connect, implementing custom authentication providers, and configuring CSRF/CORS policies, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Spring Security & OAuth2 (Java Framework). Capable of solving intricate architectural challenges (architecting enterprise Single Sign-On (SSO) ecosystems, establishing zero-trust mTLS security, and leading corporate application security audits), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("b75af741-ccb9-5285-b747-8d43a9ec161e"),
        "code": "DB_MONGODB",
        "name": "MongoDB (NoSQL Document Database)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000008"),
        "domain": "Information Technology",
        "sub_domain": "Database Systems",
        "skill_family": "NoSQL Databases",
        "classification": "Tool",
        "description": (
            "MongoDB is a source-available, cross-platform, document-oriented database classified as a NoSQL product. This competency evaluates JSON/BSON document schema design, aggregation pipelines ($match, $group, $lookup, $unwind), compound and multikey indexes, replica set high availability, and sharded cluster collections."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of MongoDB (NoSQL Document Database), including document data models, BSON storage, aggregation pipelines ($match, $group, $lookup), and compound indexing. Able to perform routine tasks such as connecting via mongosh, executing basic CRUD queries (insertOne, find, updateOne, deleteOne), and understanding document structures under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing MongoDB (NoSQL Document Database) in everyday development. Independently handles authoring multi-stage aggregation pipelines, designing compound indexes, and structuring embedded versus referenced document models, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in MongoDB (NoSQL Document Database). Independently implements complex solutions such as analyzing query execution plans with explain('executionStats'), configuring write concerns, and managing replica set automated failover, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in MongoDB (NoSQL Document Database). Capable of solving intricate architectural challenges (architecting horizontally sharded MongoDB clusters, designing optimal shard key strategies avoiding jumbo chunks, and leading NoSQL strategy), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("57dbc60b-f685-516b-85b0-4e92eed78d1d"),
        "code": "DB_LIQUIBASE",
        "name": "Liquibase (Database Change Management Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000008"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Liquibase is an open-source database-independent library for tracking, managing, and applying database schema changes. This competency evaluates authoring XML/YAML/SQL changeSets, precondition validations, rollback strategies, and automated schema evolution within CI/CD pipelines."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Liquibase (Database Change Management Tool), including declarative database changelogs (YAML, XML, SQL), changeSets, preconditions, and databasechangelog audit tables. Able to perform routine tasks such as writing basic createTable and addColumn changeSets in YAML or SQL and running liquibase update under guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Liquibase (Database Change Management Tool) in everyday development. Independently handles integrating Liquibase into build pipelines, authoring explicit rollback blocks for all changeSets, and managing changelog parameters, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Liquibase (Database Change Management Tool). Independently implements complex solutions such as authoring automated preconditions to guard against unexpected schema states, managing context/label filters, and integrating into CI/CD pipelines, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Liquibase (Database Change Management Tool). Capable of solving intricate architectural challenges (establishing enterprise database release governance, implementing automated schema linting policies, and managing zero-downtime database evolution), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("5e46d867-017f-5600-907b-6656b73fbef9"),
        "code": "SYS_MAKE",
        "name": "GNU Make (Build Automation Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000004"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "GNU Make is a tool which controls the generation of executables and other non-source files of a program from the program's source files. This competency evaluates writing Makefiles, explicit and implicit pattern rules, automatic variables ($@, $<, $^), dependency generation with compiler flags (-MMD), phony targets (.PHONY), and parallel compilation (-j)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of GNU Make (Build Automation Tool), including Makefiles, target-prerequisite-recipe rules, automatic variables ($@, $<, $^), pattern rules, and phony targets (.PHONY). Able to perform routine tasks such as inspecting existing Makefiles, executing targets like make and make clean, and writing basic compilation recipes for small programs under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing GNU Make (Build Automation Tool) in everyday development. Independently handles authoring clean Makefiles utilizing pattern rules (%.o: %.c), managing compiler and linker flags (CFLAGS, LDFLAGS), and declaring .PHONY targets, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in GNU Make (Build Automation Tool). Independently implements complex solutions such as configuring automated C/C++ header dependency generation with compiler flags (-MMD), managing multi-directory recursive builds, and optimizing parallel execution (-j), optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in GNU Make (Build Automation Tool). Capable of solving intricate architectural challenges (architecting cross-platform build toolchains with GNU Make, eliminating subtle parallel build race conditions, and optimizing enterprise build speeds), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("7d6858ec-52de-5fa8-a73d-839099bca013"),
        "code": "SYS_SOCKETS",
        "name": "Network Socket Programming (C/C++)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000004"),
        "domain": "Information Technology",
        "sub_domain": "Systems Engineering",
        "skill_family": "Network Programming",
        "classification": "Technical Skill",
        "description": (
            "Network Socket Programming addresses the low-level Berkeley sockets API in C/C++ for TCP/IP and UDP communications. This competency encompasses socket creation, binding, listening, accepting client connections, handling non-blocking I/O multiplexing (select, poll, epoll), byte-order endianness conversion, and protocol packet serialization."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Network Socket Programming (C/C++), including Berkeley sockets API, TCP/UDP protocols, socket lifecycles (socket, bind, listen, accept, connect), and I/O multiplexing. Able to perform routine tasks such as creating basic blocking TCP client sockets, connecting to server ports, and sending simple byte strings with guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Network Socket Programming (C/C++) in everyday development. Independently handles building a functional TCP client-server echo application, handling socket address reuse (SO_REUSEADDR), and managing partial read and write buffers, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Network Socket Programming (C/C++). Independently implements complex solutions such as implementing high-performance non-blocking network servers using Linux epoll, managing socket state machines, and handling concurrent connection lifecycles without leaks, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Network Socket Programming (C/C++). Capable of solving intricate architectural challenges (architecting ultra-high-throughput network event loops handling 100K+ concurrent connections, tuning TCP socket window sizes, and designing binary wire protocols), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("1281cc3d-0111-59c0-976c-f059bb886a6c"),
        "code": "DEVOPS_ANSIBLE",
        "name": "Ansible (Configuration Management Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000005"),
        "domain": "Information Technology",
        "sub_domain": "Cloud & DevOps",
        "skill_family": "Infrastructure Automation",
        "classification": "Tool",
        "description": (
            "Ansible is an open-source IT automation engine that automates cloud provisioning, configuration management, and application deployment. This competency evaluates YAML Playbooks, inventory files, idempotent module executions (apt, yum, service, template), Ansible Roles, variable precedence, and Ansible Vault secret encryption."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Ansible (Configuration Management Tool), including agentless configuration management, YAML Playbooks, inventory files, idempotent modules, and Ansible Roles. Able to perform routine tasks such as running ad-hoc Ansible commands (ping, setup) against managed hosts and executing existing playbooks under guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Ansible (Configuration Management Tool) in everyday development. Independently handles authoring idempotent Ansible playbooks to provision software packages, render Jinja2 configuration templates, and restart system services reliably, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Ansible (Configuration Management Tool). Independently implements complex solutions such as structuring complex automation tasks into modular Ansible Roles, encrypting sensitive secrets using Ansible Vault, and configuring dynamic cloud inventory scripts, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Ansible (Configuration Management Tool). Capable of solving intricate architectural challenges (architecting enterprise-scale infrastructure automation platforms using Ansible Automation Platform (AWX), authoring custom Python modules, and establishing compliance automation), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("20404e18-9990-5e39-a5b6-5fd2b0728322"),
        "code": "DEVOPS_NGINX",
        "name": "Nginx (Web Server & Reverse Proxy Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000005"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Nginx is a high-performance HTTP server, reverse proxy, and load balancer. This competency covers server and location blocks, proxy_pass configuration, SSL/TLS certificate termination, HTTP load balancing algorithms (round-robin, least_conn, ip_hash), rate limiting, gzip compression, and caching static assets."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Nginx (Web Server & Reverse Proxy Tool), including event-driven architecture, reverse proxying, upstream load balancing, SSL/TLS termination, and rate limiting. Able to perform routine tasks such as editing basic nginx.conf server blocks to serve static HTML websites, starting/reloading Nginx, and inspecting access/error logs under supervision under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Nginx (Web Server & Reverse Proxy Tool) in everyday development. Independently handles configuring Nginx as a reverse proxy with proxy_pass, forwarding client headers (X-Forwarded-For, Host), and installing Let's Encrypt SSL/TLS certificates, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Nginx (Web Server & Reverse Proxy Tool). Independently implements complex solutions such as configuring rate limiting zones (limit_req), load balancing algorithms (round-robin, least_conn, ip_hash), static asset caching, and hardening security headers (HSTS, CSP), optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Nginx (Web Server & Reverse Proxy Tool). Capable of solving intricate architectural challenges (tuning Nginx worker processes and kernel socket parameters for millions of concurrent connections, architecting zero-downtime blue-green canary routing, and writing OpenResty Lua modules), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("cb998afb-8734-50f7-820c-7827b9d897c2"),
        "code": "FE_VITE",
        "name": "Vite (Frontend Build Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000006"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Frontend Tooling",
        "classification": "Tool",
        "description": (
            "Vite is a modern frontend build tool that provides an extremely fast development environment with native ES modules. This competency covers Hot Module Replacement (HMR), vite.config.ts configuration, Rollup bundling optimization, environment variable management (.env), path aliases, and plugin integration (React, Vue, Tailwind)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Vite (Frontend Build Tool), including native ES modules in development, Hot Module Replacement (HMR), Rollup-based production bundling, vite.config.ts, and environment variables. Able to perform routine tasks such as bootstrapping modern projects with npm create vite@latest, running dev servers, and executing production builds with guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Vite (Frontend Build Tool) in everyday development. Independently handles configuring path aliases, managing proxy configurations for local backend APIs, and integrating styling tools and TypeScript configurations in Vite, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Vite (Frontend Build Tool). Independently implements complex solutions such as customizing Rollup manual chunking strategies to minimize bundle sizes, analyzing bundle visualizers, and authoring custom Vite build plugins, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Vite (Frontend Build Tool). Capable of solving intricate architectural challenges (architecting enterprise monorepo build toolchains with Vite, developing community build plugins, and establishing lightning-fast developer experience (DX) workflows), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("70c7022a-450b-5df4-a609-81e5699052f7"),
        "code": "FE_ZUSTAND",
        "name": "Zustand (React State Management Library)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000006"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Frontend Architecture",
        "classification": "Technical Skill",
        "description": (
            "Zustand is a small, fast, and scalable bearbones state-management solution using simplified flux principles. This competency evaluates creating centralized stores (create), selective state subscriptions to prevent re-renders, middleware integration (persist to localStorage, devtools, immer), and managing async actions within the store."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Zustand (React State Management Library), including centralized store creation, selective state subscriptions, actions, middleware (persist, devtools, immer), and asynchronous state management. Able to perform routine tasks such as declaring a basic Zustand store with state properties and simple setter actions with guided assistance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Zustand (React State Management Library) in everyday development. Independently handles creating multi-slice stores, utilizing selector functions to subscribe only to required state slices preventing re-renders, and handling async API actions, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Zustand (React State Management Library). Independently implements complex solutions such as configuring persistence middleware for localStorage hydration, integrating Immer for nested state updates, and preventing state synchronization race conditions, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Zustand (React State Management Library). Capable of solving intricate architectural challenges (architecting enterprise client-side state architectures, harmonizing server caches (TanStack Query) with client stores, and establishing scalable state patterns), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("2b0dd5c7-3a1e-53e2-acdd-f820263fe5d2"),
        "code": "FE_CSS_LAYOUTS",
        "name": "Modern CSS (Flexbox, Grid & Layouts)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000006"),
        "domain": "Information Technology",
        "sub_domain": "Software Engineering",
        "skill_family": "Web Development",
        "classification": "Functional Skill",
        "description": (
            "Modern CSS Layouts focuses on creating complex, responsive, and adaptive web interfaces. This competency covers CSS Flexbox (axes, flex-grow, flex-shrink, align-items), CSS Grid (grid-template-columns, fr units, minmax, auto-fit, areas), CSS Custom Properties (variables), container queries, and subgrid for fluid responsive designs."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Modern CSS (Flexbox, Grid & Layouts), including CSS Box Model, Flexbox (axes, flex-grow, flex-shrink, alignment), CSS Grid (fr units, minmax, auto-fit, grid areas), and container queries. Able to perform routine tasks such as understanding margins, paddings, and using display: flex to align items horizontally or vertically with guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Modern CSS (Flexbox, Grid & Layouts) in everyday development. Independently handles building responsive 2D layouts using CSS Grid and Flexbox, handling media queries, and centering elements cleanly without CSS positioning hacks, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Modern CSS (Flexbox, Grid & Layouts). Independently implements complex solutions such as authoring fluid auto-fitting responsive grids without media queries, utilizing CSS custom properties for dynamic theming, and applying container queries for component-level responsiveness, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Modern CSS (Flexbox, Grid & Layouts). Capable of solving intricate architectural challenges (mastering the visual presentation layer and browser rendering pipelines, implementing cutting-edge CSS specifications (Subgrid, Anchor Positioning), and optimizing layout performance), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("4342aa4e-38b1-5fac-94e7-1c03fd085000"),
        "code": "AI_KERAS",
        "name": "TensorFlow & Keras (Deep Learning Framework)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000007"),
        "domain": "Information Technology",
        "sub_domain": "Artificial Intelligence",
        "skill_family": "Deep Learning",
        "classification": "Technical Skill",
        "description": (
            "TensorFlow and Keras provide a comprehensive ecosystem of tools for machine learning and deep neural networks. This competency evaluates Sequential and Functional APIs, custom layers and callbacks (EarlyStopping, ModelCheckpoint), transfer learning with pretrained models (MobileNet, ResNet), and export formats (SavedModel, TFLite)."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of TensorFlow & Keras (Deep Learning Framework), including Sequential and Functional APIs, neural network layers (Dense, Conv2D, LSTM), callbacks (EarlyStopping, ModelCheckpoint), and transfer learning. Able to perform routine tasks such as defining simple Sequential feedforward neural networks, compiling with loss and optimizer, and running model.fit() with guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing TensorFlow & Keras (Deep Learning Framework) in everyday development. Independently handles building convolutional neural networks (CNNs), applying image data augmentation, and using callbacks like EarlyStopping to prevent overfitting, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in TensorFlow & Keras (Deep Learning Framework). Independently implements complex solutions such as implementing multi-input/multi-output models with the Functional API, authoring custom loss functions, and fine-tuning deep transfer learning backbones, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in TensorFlow & Keras (Deep Learning Framework). Capable of solving intricate architectural challenges (optimizing enterprise deep learning serving with TensorFlow Serving and TensorRT, quantizing models for edge execution with TFLite, and establishing deep learning standards), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("1d584e06-e358-5216-89ce-0cd8c752c955"),
        "code": "AI_OPENCV",
        "name": "OpenCV (Computer Vision Library)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000007"),
        "domain": "Information Technology",
        "sub_domain": "Artificial Intelligence",
        "skill_family": "Computer Vision",
        "classification": "Technical Skill",
        "description": (
            "OpenCV is a library of programming functions mainly for real-time computer vision and image processing. This competency covers image matrix manipulations (NumPy arrays), color space conversions (BGR to RGB/HSV), filtering and edge detection (Canny, Sobel, Gaussian blur), contour detection, bounding boxes, and video stream frame processing."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of OpenCV (Computer Vision Library), including image matrix representations, color space transformations (BGR, RGB, HSV), spatial filtering, edge detection (Canny), and contour extraction. Able to perform routine tasks such as reading, displaying, and writing image files using cv2.imread(), cv2.imshow(), and cv2.imwrite() under supervision under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing OpenCV (Computer Vision Library) in everyday development. Independently handles applying image thresholding, smoothing filters, Canny edge detection, and drawing bounding boxes around detected image contours, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in OpenCV (Computer Vision Library). Independently implements complex solutions such as processing video streams in real-time, tracking moving objects across frames, and integrating OpenCV preprocessing into deep learning inference pipelines, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in OpenCV (Computer Vision Library). Capable of solving intricate architectural challenges (architecting industrial real-time computer vision systems, calibrating multi-camera matrices, and implementing 3D visual SLAM algorithms for autonomous systems), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
    {
        "id": uuid.UUID("e9d9f268-877e-5af8-9895-a18ad2baaf82"),
        "code": "AI_OLLAMA",
        "name": "Ollama (Local LLM Runtime Tool)",
        "group_id": uuid.UUID("a0000000-0000-0000-0000-000000000007"),
        "domain": "Information Technology",
        "sub_domain": "Information Technology",
        "skill_family": "Software Development Tools",
        "classification": "Tool",
        "description": (
            "Ollama is an open-source tool that allows users to run large language models locally on personal computers and servers. This competency evaluates installing and running quantized models (Llama 3, Mistral, Qwen), Modelfile customization (system prompts, temperature), REST API integration with Python/curl, GPU offloading, and embedding generation for local RAG."
        ),
        "rubrics": {
            "NOVICE": (
                "The individual with no experience or no understanding to perform the task."
            ),
            "BEGINNER": (
                "Understands the foundational purpose and core concepts of Ollama (Local LLM Runtime Tool), including local LLM runtimes, GGUF model quantization, Modelfiles (system prompts, temperature, parameters), and local REST API endpoints. Able to perform routine tasks such as installing Ollama, running basic model prompts from the command line (ollama run llama3), and chatting with local models under guidance under guided supervision, with limited troubleshooting capability."
            ),
            "COMPETENT": (
                "Demonstrates practical working proficiency in utilizing Ollama (Local LLM Runtime Tool) in everyday development. Independently handles authoring custom Modelfiles to set persona system instructions and temperature, managing local models, and querying the local Ollama HTTP REST API, resolves common errors, and delivers functional features without constant guidance."
            ),
            "PROFICIENT": (
                "Exhibits advanced technical command and architectural insight in Ollama (Local LLM Runtime Tool). Independently implements complex solutions such as integrating Ollama into local LangChain and private RAG workflows, generating local vector embeddings, and configuring multi-GPU layer offloading for high token generation speed, optimizes performance, and provides code review guidance to peers."
            ),
            "MASTER": (
                "Authoritative expert recognized for comprehensive mastery with near-flawless execution in Ollama (Local LLM Runtime Tool). Capable of solving intricate architectural challenges (architecting secure, air-gapped on-premise local LLM compute clusters, benchmarking GGUF quantization precision vs throughput, and leading private enterprise generative AI strategy), establishing engineering standards, and leading technical innovation."
            ),
        },
    },
]
