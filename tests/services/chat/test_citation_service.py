from types import SimpleNamespace

from app.services.citation_service import (
    build_universal_jump_url,
    extract_best_sentence,
    normalize_search_url,
    verify_citations,
)


def test_normalize_search_url_prefixes_provider_relative_redirects():
    assert normalize_search_url("/goto?url=CAESabc") == "https://www.google.com/goto?url=CAESabc"
    assert normalize_search_url("goto?url=CAESabc") == "https://www.google.com/goto?url=CAESabc"
    assert normalize_search_url("//www.google.com/goto?url=CAESabc") == (
        "https://www.google.com/goto?url=CAESabc"
    )
    assert normalize_search_url("https://example.com/article") == "https://example.com/article"
    assert normalize_search_url(None) == ""


def test_internet_citations_normalizes_relative_redirect_url():
    from app.services.rag_service import WebResult, internet_citations

    sources = internet_citations(
        [WebResult(title="Email guide", url="/goto?url=CAESabc", content="Send email")]
    )

    assert sources[0].url == "https://www.google.com/goto?url=CAESabc"


def test_build_universal_jump_url_with_range():
    base_url = "https://en.wikipedia.org/wiki/C_(programming_language)"
    snippet = "C was originally developed by Dennis Ritchie between 1972 and 1973 at Bell Labs."

    url = build_universal_jump_url(base_url, snippet)
    assert "#:~:text=" in url
    assert "C%20was%20originally%20developed" in url
    assert "1973%20at%20Bell%20Labs" in url
    assert "Labs." not in url


def test_build_universal_jump_url_short_and_empty():
    assert build_universal_jump_url("https://example.com", "") == "https://example.com"
    assert build_universal_jump_url("https://example.com", None) == "https://example.com"
    assert build_universal_jump_url("https://example.com", "Dennis Ritchie") == "https://example.com#:~:text=Dennis%20Ritchie"


def test_build_universal_jump_url_with_markdown_and_hyphen():
    base_url = "https://example.com/blog/ai-sdlc"
    snippet = "Home > Blog\n\n**An AI-led SDLC** accelerates delivery and improves developer productivity across the board."
    url = build_universal_jump_url(base_url, snippet)
    assert "#:~:text=" in url
    assert "**" not in url
    # Hyphen must be percent-encoded as %2D according to W3C spec
    assert "%2D" in url
    assert "Home" not in url  # Should select the coherent paragraph/sentence


def test_extract_best_sentence_selects_most_relevant_clause():
    chunk = (
        "Welcome to the course overview. "
        "The final practical exam accounts for 60% of your total grade. "
        "Students missing more than 20% of class will not be allowed to take the exam."
    )
    assertion = "How much does the practical exam count for?"
    best = extract_best_sentence(chunk, assertion)
    assert "60% of your total grade" in best
    assert "Welcome to the course" not in best


def test_verify_citations_removes_hallucinated_and_out_of_bounds_markers():
    chunks = [
        SimpleNamespace(content="Python was created by Guido van Rossum and released in 1991."),
        SimpleNamespace(content="Calculus focuses on limits, functions, derivatives, and integrals."),
    ]

    # [1] is valid, [99] is out of bounds, [2] in second sentence has NO relation to Calculus
    answer = (
        "Python was designed by Guido [1]. "
        "Albert Einstein invented relativity in Switzerland [2]. "
        "Random unsourced statement [99]."
    )

    clean_answer, valid_indices = verify_citations(answer, chunks)
    assert "[1]" in clean_answer
    assert "[2]" not in clean_answer
    assert "[99]" not in clean_answer
    assert valid_indices == [1]


def test_cited_page_citations_capped_at_max_citations():
    from app.services.rag_service import ScoredChunk, cited_page_citations

    # Create 5 distinct page chunks
    chunks = [
        ScoredChunk(content=f"Content for section {i}", score=0.9, metadata={"document_id": f"doc-{i}", "page_number": i})
        for i in range(1, 6)
    ]
    # Answer cites all 5 chunks
    answer = "Points: [1], [2], [3], [4], [5]."

    # Default max_citations is 3
    sources = cited_page_citations(chunks, answer)
    assert len(sources) == 3
    assert [s.document_id for s in sources] == ["doc-1", "doc-2", "doc-3"]


def test_extract_best_sentence_prefers_exact_over_longer_neighbor():
    chunk = (
        "The input function reads text from the user. "
        "The input function reads text from the user and returns it as a string to the caller in this python program."
    )
    assertion = "The input function reads text from the user."
    best = extract_best_sentence(chunk, assertion)
    assert best == "The input function reads text from the user."


