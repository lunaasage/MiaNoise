"""
MiaNoise — Streamlit dashboard
Four tabs: Map · Neighborhood Profiles · Compare & Temporal · Chat with MiaNoise

Run from the project root:
    streamlit run ui/app.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=False), override=True)

import streamlit as st
from streamlit_folium import st_folium
from shapely.geometry import Point

from ingestion.db import (
    load_latest_scores,
    load_neighborhood_geodataframe,
    load_profile,
    load_all_profiles,
    load_neighborhood_reviews,
)
from ui.map_builder import build_map
from agent.executor import get_agent, ask


st.set_page_config(
    page_title="MiaNoise — Miami Noise Intelligence",
    page_icon="🔊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Cached loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def _scores():
    return load_latest_scores()

@st.cache_data(ttl=86400)
def _gdf():
    return load_neighborhood_geodataframe()

@st.cache_data(ttl=300)
def _profile(name: str):
    return load_profile(name)

@st.cache_data(ttl=3600)
def _all_profiles():
    return load_all_profiles()

@st.cache_data(ttl=3600)
def _reviews(name: str):
    return load_neighborhood_reviews(name)

@st.cache_resource
def _agent():
    return get_agent()


# ── Session state ──────────────────────────────────────────────────────────────

if "selected" not in st.session_state:
    st.session_state.selected = None
if "messages" not in st.session_state:
    st.session_state.messages = []       # display messages [{role, content}]
if "agent_history" not in st.session_state:
    st.session_state.agent_history = []  # LangChain message objects for multi-turn context
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None  # user message waiting for agent response


# ── Shared data ────────────────────────────────────────────────────────────────

with st.spinner("Loading neighborhood data…"):
    scores = _scores()
    gdf = _gdf().copy()
    raw_profiles = _all_profiles()

gdf["composite_score"] = gdf["name"].map(scores).fillna(0.0)

profile_data = sorted(
    [
        {
            "name": p["neighborhood_name"],
            "profile_text": p["profile_text"],
            "score": scores.get(p["neighborhood_name"], 0.0),
        }
        for p in raw_profiles
    ],
    key=lambda x: x["score"],
    reverse=True,
)
profile_names = [p["name"] for p in profile_data]


# ── Helpers ────────────────────────────────────────────────────────────────────

def noise_label(score: float) -> str:
    if score > 0.75:
        return "Very Loud"
    if score > 0.5:
        return "Loud"
    if score > 0.25:
        return "Moderate"
    return "Quiet"

def noise_badge(score: float) -> str:
    return {"Very Loud": "🔴", "Loud": "🟠", "Moderate": "🟡", "Quiet": "🟢"}[noise_label(score)]

NOISE_RELEVANCE_KW = [
    "loud", "noise", "noisy", "quiet", "sound", "music",
    "crowd", "crowded", "packed", "busy", "lively", "energetic",
    "blasting", "vibrat", "bass", "party", "club", "bar scene",
    "rowdy", "chaotic", "peaceful", "serene", "atmosphere",
    "volume", "speaker", "dj", "live music", "drunk", "bouncer",
    "late night", "nightlife", "disturb", "sleep",
]
WEEKEND_NIGHT_KW = [
    "weekend", "friday", "saturday", "sunday",
    "night", "late night", "late at night", "midnight",
    "1am", "2am", "3am", "4am", "evening", "after dark",
]
WEEKDAY_DAY_KW = [
    "weekday", "monday", "tuesday", "wednesday", "thursday",
    "morning", "daytime", "during the day", "afternoon",
    "lunch", "business hour",
]

def is_noise_relevant(text: str) -> bool:
    """Return True only if the review mentions noise/atmosphere signals."""
    tl = text.lower()
    return any(k in tl for k in NOISE_RELEVANCE_KW)

def split_temporal(texts: list[str]) -> tuple[list[str], list[str]]:
    wn, wd = [], []
    for t in texts:
        if not is_noise_relevant(t):
            continue
        tl = t.lower()
        if any(k in tl for k in WEEKEND_NIGHT_KW):
            wn.append(t)
        if any(k in tl for k in WEEKDAY_DAY_KW):
            wd.append(t)
    return wn, wd


# ── Header ─────────────────────────────────────────────────────────────────────

st.title("MiaNoise")
st.caption("Miami neighborhood noise intelligence for renters.")

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_map, tab_profiles, tab_compare, tab_chat = st.tabs([
    "Map",
    "Neighborhood Profiles",
    "Compare & Temporal",
    "Chat with MiaNoise",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MAP
# ══════════════════════════════════════════════════════════════════════════════

with tab_map:
    col_map, col_info = st.columns([3, 2], gap="large")

    with col_map:
        m = build_map(gdf)
        map_data = st_folium(m, use_container_width=True, height=540)

        clicked = map_data.get("last_clicked") if map_data else None
        if clicked:
            pt = Point(clicked["lng"], clicked["lat"])
            matches = gdf[gdf.geometry.contains(pt)]
            if not matches.empty:
                st.session_state.selected = matches.iloc[0]["name"]

    with col_info:
        selected = st.session_state.selected

        if selected:
            hdr, clear_btn = st.columns([4, 1])
            with hdr:
                st.subheader(selected)
            with clear_btn:
                if st.button("✕", help="Clear selection", key="clear_map"):
                    st.session_state.selected = None
                    st.rerun()

            score = scores.get(selected, 0.0)
            st.metric("Noise Score", f"{score:.0%}")
            st.caption(f"{noise_badge(score)} {noise_label(score)}")

            with st.spinner("Loading profile…"):
                profile = _profile(selected)
            if profile:
                st.markdown(profile)
            else:
                st.info("No profile available for this neighborhood yet.")

        else:
            st.markdown("#### Select a neighborhood")
            st.markdown("Hover to see the noise score. Click to read the AI-generated noise profile.")

            if scores:
                st.markdown("---")
                st.caption("**Loudest neighborhoods**")
                top5 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
                for name, s in top5:
                    if st.button(
                        f"{noise_badge(s)} {name}  —  {s:.0%}",
                        key=f"quick_{name}",
                        use_container_width=True,
                    ):
                        st.session_state.selected = name
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — NEIGHBORHOOD PROFILES
# ══════════════════════════════════════════════════════════════════════════════

with tab_profiles:
    st.subheader(f"Neighborhood Profiles — {len(profile_data)} neighborhoods")

    search_col, filter_col, sort_col = st.columns([3, 2, 2])
    with search_col:
        search = st.text_input(
            "Search", placeholder="Search by name…", label_visibility="collapsed"
        )
    with filter_col:
        level_filter = st.selectbox(
            "Noise level",
            ["All levels", "Quiet (0–25%)", "Moderate (25–50%)", "Loud (50–75%)", "Very Loud (75–100%)"],
            label_visibility="collapsed",
        )
    with sort_col:
        sort_by = st.selectbox(
            "Sort",
            ["Loudest first", "Quietest first", "A → Z"],
            label_visibility="collapsed",
        )

    filtered = profile_data
    if search:
        filtered = [p for p in filtered if search.lower() in p["name"].lower()]
    if level_filter != "All levels":
        bounds = {
            "Quiet (0–25%)":          (0.0,  0.25),
            "Moderate (25–50%)":      (0.25, 0.5),
            "Loud (50–75%)":          (0.5,  0.75),
            "Very Loud (75–100%)":    (0.75, 1.01),
        }
        lo, hi = bounds[level_filter]
        filtered = [p for p in filtered if lo <= p["score"] < hi]
    if sort_by == "Quietest first":
        filtered = sorted(filtered, key=lambda x: x["score"])
    elif sort_by == "A → Z":
        filtered = sorted(filtered, key=lambda x: x["name"])

    st.caption(f"Showing {len(filtered)} of {len(profile_data)} neighborhoods")
    st.divider()

    if not filtered:
        st.info("No neighborhoods match your filters.")
    else:
        for p in filtered:
            s = p["score"]
            with st.expander(
                f"{noise_badge(s)} **{p['name']}** — {s:.0%} · {noise_label(s)}"
            ):
                st.markdown(p["profile_text"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — COMPARE & TEMPORAL
# ══════════════════════════════════════════════════════════════════════════════

with tab_compare:
    st.subheader("Compare Neighborhoods")
    st.caption("Select two neighborhoods to compare noise profiles and temporal patterns.")

    drop_a, drop_b = st.columns(2)
    with drop_a:
        nbhd_a = st.selectbox("Neighborhood A", ["— select —"] + profile_names, key="cmp_a")
    with drop_b:
        nbhd_b = st.selectbox("Neighborhood B", ["— select —"] + profile_names, key="cmp_b")

    if nbhd_a == "— select —" or nbhd_b == "— select —":
        st.info("Select both neighborhoods above to see the comparison.")
    elif nbhd_a == nbhd_b:
        st.warning("Select two different neighborhoods.")
    else:
        # ── Noise profiles side by side ────────────────────────────────────
        st.divider()
        st.markdown("#### Noise Profiles")
        prof_a, prof_b = st.columns(2)

        for col, name in [(prof_a, nbhd_a), (prof_b, nbhd_b)]:
            s = scores.get(name, 0.0)
            with col:
                st.markdown(f"**{name}**")
                st.metric("Noise Score", f"{s:.0%}")
                st.caption(f"{noise_badge(s)} {noise_label(s)}")
                p = _profile(name)
                if p:
                    st.markdown(p)
                else:
                    st.info("No profile available.")

        # ── Temporal patterns ──────────────────────────────────────────────
        st.divider()
        st.markdown("#### Temporal Patterns")
        st.caption(
            "Reviews classified by time-of-day and day-of-week keywords found in review text. "
            "Full hourly and weekday vs. weekend time-series charts will appear here once "
            "time-stamped complaint data and hourly traffic data are available in the production version."
        )

        with st.spinner("Loading reviews…"):
            rev_a = _reviews(nbhd_a)
            rev_b = _reviews(nbhd_b)

        wn_a, wd_a = split_temporal(rev_a)
        wn_b, wd_b = split_temporal(rev_b)

        temp_a, temp_b = st.columns(2)

        for col, name, wn, wd, total in [
            (temp_a, nbhd_a, wn_a, wd_a, len(rev_a)),
            (temp_b, nbhd_b, wn_b, wd_b, len(rev_b)),
        ]:
            with col:
                st.markdown(f"**{name}**")
                st.caption(f"{total} reviews total")

                st.markdown("**Weekend / Night mentions**")
                if wn:
                    st.metric("Reviews", len(wn), help="Reviews mentioning weekends or nighttime")
                    for excerpt in wn[:3]:
                        st.markdown(
                            f"> _{excerpt[:220]}{'…' if len(excerpt) > 220 else ''}_"
                        )
                else:
                    st.caption("No weekend/night mentions found in reviews.")

                st.markdown("**Weekday / Daytime mentions**")
                if wd:
                    st.metric("Reviews", len(wd), help="Reviews mentioning weekdays or daytime")
                    for excerpt in wd[:3]:
                        st.markdown(
                            f"> _{excerpt[:220]}{'…' if len(excerpt) > 220 else ''}_"
                        )
                else:
                    st.caption("No weekday/daytime mentions found in reviews.")

        # Placeholder for production charts
        with st.expander("Hourly & daily noise charts — coming in production version"):
            st.info(
                "Once the full version integrates hourly traffic data (TomTom), construction "
                "permits, and time-stamped 311 complaint data, this section will show:\n\n"
                "- Average noise score by hour of day (Mon–Fri vs. Sat–Sun)\n"
                "- Complaint frequency heatmap by day and time\n"
                "- ML-identified peak noise windows per neighborhood\n"
                "- Block-level granularity once tract/block-level data is available"
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — CHAT WITH MIANOISE
# ══════════════════════════════════════════════════════════════════════════════

with tab_chat:
    st.subheader("Chat with MiaNoise")
    st.caption(
        'e.g. "Find me a quiet neighborhood near Brickell"  ·  '
        '"Which areas have the most nightlife noise?"  ·  '
        '"Is Wynwood loud on weekdays?"'
    )

    # Input at the top — always visible, never scrolls away
    with st.form("chat_form", clear_on_submit=True):
        col_input, col_btn = st.columns([5, 1])
        with col_input:
            user_input = st.text_input(
                "",
                placeholder="Ask about noise levels in any Miami neighborhood…",
                label_visibility="collapsed",
            )
        with col_btn:
            submitted = st.form_submit_button("Send", use_container_width=True)

    if submitted and user_input.strip():
        prompt = user_input.strip()
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.pending_prompt = prompt
        st.rerun()  # rerun immediately so user message renders before generation starts

    # Messages below the input box
    st.divider()
    if not st.session_state.messages and not st.session_state.pending_prompt:
        st.caption("Your conversation will appear here.")
    else:
        # Render history first (reversed = newest at top) so user message is always visible
        for msg in reversed(st.session_state.messages):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Then generate response below the user message
        if st.session_state.pending_prompt:
            pending = st.session_state.pending_prompt
            st.session_state.pending_prompt = None
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    agent = _agent()
                    response, updated_history = ask(
                        agent, pending, st.session_state.agent_history
                    )
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.session_state.agent_history = updated_history
            st.rerun()
