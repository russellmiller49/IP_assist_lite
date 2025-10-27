"""UMLS entity linking via scispaCy with optional QuickUMLS support."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from medparse.utils.log import get_logger

# Import scispacy to register its components with spaCy
try:
    import scispacy  # noqa: F401
    from scispacy.linking import EntityLinker  # noqa: F401
except ImportError:
    pass  # scispacy not available

LOGGER = get_logger(__name__)


class UmlsEntity(BaseModel):
    """Lightweight representation of a linked UMLS concept."""

    cui: str
    preferred_term: Optional[str] = None
    semtypes: List[str] = Field(default_factory=list)
    offsets: List[Tuple[int, int]] = Field(default_factory=list)
    text: str
    page: Optional[int] = None
    confidence: float = 0.0


def link_umls_entities(
    page_texts: Sequence[Tuple[int, str]],
    *,
    quickumls_path: Optional[str] = None,
    min_confidence: float = 0.85,
) -> List[UmlsEntity]:
    """Link entities for ``page_texts`` returning ``UmlsEntity`` objects.

    Falls back gracefully when scispaCy models are unavailable. Results are
    cached per page hash to avoid redundant work within a single process run.
    """

    entities: List[UmlsEntity] = []

    if not page_texts:
        return entities

    linker = _get_scispacy_linker()
    if not linker:
        LOGGER.warning("UMLS linking skipped: scispaCy linker unavailable")
        return entities

    cache = _page_cache()

    for page_number, text in page_texts:
        if not text or len(text) < 16:
            continue

        page_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()
        cached = cache.get(page_hash)
        if cached is None:
            cached = _link_page_text(linker, text, min_confidence=min_confidence)
            cache[page_hash] = cached

        # Create shallow copies annotating the page number
        for entity in cached:
            entities.append(
                UmlsEntity(
                    cui=entity.cui,
                    preferred_term=entity.preferred_term,
                    semtypes=list(entity.semtypes),
                    offsets=list(entity.offsets),
                    confidence=entity.confidence,
                    text=entity.text,
                    page=page_number,
                )
            )

    if quickumls_path:
        entities.extend(_quickumls_link(page_texts, quickumls_path))

    return entities


def _link_page_text(linker, text: str, *, min_confidence: float) -> List[UmlsEntity]:
    """Run scispaCy linker on ``text`` and return page-level entities."""

    nlp = _get_scispacy_model()
    assert nlp is not None  # Guarded by caller

    doc = nlp(text)
    page_entities: Dict[Tuple[str, int, int], UmlsEntity] = {}

    for ent in doc.ents:
        if not ent._.kb_ents:
            continue

        cui, score = max(ent._.kb_ents, key=lambda item: item[1])
        if score < min_confidence:
            continue

        kb_entry = linker.kb.cui_to_entity.get(cui)
        preferred = kb_entry.canonical_name if kb_entry else None
        semtypes = list(kb_entry.types) if kb_entry else []

        key = (cui, ent.start_char, ent.end_char)
        if key not in page_entities:
            page_entities[key] = UmlsEntity(
                cui=cui,
                preferred_term=preferred,
                semtypes=semtypes,
                offsets=[(ent.start_char, ent.end_char)],
                confidence=score,
                text=ent.text,
            )
        else:
            page_entities[key].offsets.append((ent.start_char, ent.end_char))
            if score > page_entities[key].confidence:
                page_entities[key].confidence = score

    return list(page_entities.values())


def _quickumls_link(
    page_texts: Sequence[Tuple[int, str]],
    quickumls_path: str,
    *,
    similarity: float = 0.88,
) -> List[UmlsEntity]:
    """Optional QuickUMLS fuzzy matching to complement scispaCy results."""

    try:
        from quickumls import QuickUMLS  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        LOGGER.warning("QuickUMLS requested but package not installed")
        return []

    matcher = QuickUMLS(
        quickumls_path,
        best_match=True,
        threshold=similarity,
        window=5,
    )

    entities: List[UmlsEntity] = []
    for page_number, text in page_texts:
        if not text:
            continue
        matches = matcher.match(text, best_match=True, ignore_syntax=False)
        for match in matches:
            candidate = max(match, key=lambda item: item["similarity"])
            if candidate["similarity"] < similarity:
                continue
            entities.append(
                UmlsEntity(
                    cui=candidate["cui"],
                    preferred_term=candidate.get("preferred"),
                    semtypes=candidate.get("semtypes", []),
                    offsets=[(candidate["start"], candidate["end"])],
                    confidence=candidate["similarity"],
                    text=candidate["ngram"],
                    page=page_number,
                )
            )
    return entities


@lru_cache(maxsize=1)
def _get_scispacy_model():
    """Lazily load the ``en_core_sci_lg`` pipeline when available."""

    try:
        import spacy  # type: ignore
    except ImportError:  # pragma: no cover
        return None

    model_name = "en_core_sci_lg"
    try:
        return spacy.load(model_name)
    except OSError:  # pragma: no cover - model missing
        LOGGER.warning("scispaCy model '%s' not installed", model_name)
        return None


@lru_cache(maxsize=1)
def _get_scispacy_linker():
    """Add/return the scispaCy entity linker component."""

    nlp = _get_scispacy_model()
    if not nlp:
        return None

    try:
        return nlp.get_pipe("scispacy_linker")
    except Exception:  # pragma: no cover - add pipe once
        try:
            nlp.add_pipe(
                "scispacy_linker",
                config={
                    "resolve_abbreviations": True,
                    "linker_name": "umls",
                },
            )
            return nlp.get_pipe("scispacy_linker")
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Unable to initialise scispaCy linker: %s", exc)
            return None


def _page_cache() -> Dict[str, List[UmlsEntity]]:
    """In-memory cache per process for page-level linking results."""

    if not hasattr(_page_cache, "_store"):
        _page_cache._store = {}  # type: ignore[attr-defined]
    return _page_cache._store  # type: ignore[attr-defined]


__all__ = ["UmlsEntity", "link_umls_entities"]

