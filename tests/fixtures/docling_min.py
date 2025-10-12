from medparse.ingest.pdf_reader import PageContent, TextBlock


def build_min_pages():
    page1 = PageContent(
        number=1,
        text="Heading\nBody text",
        lines=["Heading", "Body text"],
        blocks=[
            TextBlock(text="Heading", bbox=(0, 0, 50, 10), font_size=14, is_bold=True),
            TextBlock(text="Body text", bbox=(0, 12, 80, 24), font_size=10, is_bold=False),
        ],
        tables=[],
    )

    page2 = PageContent(
        number=2,
        text="Continuation",
        lines=["Continuation"],
        blocks=[
            TextBlock(text="Continuation", bbox=(0, 0, 90, 12), font_size=10, is_bold=False),
        ],
        tables=[],
    )

    return [page1, page2]
