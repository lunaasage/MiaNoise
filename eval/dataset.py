"""
RAGAS evaluation dataset for MiaNoise.

15 test cases covering:
  - High-score nightlife neighborhoods (Wynwood, CBD, Brickell)
  - Moderate-score mixed neighborhoods (Flagami, Edgewater, Little Havana)
  - Lower-score residential neighborhoods (Midtown, Coconut Grove)
  - Temporal questions (night vs. day, weekends)
  - Renter decision questions

Ground truths are factual reference answers written from known score data and
Miami neighborhood characteristics. Used by RAGAS context_recall metric to
check whether retrieved chunks contain the facts needed to answer correctly.
"""

TEST_CASES: list[dict] = [
    # ── High-score, venue-driven neighborhoods ─────────────────────────────
    {
        "neighborhood": "Wynwood Industrial District",
        "question": "Is Wynwood Industrial District loud at night?",
        "ground_truth": (
            "Wynwood Industrial District has a composite noise score of 0.52, placing it "
            "among Miami's loudest neighborhoods. Its noise is driven by bars and nightclubs "
            "generating amplified music and outdoor crowd noise, especially on weekend nights. "
            "Nighttime noise is a defining characteristic of this neighborhood."
        ),
    },
    {
        "neighborhood": "Wynwood Industrial District",
        "question": "Is Wynwood Industrial District quieter during the day than at night?",
        "ground_truth": (
            "Wynwood Industrial District's noise is primarily nightlife-driven, so daytime "
            "hours are generally calmer than evenings and weekends. Daytime noise is mainly "
            "from traffic and commercial activity rather than music and crowds."
        ),
    },
    {
        "neighborhood": "CBD",
        "question": "How noisy is the CBD for someone considering living there?",
        "ground_truth": (
            "The CBD has a composite noise score of 0.70, the highest among all Miami "
            "neighborhoods, driven by dense road traffic and a high concentration of bars "
            "and restaurants. Noise is elevated throughout the day and evening. "
            "Noise-sensitive residents would find the environment demanding."
        ),
    },
    {
        "neighborhood": "Brickell Village",
        "question": "What are the noise levels in Brickell Village on weekends?",
        "ground_truth": (
            "Brickell Village has a composite noise score of 0.52, driven by bars and "
            "restaurants. Weekend nights see elevated noise from nightlife activity, outdoor "
            "crowds, and venues with live music or outdoor seating on Friday and Saturday "
            "evenings."
        ),
    },
    {
        "neighborhood": "Brickell Village",
        "question": "Is Brickell Village a good place to live for someone who works from home and needs quiet during the day?",
        "ground_truth": (
            "Brickell Village has elevated noise levels from both daytime traffic and evening "
            "nightlife. While daytime noise from bars and clubs is lower than at night, road "
            "traffic and commercial activity persist throughout the day. It may not be ideal "
            "for those requiring a quiet work-from-home environment."
        ),
    },
    # ── Temporal / context-specific ────────────────────────────────────────
    {
        "neighborhood": "Wynwood Industrial District",
        "question": "What makes Wynwood Industrial District noisy — is it traffic or nightlife?",
        "ground_truth": (
            "Wynwood Industrial District's noise is primarily nightlife-driven: bars, "
            "nightclubs, and outdoor venue areas generate amplified music and crowd noise, "
            "especially on weekends. Road traffic plays a secondary role compared to the "
            "venue-driven noise from its dense concentration of late-night establishments."
        ),
    },
    {
        "neighborhood": "Flagami",
        "question": "What types of noise are common in Flagami?",
        "ground_truth": (
            "Flagami has a moderate-to-high composite noise score. Noise in Flagami comes "
            "from a mix of road traffic, restaurants, and bars. It is a commercially active "
            "neighborhood with more daytime activity than pure nightlife districts."
        ),
    },
    # ── Moderate-score residential/mixed neighborhoods ──────────────────────
    {
        "neighborhood": "Edgewater",
        "question": "Is Edgewater a quiet neighborhood compared to Wynwood?",
        "ground_truth": (
            "Edgewater is generally quieter than Wynwood Industrial District. While Edgewater "
            "has waterfront restaurants and some bar activity, it lacks the dense nightclub "
            "concentration that drives Wynwood's noise. It is a more residential neighborhood "
            "with moderate noise levels."
        ),
    },
    {
        "neighborhood": "Little Havana",
        "question": "What is the noise situation in Little Havana?",
        "ground_truth": (
            "Little Havana has moderate noise levels driven by street activity, restaurants, "
            "and cultural venues. It is a vibrant neighborhood but does not have the heavy "
            "nightclub concentration found in areas like Wynwood or Brickell Village. "
            "Daytime street noise and music from cafés and restaurants are common."
        ),
    },
    {
        "neighborhood": "Design District",
        "question": "Is the Design District noisy?",
        "ground_truth": (
            "The Design District has noise from upscale retail, restaurants, and bars, but "
            "it is less nightlife-heavy than Wynwood or Brickell. Evening restaurant and "
            "bar noise is the primary source of disturbance, though the area is generally "
            "more moderate in noise levels than Miami's loudest nightlife districts."
        ),
    },
    # ── Lower-score / limited-data neighborhoods ────────────────────────────
    {
        "neighborhood": "Midtown",
        "question": "Is Midtown Miami quiet enough for someone sensitive to noise?",
        "ground_truth": (
            "Midtown has a composite noise score of 0.04, among the lowest in Miami, "
            "reflecting few mapped nightlife venues and minimal noise complaints. "
            "Limited venue and complaint data indicates a calmer residential character. "
            "Some traffic and construction noise may be present, but it ranks as one of "
            "Miami's quieter neighborhoods overall."
        ),
    },
    {
        "neighborhood": "Coconut Grove",
        "question": "Would Coconut Grove be a good choice for a noise-sensitive renter?",
        "ground_truth": (
            "Coconut Grove has a more residential and tree-lined character than Miami's "
            "downtown neighborhoods. While the village center has restaurants and bars, "
            "the surrounding residential areas are quieter. It is generally a better choice "
            "for noise-sensitive renters than high-score areas like the CBD or Wynwood."
        ),
    },
    # ── Renter decision / comparison questions ──────────────────────────────
    {
        "neighborhood": "Brickell Village",
        "question": "Does noise from Brickell Village's nightlife persist late into the night?",
        "ground_truth": (
            "Brickell Village has a composite noise score of 0.52 driven by bars and "
            "restaurants. Venue noise, outdoor crowds, and music from nightlife establishments "
            "are documented in reviews, particularly on weekend evenings. Noise from these "
            "venues can extend into late-night hours on Fridays and Saturdays."
        ),
    },
    {
        "neighborhood": "Allapattah",
        "question": "Is Allapattah a noisy neighborhood?",
        "ground_truth": (
            "Allapattah has moderate noise levels compared to Miami's nightlife districts. "
            "It is an emerging neighborhood with commercial activity and road traffic as "
            "the primary noise sources. It has fewer dedicated nightlife venues than areas "
            "like Wynwood or Brickell Village."
        ),
    },
    {
        "neighborhood": "CBD",
        "question": "Is there any time of day when the CBD is relatively quiet?",
        "ground_truth": (
            "The CBD has Miami's highest composite noise score and is active throughout "
            "the day and night. Early morning hours before business activity picks up may "
            "be the quietest periods. Road traffic, bars, and restaurants keep noise levels "
            "elevated during most waking hours."
        ),
    },
]