def test_extract_cited_passages_overview_with_reconstructed_headers():
    from app.services.citation_service import extract_cited_passages
    from app.services.rag_service import ScoredChunk

    # Chunks have Header 1 and Header 4 instead of explicit section_path
    c1 = ScoredChunk(
        content="- **Rich Standard Library**: C++ provides STL templates for efficiency.",
        score=0.99,
        metadata={"document_id": "doc-1", "page_number": 16, "Header 1": "C++ Basics", "Header 4": "Advantages of C++", "chunk_index": 1},
    )
    c2 = ScoredChunk(
        content="- **OOPS Concepts**: C++ provides OOP features like polymorphism.",
        score=0.98,
        metadata={"document_id": "doc-1", "page_number": 17, "Header 1": "C++ Basics", "Header 4": "Advantages of C++", "chunk_index": 2},
    )
    answer = "The advantages of C++ include STL and OOP [1]."
    question = "What are the advantages of C++?"
    passages = extract_cited_passages(answer, [c1, c2], question=question)

    assert 1 in passages
    # Overview mode includes bullets from both member chunks under the Advantages section
    combined = " ".join(passages[1])
    assert "Rich Standard Library" in combined
    assert "OOPS Concepts" in combined


def test_extract_cited_passages_comparison_table_with_negation():
    from app.services.citation_service import extract_cited_passages
    from app.services.rag_service import ScoredChunk

    chunk = ScoredChunk(
        content="Features of C++:\n- OOPS Concepts: C++ provides OOP like class, object, polymorphism.\n- Memory Management: C++ uses new and delete.",
        score=0.95,
        metadata={"document_id": "doc-1", "page_number": 4},
    )
    # Comparison table where a cell contains negation "No"
    answer = (
        "| Feature | C | C++ |\n"
        "| --- | --- | --- |\n"
        "| OOP | No | Yes [1] |\n"
    )
    passages = extract_cited_passages(answer, [chunk], question="Compare C and C++ on OOP")
    assert 1 in passages
    assert any("OOPS Concepts" in p for p in passages[1])


def test_extract_cited_passages_cross_lingual_vietnamese():
    from app.services.citation_service import extract_cited_passages
    from app.services.rag_service import ScoredChunk

    chunk = ScoredChunk(
        content="- OOPS Concepts: C++ provides OOP like class, object, polymorphism.",
        score=0.95,
        metadata={"document_id": "doc-1", "page_number": 4},
    )
    answer = "C++ hỗ trợ lập trình hướng đối tượng với các khái niệm như class, object [1]."
    question = "So sánh C và C++ về tính năng hướng đối tượng"
    passages = extract_cited_passages(answer, [chunk], question=question)
    assert 1 in passages
    assert "OOPS Concepts" in passages[1][0]


def test_cited_page_citations_merges_same_page_chunks():
    from app.services.rag_service import ScoredChunk, cited_page_citations

    c1 = ScoredChunk(
        content='Printing "Hello, World!" is the first program in C++.',
        score=0.99,
        metadata={"document_id": "doc-cpp", "page_number": 33, "section_path": "C++ > Hello World Intro"},
    )
    c2 = ScoredChunk(
        content='int main() { cout << "Hello, World!"; return 0; }',
        score=0.98,
        metadata={"document_id": "doc-cpp", "page_number": 33, "section_path": "C++ > Hello World Code"},
    )
    answer = 'The first C++ program prints Hello World [1]. Here is the code: cout << "Hello, World!" [2].'
    sources = cited_page_citations([c1, c2], answer, max_citations=3)

    # Both chunks are on page 33 of doc-cpp, so they MUST collapse into 1 citation source
    assert len(sources) == 1
    assert sources[0].document_id == "doc-cpp"
    assert sources[0].page == 33
    assert sources[0].pages == (33,)
    assert sources[0].page_label == "33"
    assert sources[0].section == "C++"
    assert set(sources[0].indexes) == {1, 2}
    # Highlights from both chunks are preserved
    assert len(sources[0].highlights) == 2


