from __future__ import annotations

from medparse.ifu.frontmatter import infer_manufacturer_from_footer_texts


def test_infer_manufacturer_from_footer_texts_uses_domains_and_copyright() -> None:
    lines = [
        "© 2022 Example Medical Inc.",
        "All rights reserved.",
        "https://www.examplemedical.com/support",
        "Contact us at info@examplemedical.com",
    ]

    inferred = infer_manufacturer_from_footer_texts(lines)

    assert inferred == "Example Medical Inc"
