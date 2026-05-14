from .base import NeighborhoodScore, NoiseSource


class YelpReviews(NoiseSource):
    """Yelp Fusion API — business review text for RAG corpus; noise signal from review sentiment."""

    source_id = "yelp_reviews"
    source_role = "corpus"
    required_env_vars = ["YELP_API_KEY"]

    def fetch(self) -> list[NeighborhoodScore]:
        # Sprint 2: fetch reviews for businesses near each neighborhood, store raw text
        # in Supabase for RAG ingestion. Score is 0 here (weight=0); real value is in
        # the text chunks passed to the embedding pipeline.
        raise NotImplementedError("yelp_reviews.fetch — implement in Sprint 2")