def test_cited_page_citations_merges_adjacent_page_section():
    from app.services.rag_service import ScoredChunk, cited_page_citations

    c1 = ScoredChunk(
        content="Overview of pointers and memory addresses in C++.",
        score=0.95,
        metadata={"document_id": "doc-cpp", "page_number": 40, "section_path": "C++ > Pointers"},
    )
    c2 = ScoredChunk(
        content="Pointer arithmetic and dereferencing syntax.",
        score=0.94,
        metadata={"document_id": "doc-cpp", "page_number": 41, "section_path": "C++ > Pointers > Operations"},
    )
    answer = "Pointers manage memory addresses [1] and support dereferencing [2]."
    sources = cited_page_citations([c1, c2], answer, max_citations=3)

    # Adjacent pages 40 and 41 sharing section path collapse into continuous multi-page citation
    assert len(sources) == 1
    assert sources[0].document_id == "doc-cpp"
    assert sources[0].page == 40
    assert sources[0].pages == (40, 41)
    assert sources[0].page_label == "40-41"
    assert sources[0].section == "C++ > Pointers"
    assert set(sources[0].indexes) == {1, 2}


def test_citation_section_falls_back_to_headers_then_page_only():
    from app.services.rag_service import ScoredChunk, cited_page_citations, curriculum_citations

    header_chunk = ScoredChunk(
        content="Pointers store memory addresses.",
        score=0.9,
        metadata={
            "document_id": "doc-headers",
            "page_number": 7,
            "Header 1": "Chapter 1",
            "Header 2": "Section 1.1",
        },
    )
    header_sources = cited_page_citations(
        [header_chunk], "Pointers store memory addresses [1]."
    )
    assert header_sources[0].section == "Chapter 1 > Section 1.1"

    section_chunk = ScoredChunk(
        content="Pointers can be dereferenced.",
        score=0.9,
        metadata={
            "document_id": "doc-section",
            "page_number": 9,
            "section_path": "C++ > Pointers",
        },
    )
    provisional = curriculum_citations([section_chunk])
    assert provisional[0].section == "C++ > Pointers"

    page_only_chunk = ScoredChunk(
        content="Pointers can be compared.",
        score=0.9,
        metadata={"document_id": "doc-page-only", "page_number": 11},
    )
    page_only = cited_page_citations(
        [page_only_chunk], "Pointers can be compared [1]."
    )
    assert page_only[0].section is None
    assert page_only[0].page == 11

    unrelated_sections = ScoredChunk(
        content="Alpha fact is true.",
        score=0.9,
        metadata={
            "document_id": "doc-mixed",
            "page_number": 12,
            "section_path": "Intro",
        },
    )
    unrelated_sections_2 = ScoredChunk(
        content="Beta fact is true.",
        score=0.9,
        metadata={
            "document_id": "doc-mixed",
            "page_number": 12,
            "section_path": "Code",
        },
    )
    merged = cited_page_citations(
        [unrelated_sections, unrelated_sections_2],
        "Alpha fact is true [1]. Beta fact is true [2].",
    )
    assert len(merged) == 1
    assert merged[0].section is None


def test_citation_cleans_legacy_ocr_section_path_but_preserves_valid_suffix():
    from app.services.rag_service import ScoredChunk, curriculum_citations

    corrupted_prefix = (
        "4: Right subtree<br>23<br> and left subtree<br>#3: Left subtree<br>"
        "14 31<br> no right subtree<br>#2: Right subtree 7<br> no left subtree<br>"
        "#1: Leaf Node 9<br><!-- End of picture text -->"
    )
    queue_chunk = ScoredChunk(
        content="Queue enqueue and dequeue steps.",
        score=0.9,
        metadata={
            "document_id": "dsa-doc",
            "page_number": 59,
            "section_path": f"{corrupted_prefix} > Queues",
        },
    )
    nested_chunk = ScoredChunk(
        content="A standard queue supports enqueue and dequeue.",
        score=0.9,
        metadata={
            "document_id": "dsa-doc",
            "page_number": 60,
            "section_path": f"{corrupted_prefix} > Queues > 6.1 A standard queue",
        },
    )

    queue_source, nested_source = curriculum_citations([queue_chunk, nested_chunk])
    assert queue_source.section == "Queues"
    assert nested_source.section == "Queues > 6.1 A standard queue"


def test_citation_preserves_valid_ocr_and_generic_section_titles():
    from app.services.rag_service import ScoredChunk, curriculum_citations

    chunk = ScoredChunk(
        content="OCR overview and a generic stack implementation.",
        score=0.9,
        metadata={
            "document_id": "ocr-doc",
            "page_number": 7,
            "section_path": "OCR Overview > Stack <T>",
        },
    )

    source = curriculum_citations([chunk])[0]
    assert source.section == "OCR Overview > Stack <T>"


def test_citation_preserves_plain_picture_text_and_lowercase_generic_title():
    from app.services.rag_service import ScoredChunk, curriculum_citations

    chunk = ScoredChunk(
        content="Picture text section for a generic stack.",
        score=0.9,
        metadata={
            "document_id": "picture-doc",
            "page_number": 8,
            "section_path": "Picture Text > Stack <p>",
        },
    )

    source = curriculum_citations([chunk])[0]
    assert source.section == "Picture Text > Stack <p>"


