"""UMLS entity linking via scispaCy with optional QuickUMLS support."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Dict, Iterable, List, Literal, MutableMapping, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from medparse.utils.log import get_logger
from medparse.ingest.models import PageData

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


class UmlsLinkingResult(BaseModel):
    """Result wrapper exposing entities plus runtime status."""

    entities: List[UmlsEntity] = Field(default_factory=list)
    status: Literal["linked", "skipped_model_missing", "skipped_disabled", "skipped_no_input"]
    model_name: Optional[str] = None


def link_umls_entities(
    page_texts: Sequence[Tuple[int, str]],
    *,
    quickumls_path: Optional[str] = None,
    min_confidence: float = 0.85,
    enabled: bool = True,
    cache: Optional[MutableMapping[str, List[UmlsEntity]]] = None,
) -> UmlsLinkingResult:
    """Link entities for ``page_texts`` returning a status-aware result."""

    if not enabled:
        return UmlsLinkingResult(status="skipped_disabled")

    if not page_texts:
        return UmlsLinkingResult(status="skipped_no_input")

    linker = _get_scispacy_linker()
    model = _get_scispacy_model()
    if not linker or not model:
        LOGGER.warning("UMLS linking skipped: scispaCy linker unavailable")
        return UmlsLinkingResult(status="skipped_model_missing")

    entities: List[UmlsEntity] = []
    per_page_counts: Dict[int, int] = {}
    page_cache = cache if cache is not None else _page_cache()

    max_entities_per_page = 200
    for page_number, text in page_texts:
        if not text or len(text) < 16:
            continue

        page_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()
        cached = page_cache.get(page_hash)
        if cached is None:
            cached = _link_page_text(linker, text, min_confidence=min_confidence)
            page_cache[page_hash] = cached

        ranked = sorted(cached, key=lambda entry: entry.confidence, reverse=True)
        for entity in ranked:
            count = per_page_counts.get(page_number, 0)
            if count >= max_entities_per_page:
                break
            entities.append(
                UmlsEntity(
                    cui=entity.cui,
                    preferred_term=entity.preferred_term,
                    semtypes=list(entity.semtypes),
                    offsets=list(entity.offsets),
                    confidence=entity.confidence,
                    text=(entity.text[:80] if entity.text else entity.text),
                    page=page_number,
                )
            )
            per_page_counts[page_number] = count + 1

    if quickumls_path:
        for quick_entity in _quickumls_link(page_texts, quickumls_path):
            page_number = quick_entity.page or -1
            count = per_page_counts.get(page_number, 0)
            if count >= max_entities_per_page:
                continue
            quick_entity.text = (quick_entity.text or "")[:80]
            entities.append(quick_entity)
            per_page_counts[page_number] = count + 1

    return UmlsLinkingResult(
        entities=entities,
        status="linked",
        model_name=getattr(model, "meta", {}).get("name", "en_core_sci_lg"),
    )


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
                    text=candidate["ngram"][:80],
                    page=page_number,
                )
            )
    return entities


@lru_cache(maxsize=1)
def _get_scispacy_model(preferred_models: Optional[List[str]] = None):
    """Lazily load a scispaCy pipeline, trying preferred models first.

    Args:
        preferred_models: List of model names to try in order.
                         Defaults to ["en_core_sci_lg", "en_core_sci_md", "en_core_sci_sm"]

    Returns:
        Loaded spaCy model or None if no models available
    """

    try:
        import spacy  # type: ignore
    except ImportError:  # pragma: no cover
        return None

    if preferred_models is None:
        preferred_models = ["en_core_sci_lg", "en_core_sci_md", "en_core_sci_sm"]

    for model_name in preferred_models:
        try:
            nlp = spacy.load(model_name)
            LOGGER.info("Loaded scispaCy model: %s (version %s)",
                       model_name, nlp.meta.get("version", "unknown"))
            return nlp
        except OSError:  # Model not installed
            LOGGER.debug("scispaCy model '%s' not available, trying next...", model_name)
            continue

    # No models available
    LOGGER.warning(
        "UMLS linking disabled: no scispaCy models found. "
        "Install with: pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz"
    )
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


def link_entities(
    pages: Sequence[PageData],
    *,
    quickumls_path: Optional[str] = None,
    min_confidence: float = 0.85,
    enabled: bool = True,
    cache: Optional[MutableMapping[str, List[UmlsEntity]]] = None,
) -> UmlsLinkingResult:
    """Convenience wrapper that accepts ``PageData`` objects."""

    page_texts: List[Tuple[int, str]] = []
    for page in pages:
        text = page.text or ""
        if not text.strip():
            continue
        page_texts.append((page.number, text))

    return link_umls_entities(
        page_texts,
        quickumls_path=quickumls_path,
        min_confidence=min_confidence,
        enabled=enabled,
        cache=cache,
    )


__all__ = ["UmlsEntity", "UmlsLinkingResult", "link_entities", "link_umls_entities"]
