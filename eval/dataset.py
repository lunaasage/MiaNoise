"""
RAGAS evaluation dataset for MiaNoise.

15 test cases covering:
  - High-noise nightlife neighborhoods (Wynwood, CBD, Brickell)
  - Moderate mixed neighborhoods (Flagami, Edgewater, Little Havana)
  - Lower-activity residential neighborhoods (Midtown, Coconut Grove)
  - Temporal questions (night vs. day, weekends)
  - Renter decision questions

Ground truth design principle (v2, April 27 2026):
  Ground truths reference only qualitative, reviewable facts — characteristics
  that plausibly appear in Google Places reviews of bars, restaurants, and
  nightclubs. Composite scores are intentionally excluded: they live in our
  metadata layer, not in the review corpus, so including them in ground truths
  caused RAGAS context_recall to penalize the system for a structural mismatch
  rather than a retrieval failure. This revision makes the eval informative.

  See tasks/lessons.md L18 for the full reasoning.
"""

TEST_CASES: list[dict] = [
    # ── High-noise, venue-driven neighborhoods ─────────────────────────────
    {
        "neighborhood": "Wynwood Industrial District",
        "question": "Is Wynwood Industrial District loud at night?",
        "ground_truth": (
            "Wynwood Industrial District is loud at night, driven by bars and nightclubs "
            "that generate amplified music and large outdoor crowds. Venues play music at "
            "high volume, and outdoor patios and gathering areas keep noise levels elevated "
            "well into the late-night hours, especially on Friday and Saturday. Reviews "
            "consistently describe the area as energetic and noisy after dark."
        ),
    },
    {
        "neighborhood": "Wynwood Industrial District",
        "question": "Is Wynwood Industrial District quieter during the day than at night?",
        "ground_truth": (
            "Wynwood Industrial District is noticeably calmer during the day than at night. "
            "The area's noise is driven by its nightlife — bars, clubs, and outdoor venue "
            "spaces — which are largely inactive during daytime hours. Reviews describe a "
            "relaxed daytime atmosphere that transforms into a loud, crowded scene in the "
            "evenings and on weekends."
        ),
    },
    {
        "neighborhood": "CBD",
        "question": "How noisy is the CBD for someone considering living there?",
        "ground_truth": (
            "The CBD is one of Miami's noisiest areas for residents. It has a dense "
            "concentration of bars and restaurants that generate late-night noise, with "
            "reviews documenting loud music and crowds on the sidewalk as late as 2am on "
            "weeknights. Road traffic adds a persistent daytime noise layer. Someone "
            "sensitive to noise would find the CBD environment challenging to live in."
        ),
    },
    {
        "neighborhood": "Brickell Village",
        "question": "What are the noise levels in Brickell Village on weekends?",
        "ground_truth": (
            "Brickell Village gets noticeably louder on weekend nights. Its bars and "
            "late-night venues draw large crowds, and reviews describe high energy and "
            "lively atmospheres at spots like Blackbird Ordinary on Friday and Saturday "
            "evenings. Outdoor seating and street-level activity contribute to elevated "
            "noise that extends into the late-night hours."
        ),
    },
    {
        "neighborhood": "Brickell Village",
        "question": "Is Brickell Village a good place to live for someone who works from home and needs quiet during the day?",
        "ground_truth": (
            "Brickell Village is a mixed environment for daytime quiet. While the loudest "
            "nightlife noise is concentrated in evenings, the neighborhood has active bars "
            "and restaurants whose daytime atmosphere can be lively and social. Some reviews "
            "note a flat or quiet atmosphere at certain venues during off-peak hours, but "
            "the overall commercial activity and traffic make consistent daytime quiet "
            "difficult to count on."
        ),
    },
    # ── Temporal / context-specific ────────────────────────────────────────
    {
        "neighborhood": "Wynwood Industrial District",
        "question": "What makes Wynwood Industrial District noisy — is it traffic or nightlife?",
        "ground_truth": (
            "Wynwood Industrial District's noise comes primarily from nightlife, not traffic. "
            "Bars and nightclubs play amplified music at high volumes, and reviews specifically "
            "call out venues like Oasis Wynwood as 'incredibly loud, way louder than music "
            "needs to be.' Outdoor areas and patios keep crowd noise spilling into the street. "
            "Traffic is a secondary contributor compared to the venue-driven noise."
        ),
    },
    {
        "neighborhood": "Flagami",
        "question": "What types of noise are common in Flagami?",
        "ground_truth": (
            "Flagami's noise comes mainly from restaurants and bars rather than dedicated "
            "nightclubs. Venues like Happy Wine Calle Ocho feature live music on weekends, "
            "creating a vibrant, social atmosphere. The neighborhood has a commercially "
            "active character with music and crowd noise from dining establishments being "
            "the primary sources, alongside general street traffic."
        ),
    },
    # ── Moderate-score residential/mixed neighborhoods ──────────────────────
    {
        "neighborhood": "Edgewater",
        "question": "Is Edgewater a quiet neighborhood compared to Wynwood?",
        "ground_truth": (
            "Edgewater has bar and restaurant activity but lacks the dense nightclub "
            "concentration that defines Wynwood. Venues like Lagniappe draw crowds and "
            "can get busy mid-week through the weekend, but the overall noise character "
            "is more restaurant-and-bar than club-and-late-night. Edgewater has a more "
            "residential feel than Wynwood, though it is not silent."
        ),
    },
    {
        "neighborhood": "East Little Havana",
        "question": "What is the noise situation in East Little Havana?",
        "ground_truth": (
            "East Little Havana has a lively, music-filled atmosphere driven by cafés, "
            "restaurants, and cultural venues. Spots like Cafe La Trova and Odd Birds Miami "
            "host live music and events like rumba nights, generating crowd noise and "
            "amplified music in the evenings. The character is vibrant and cultural rather "
            "than heavy nightclub-driven, with music and street energy being the main sources."
        ),
    },
    {
        "neighborhood": "Design District",
        "question": "Is the Design District noisy?",
        "ground_truth": (
            "The Design District has bar and restaurant noise, particularly in the evenings. "
            "Venues like The Stage draw an eclectic crowd and play hip hop and house music. "
            "The noise character is bar and dining-driven rather than nightclub-heavy, making "
            "it active in the evenings but not as persistently loud as dedicated nightlife "
            "districts. It is more of a dining and arts destination than a late-night scene."
        ),
    },
    # ── Lower-activity / limited-data neighborhoods ─────────────────────────
    {
        "neighborhood": "Midtown",
        "question": "Is Midtown Miami quiet enough for someone sensitive to noise?",
        "ground_truth": (
            "Midtown Miami has fewer late-night nightlife venues than neighborhoods like "
            "Wynwood or Brickell, which limits the most intense noise sources. However, "
            "restaurants and casual dining spots in the area can have lively atmospheres "
            "with background music. The overall character is calmer than Miami's nightlife "
            "cores, though individual venues may still generate some ambient noise."
        ),
    },
    {
        "neighborhood": "Grove Center",
        "question": "Would Grove Center (Coconut Grove) be a good choice for a noise-sensitive renter?",
        "ground_truth": (
            "Grove Center has restaurants and bars that generate some evening noise, and "
            "reviews note that certain spots like Calista Cafe are 'not the quietest given "
            "the location.' The area is commercially active enough that noise-sensitive "
            "renters should be aware of dining and bar noise, though it lacks the dense "
            "late-night club scene that makes areas like Wynwood particularly challenging."
        ),
    },
    # ── Renter decision / comparison questions ──────────────────────────────
    {
        "neighborhood": "Brickell Village",
        "question": "Does noise from Brickell Village's nightlife persist late into the night?",
        "ground_truth": (
            "Yes, noise from Brickell Village's nightlife does persist late into the night. "
            "Reviews describe venues like Blackbird Ordinary as places where 'the energy is "
            "always high' and the atmosphere makes it easy to stay late. Bars and late-night "
            "spots draw crowds on Friday and Saturday evenings, with noise and activity "
            "continuing well into the late-night hours."
        ),
    },
    {
        "neighborhood": "Allapattah Industrial District",
        "question": "Is Allapattah noisy?",
        "ground_truth": (
            "Allapattah Industrial District has a more industrial and commercial character "
            "than a nightlife-driven one. Reviews reference warehouse settings and commercial "
            "truck activity, suggesting that noise here comes more from industrial operations "
            "and traffic than from bars and clubs. It has fewer dedicated nightlife venues "
            "and a quieter evening character than areas like Wynwood or Brickell Village."
        ),
    },
    {
        "neighborhood": "CBD",
        "question": "Is there any time of day when the CBD is relatively quiet?",
        "ground_truth": (
            "The CBD has persistent noise throughout the day and into the late night. "
            "Reviews document loud music and crowds outside bars and restaurants as late "
            "as 2am, even on weeknights. The density of bars, restaurants, and street "
            "activity means noise levels remain elevated during most waking hours. Early "
            "morning, before business and dining activity picks up, is likely the calmest "
            "window."
        ),
    },
]
