from .base import NeighborhoodScore, NoiseSource


class RedditPosts(NoiseSource):
    """Reddit PRAW — r/miami and r/MiamiBeach noise anecdotes for RAG corpus."""

    source_id = "reddit_posts"
    source_role = "corpus"
    required_env_vars = [
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USER_AGENT",
    ]

    def fetch(self) -> list[NeighborhoodScore]:
        # Sprint 2: search r/miami and r/MiamiBeach for noise-related posts, extract text,
        # tag by mentioned neighborhood, store in Supabase for RAG ingestion.
        raise NotImplementedError("reddit_posts.fetch — implement in Sprint 2")
