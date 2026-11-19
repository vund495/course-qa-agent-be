"""Section-path cleanup must remove OCR artifacts without erasing valid headings."""

from __future__ import annotations

from app.services.section_path import (
    clean_section_path,
    is_corrupted_section_segment,
    section_path_from_metadata,
)


def test_valid_ocr_and_generic_headings_survive_cleanup() -> None:
    path = "OCR Overview > Stack <T>"

    assert is_corrupted_section_segment("OCR Overview") is False
    assert is_corrupted_section_segment("Stack <T>") is False
    assert is_corrupted_section_segment("Stack <P>") is False
    assert is_corrupted_section_segment("Stack <p>") is False
    assert clean_section_path(path) == path
    assert clean_section_path("Stack <P>") == "Stack <P>"
    assert clean_section_path("Stack <p>") == "Stack <p>"
    assert section_path_from_metadata({"section_path": path}) == path


def test_plain_picture_text_heading_survives_cleanup() -> None:
    path = "Picture Text > Stack <p>"

    assert is_corrupted_section_segment("Picture Text") is False
    assert is_corrupted_section_segment("Picture Text > Stack <p>") is False
    assert clean_section_path(path) == path
    assert section_path_from_metadata({"section_path": path}) == path


def test_valid_ocr_and_generic_headers_survive_metadata_cleanup() -> None:
    meta = {
        "Header 1": "OCR Overview",
        "Header 2": "Stack <T>",
        "section_path": "OCR Overview > Stack <T>",
    }

    assert section_path_from_metadata(meta) == "OCR Overview > Stack <T>"


def test_dsa_picture_text_prefix_still_cleans_to_queues() -> None:
    corrupted_prefix = (
        "4: Right subtree<br>23<br> and left subtree<br>#3: Left subtree<br>"
        "14 31<br> no right subtree<br>#2: Right subtree 7<br> no left subtree<br>"
        "#1: Leaf Node 9<br><!-- End of picture text -->"
    )

    assert is_corrupted_section_segment(corrupted_prefix) is True
    assert clean_section_path(f"{corrupted_prefix} > Queues") == "Queues"
    assert (
        section_path_from_metadata(
            {
                "Header 1": corrupted_prefix,
                "Header 2": "Queues",
                "section_path": f"{corrupted_prefix} > Queues",
            }
        )
        == "Queues"
    )