def test_history_citation_schema_preserves_section_and_page_metadata():
    from app.schemas.history import ChatCitation

    citation = ChatCitation.model_validate(
        {
            "index": 1,
            "kind": "curriculum",
            "title": "C++ slides.pdf",
            "url": None,
            "snippet": "Pointers store addresses.",
            "document_id": "doc-1",
            "page": 7,
            "pages": [7, 8],
            "page_label": "7-8",
            "section": "Chapter 1 > Pointers",
            "indexes": [1],
            "highlights": ["Pointers store addresses."],
        }
    )

    assert citation.section == "Chapter 1 > Pointers"
    assert citation.pages == [7, 8]
    assert citation.page_label == "7-8"
    assert citation.model_dump()["section"] == "Chapter 1 > Pointers"


def test_code_block_citation_prefers_code_over_intro_sentence():
    from app.services.citation_service import extract_cited_passages
    from app.services.rag_service import ScoredChunk

    chunk = ScoredChunk(
        content=(
            'Let us see the first C++ program that prints "Hello, World!" −\n'
            '```cpp\n'
            '#include<iostream>\n'
            'using namespace std;\n'
            'int main() {\n'
            '    cout << "Hello, World!";\n'
            '    return 0;\n'
            '}\n'
            '```\n'
            '###### **Output**\n'
            'This program will print "Hello, World!" on the output screen.'
        ),
        score=0.99,
        metadata={"document_id": "doc-cpp", "page_number": 33},
    )
    answer = (
        'Below is the standard C++ program that prints "Hello, World!" [1]:\n\n'
        '```cpp\n'
        '#include <iostream>\n'
        'using namespace std;\n'
        'int main() {\n'
        '    cout << "Hello, World!";\n'
        '    return 0;\n'
        '}\n'
        '```'
    )
    passages = extract_cited_passages(answer, [chunk], question="write hello world in c++")
    assert 1 in passages
    # Must highlight the code block, NOT the conversational intro sentence
    assert any("int main()" in p for p in passages[1])
    assert not any(p.startswith("Let us see the first") for p in passages[1])


def test_extract_cited_passages_short_list_items():
    from app.services.citation_service import extract_cited_passages
    from app.services.rag_service import ScoredChunk

    chunk = ScoredChunk(
        content=(
            "There are many C++ compilers available that you can use to compile and run the abovementioned program:\n"
            "- Clang C++\n"
            "- IBM C++\n"
            "- HP C++\n"
            "- Intel C++"
        ),
        score=0.99,
        metadata={"document_id": "doc-compilers", "page_number": 3},
    )
    answer = (
        "Here are the available compilers [1]:\n"
        "- Clang C++ [1]\n"
        "- IBM C++ [1]\n"
        "- HP C++ [1]\n"
        "- Intel C++ [1]"
    )
    question = "What are some C++ compilers you can use to run programs?"
    passages = extract_cited_passages(answer, [chunk], question=question)
    assert 1 in passages
    # All short list items must be extracted, not overridden by the intro sentence
    assert any("Clang C++" in p for p in passages[1])
    assert any("IBM C++" in p for p in passages[1])
    assert any("HP C++" in p for p in passages[1])
    assert any("Intel C++" in p for p in passages[1])


def test_fibonacci_irrelevant_intro_chunk_yields_no_citations():
    from app.services.citation_service import verify_citations
    from app.services.rag_service import ScoredChunk, cited_page_citations

    # Chunk contains compiler setup and general C++ intro boilerplate
    c1 = ScoredChunk(
        content=(
            "We have provided an easy C++ online compiler. Click on this link to try it.\n"
            "The basic structure of a C++ program consists of the following parts:\n"
            "- Headers\n"
            "- Main function\n"
            "- Return statement"
        ),
        score=0.9,
        metadata={"document_id": "doc-1", "page_number": 1},
    )
    question = "Viết giúp tôi hoàn chỉnh bài tập code tính số Fibonacci bằng đệ quy trong C++"
    answer = "Để giải bài toán tính số Fibonacci bằng đệ quy trong C++, ta cần xác định trường hợp cơ sở [1]."

    clean_ans, valid = verify_citations(answer, [c1], question=question)
    assert valid == []
    assert "[1]" not in clean_ans

    sources = cited_page_citations([c1], answer, question=question)
    assert len(sources) == 0


