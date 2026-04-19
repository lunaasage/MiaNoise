# MiaNoise — Sprint 2 TODO

**Sprint:** 2 — RAG Pipeline  
**Status:** CURRENT  
**Goal:** Given a neighborhood name, generate a natural-language noise profile grounded in review text.

---

## Tasks

- [ ] **2.1** Implement `yelp_reviews.fetch()` — pull business review text for bars/nightclubs/restaurants near each neighborhood centroid; store raw text in Supabase `reviews` table
- [ ] **2.2** Implement `reddit_posts.fetch()` — search r/miami and r/MiamiBeach for noise-related posts mentioning neighborhood names; store in `reviews` table
- [ ] **2.3** Chunking + embedding — split review text into ~512-token chunks, embed with `text-embedding-3-small`, store vectors in `embeddings` table
- [ ] **2.4** Retrieval function — given a neighborhood name + query, retrieve top-k relevant chunks from `embeddings` via pgvector cosine similarity
- [ ] **2.5** Profile synthesis — LLM call (claude-sonnet) with retrieved chunks + composite score as context → generate neighborhood noise profile narrative
- [ ] **2.6** End-to-end test — call profile synthesis for Wynwood; verify output is grounded, specific, and matches the North Star description

---

## Open Questions Before Starting

- How many Yelp reviews can we pull per neighborhood before hitting the Fusion API quota?
- Reddit: do r/miami posts actually mention neighborhood names explicitly, or do they use street names/landmarks? Need to sample before building the retrieval logic.
- Chunking strategy: fixed 512-token windows vs. sentence-boundary chunking — which is better for this content type?
