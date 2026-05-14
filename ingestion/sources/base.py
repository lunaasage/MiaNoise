from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar
import logging
import os

logger = logging.getLogger(__name__)


@dataclass
class CorpusDocument:
    """A single text document for the RAG corpus. Returned by corpus sources."""
    neighborhood: str
    source_id: str
    content: str           # raw review/post text for embedding
    author: str = ""
    external_url: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class NeighborhoodScore:
    neighborhood: str
    normalized_score: float  # 0.0–1.0
    raw_value: float
    source_id: str
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.normalized_score <= 1.0:
            raise ValueError(
                f"normalized_score must be in [0, 1], got {self.normalized_score}"
            )


class NoiseSource(ABC):
    """
    Abstract base for all noise data sources.

    source_role determines how the pipeline uses a source's output:
      "scoring" — output goes to score_engine → composite noise score
      "corpus"  — output goes to the RAG corpus (reviews/embeddings tables)
      "both"    — output goes to both pipelines

    Subclasses set source_id, source_role, weight (scoring only), and
    required_env_vars. The pipeline calls fetch_safe(), which handles
    availability checks and runtime errors so a broken source never
    takes down the pipeline.

    To add a new source:
      1. Create ingestion/sources/<name>.py
      2. Subclass NoiseSource, set source_id / source_role / weight / required_env_vars
      3. Implement fetch() — return one NeighborhoodScore per neighborhood
      4. Add the class to ALL_SOURCES in ingestion/sources/__init__.py
    """

    source_id: ClassVar[str]
    source_role: ClassVar[str] = "scoring"  # "scoring" | "corpus" | "both"
    weight: ClassVar[float] = 1.0           # only meaningful for scoring/both sources
    required_env_vars: ClassVar[list[str]] = []

    def is_available(self) -> bool:
        """Return True if all required env vars are present."""
        missing = [v for v in self.required_env_vars if not os.getenv(v)]
        if missing:
            logger.debug(
                "%s unavailable — missing env vars: %s", self.source_id, missing
            )
            return False
        return True

    @abstractmethod
    def fetch(self) -> list[NeighborhoodScore] | list[CorpusDocument]:
        """
        Fetch noise data. Scoring sources return list[NeighborhoodScore];
        corpus sources return list[CorpusDocument].
        """
        ...

    def fetch_safe(self) -> list[NeighborhoodScore] | list[CorpusDocument] | None:
        """
        Pipeline entry point. Returns None when the source is unavailable.
        Re-raises NotImplementedError so unfinished stubs fail loudly in dev.
        Catches all other exceptions so one bad source never crashes a run.
        """
        if not self.is_available():
            return None
        try:
            return self.fetch()
        except NotImplementedError:
            raise
        except Exception as exc:
            logger.warning("%s fetch failed: %s", self.source_id, exc, exc_info=True)
            return None