def test_fibonacci_relevant_recursion_chunk_yields_exact_highlight():
    from app.services.citation_service import verify_citations
    from app.services.rag_service import ScoredChunk, cited_page_citations

    c = ScoredChunk(
        content=(
            "Recursion in C++:\n"
            "- A recursive function must define a base case to terminate execution.\n"
            "- Recursive step breaks the problem into smaller subproblems."
        ),
        score=0.95,
        metadata={"document_id": "doc-1", "page_number": 12},
    )
    question = "Viết giúp tôi hoàn chỉnh bài tập code tính số Fibonacci bằng đệ quy trong C++"
    answer = "Hàm đệ quy tính Fibonacci cần có trường hợp cơ sở (base case) để dừng [1]."

    clean_ans, valid = verify_citations(answer, [c], question=question)
    assert valid == [1]
    assert "[1]" in clean_ans

    sources = cited_page_citations([c], answer, question=question)
    assert len(sources) == 1
    assert "- A recursive function must define a base case to terminate execution." in sources[0].highlights


def test_extract_cited_passages_filters_running_headers_and_chapter_bleeds():
    from app.services.citation_service import extract_cited_passages
    from app.services.rag_service import ScoredChunk

    chunk = ScoredChunk(
        content=(
            "#### Facts about C++\n"
            "Here are some interesting and lesser-known facts about the C++ programming language −\n\n"
            "- C++ language was invented at the AT&T Bell Labs.\n"
            "- C++ language is heavily used in NASA.\n\n"
            "C++ Tutorial\n\n"
            "- C++ does not support pure object-oriented programming.\n\n"
            "C++ Tutorial **\n\n"
            "2. C++ Environment Setup**"
        ),
        score=0.95,
        metadata={
            "document_id": "doc-cpp",
            "file_name": "cpp_tutorial.pdf",
            "page_number": 17,
            "section_path": "C++ Tutorial > Facts about C++",
        },
    )
    answer = "Here are key facts about C++ [1]."
    question = "tell me facts about C++"
    passages = extract_cited_passages(answer, [chunk], question=question)

    assert 1 in passages
    extracted = list(passages[1])

    # Verified: legitimate bullet points are retained
    assert any("AT&T Bell Labs" in p for p in extracted)
    assert any("NASA" in p for p in extracted)
    assert any("pure object-oriented programming" in p for p in extracted)

    # Verified: running headers, footers, and next-chapter headings are filtered out
    assert not any(p.strip() == "C++ Tutorial" for p in extracted)
    assert not any("C++ Tutorial **" in p for p in extracted)
    assert not any("2. C++ Environment Setup" in p for p in extracted)


def test_extract_cited_passages_preserves_roman_numerals_and_short_informative_items():
    from app.services.citation_service import extract_cited_passages
    from app.services.rag_service import ScoredChunk

    chunk = ScoredChunk(
        content=(
            "Advantages of C++:\n\n"
            "I. High performance: compiles to native machine code.\n\n"
            "II. Hardware access: direct memory manipulation via pointers.\n\n"
            "III. Portability"
        ),
        score=0.96,
        metadata={
            "document_id": "doc-cpp",
            "file_name": "cpp_tutorial.pdf",
            "page_number": 16,
            "section_path": "Advantages of C++",
        },
    )
    answer = "The advantages of C++ are high performance and hardware access [1]."
    question = "advantages of c++"
    passages = extract_cited_passages(answer, [chunk], question=question)

    assert 1 in passages
    extracted = list(passages[1])

    # All Roman numeral points must be safely preserved
    assert any("High performance" in p for p in extracted)
    assert any("Hardware access" in p for p in extracted)
    assert any("Portability" in p for p in extracted)


def test_extract_cited_passages_preserves_numbered_list_items():
    from app.services.citation_service import extract_cited_passages
    from app.services.rag_service import ScoredChunk

    chunk = ScoredChunk(
        content=(
            "Key Benefits of C++:\n\n"
            "1. Low-level control: direct hardware access.\n\n"
            "2. High execution speed: minimal runtime overhead."
        ),
        score=0.96,
        metadata={
            "document_id": "doc-cpp",
            "file_name": "cpp_tutorial.pdf",
            "page_number": 16,
            "section_path": "Key Benefits of C++",
        },
    )
    answer = "C++ gives low-level control and high speed [1]."
    question = "benefits of c++"
    passages = extract_cited_passages(answer, [chunk], question=question)

    assert 1 in passages
    extracted = list(passages[1])

    # Numbered points must be preserved
    assert any("Low-level control" in p for p in extracted)
    assert any("High execution speed" in p for p in extracted)






