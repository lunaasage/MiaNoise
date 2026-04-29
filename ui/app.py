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
)
from ui.map_builder import build_map
from agent.executor import get_agent, ask


st.set_page_config(
    page_title="MiaNoise — Miami Noise Intelligence",
    page_icon="🔊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Brand styles ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* ── Fonts ── */
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

  /* ── Global typography ── */
  html, body, .stApp, .stApp * { font-family: 'Inter', sans-serif; }
  .stApp h1, .stApp h2, .stApp h3,
  .stApp .stSubheader, [data-testid="stHeadingWithActionElements"] * {
    font-family: 'Space Grotesk', sans-serif !important;
    color: #EDE8D8 !important;
  }

  /* ── App chrome ── */
  .block-container { padding-top: 0.75rem !important; }
  hr { border-color: rgba(255,255,255,0.08) !important; }
  .stCaption, [data-testid="stCaptionContainer"] { color: #8892A4 !important; }

  /* ── Tabs ── */
  [data-baseweb="tab-list"] { border-bottom: 1px solid rgba(255,255,255,0.08) !important; }
  [data-baseweb="tab"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
    color: #8892A4 !important;
    background: transparent !important;
  }
  [data-baseweb="tab"][aria-selected="true"] {
    color: #00CEC9 !important;
    border-bottom: 2px solid #00CEC9 !important;
  }
  [data-baseweb="tab-highlight"] { background: #00CEC9 !important; }

  /* ── Score metrics (JetBrains Mono) ── */
  [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
  }

  /* ── Buttons ── */
  .stButton > button {
    font-family: 'Inter', sans-serif !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    background: rgba(255,255,255,0.04) !important;
    color: #EDE8D8 !important;
  }
  .stButton > button:hover {
    border-color: #00CEC9 !important;
    color: #00CEC9 !important;
    background: rgba(0,206,201,0.06) !important;
  }

  /* ── Chat: form send button ── */
  .stFormSubmitButton > button {
    background: #FF4F44 !important;
    border: none !important;
    color: #fff !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    border-radius: 6px !important;
  }
  .stFormSubmitButton > button:hover {
    background: #CC3F35 !important;
    border: none !important;
    color: #fff !important;
  }

  /* ── Chat: text input ── */
  [data-testid="stChatTab"] .stTextInput > div > div > input,
  .chat-input-area .stTextInput > div > div > input,
  section[data-testid="stForm"] input[type="text"] {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #EDE8D8 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
    border-radius: 6px !important;
  }
  section[data-testid="stForm"] input[type="text"]:focus {
    border-color: #00CEC9 !important;
    box-shadow: 0 0 0 1px #00CEC9 !important;
  }

  /* ── Expanders ── */
  [data-testid="stExpander"] summary {
    font-family: 'Inter', sans-serif !important;
    color: #EDE8D8 !important;
  }
  [data-testid="stExpander"] {
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
  }

  /* ── Selectbox / text inputs ── */
  [data-baseweb="select"] * { font-family: 'Inter', sans-serif !important; }
  [data-testid="stTextInput"] input { color: #EDE8D8 !important; }
</style>
<div style="
    height: 5px;
    background: linear-gradient(90deg, #00CEC9 0%, #FF4F44 100%);
    width: 100%;
    margin-bottom: 12px;
"></div>
""", unsafe_allow_html=True)

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



# ── Header ─────────────────────────────────────────────────────────────────────

st.image(str(Path(__file__).parent / "logo.png"), width=300)

# Waveform accent — sine wave + EKG spike, cyan→coral gradient (brand book §05)
st.markdown("""
<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="36"
     viewBox="0 0 1400 36" preserveAspectRatio="none"
     style="display:block; margin: -4px 0 12px 0;">
  <defs>
    <linearGradient id="wg" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%"   stop-color="#00CEC9"/>
      <stop offset="100%" stop-color="#FF4F44"/>
    </linearGradient>
  </defs>
  <path fill="none" stroke="url(#wg)" stroke-width="2" opacity="0.55"
    d="M0,18
       C 25,18 37,6  50,6  C 63,6  75,18 100,18
       C125,18 137,30 150,30 C163,30 175,18 200,18
       C225,18 237,6  250,6  C263,6  275,18 300,18
       C325,18 337,30 350,30 C363,30 375,18 400,18
       C425,18 437,6  450,6  C463,6  475,18 500,18
       C525,18 537,30 550,30 C563,30 575,18 600,18
       L 625,18 L 638,2 L 648,34 L 658,18 L 680,18
       C705,18 717,6  730,6  C743,6  755,18 780,18
       C805,18 817,30 830,30 C843,30 855,18 880,18
       C905,18 917,6  930,6  C943,6  955,18 980,18
       C1005,18 1017,30 1030,30 C1043,30 1055,18 1080,18
       C1105,18 1117,6  1130,6  C1143,6  1155,18 1180,18
       C1205,18 1217,30 1230,30 C1243,30 1255,18 1280,18
       C1305,18 1317,6  1330,6  C1343,6  1355,18 1380,18 L1400,18"/>
</svg>
""", unsafe_allow_html=True)

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
        map_data = st_folium(m, use_container_width=True, height=540, key="main_map")

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

        # ── Full-version placeholders ──────────────────────────────────────
        st.divider()
        st.markdown("#### Temporal Patterns — Full Version")
        st.info(
            "**Coming in the full version.** "
            "Once we integrate time-stamped data sources, this section will show side-by-side:\n\n"
            "- **Weekday vs. weekend noise score** — avg. composite score Mon–Thu vs. Fri–Sun\n"
            "- **Hour-of-day breakdown** — peak noise windows per neighborhood (requires TomTom hourly traffic + 311 complaint timestamps)\n"
            "- **Complaint frequency heatmap** — day × hour grid for each neighborhood\n\n"
            "_Data sources required: TomTom Traffic API (hourly), City of Miami 311 with timestamp resolution, construction permit dates._"
        )

        st.divider()
        st.markdown("#### Block-Level Granularity — Full Version")
        st.info(
            "**Coming in the full version.** "
            "Current scores are at the neighborhood polygon level. "
            "Block-level scoring will break each neighborhood into census tracts or city blocks, "
            "letting renters compare a quiet block inside a loud neighborhood vs. a loud block inside a quieter one.\n\n"
            "_Requires: TomTom segment-level traffic, block-level 311 complaint mapping, OSM building footprints._"
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — CHAT WITH MIANOISE
# ══════════════════════════════════════════════════════════════════════════════

def _chat_bubble(role: str, content: str) -> str:
    """Render a branded chat message bubble as HTML."""
    import re
    # Convert **bold** to <strong> with cream color
    html_body = re.sub(
        r'\*\*(.+?)\*\*',
        r'<strong style="color:#EDE8D8">\1</strong>',
        content,
    )
    html_body = html_body.replace("\n", "<br>")

    if role == "user":
        return (
            '<div style="display:flex;flex-direction:column;align-items:flex-end;margin-bottom:8px;">'
            '<div style="max-width:75%;padding:10px 14px;'
            'background:rgba(255,79,68,0.12);'
            'border-radius:8px 8px 2px 8px;'
            'border-right:2px solid #FF4F44;">'
            '<div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;'
            'color:#8892A4;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;">You</div>'
            f'<div style="font-family:\'Inter\',sans-serif;font-size:13px;line-height:21px;color:#EDE8D8;">{html_body}</div>'
            '</div></div>'
        )
    return (
        '<div style="display:flex;flex-direction:column;align-items:flex-start;margin-bottom:8px;">'
        '<div style="max-width:75%;padding:10px 14px;'
        'background:rgba(22,40,68,0.8);'
        'border-radius:8px 8px 8px 2px;'
        'border-left:2px solid #00CEC9;">'
        '<div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;'
        'color:#8892A4;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;">MiaNoise</div>'
        f'<div style="font-family:\'Inter\',sans-serif;font-size:13px;line-height:21px;color:#8892A4;">{html_body}</div>'
        '</div></div>'
    )

_THINKING_HTML = (
    '<div style="display:flex;flex-direction:column;align-items:flex-start;margin-bottom:8px;">'
    '<div style="padding:10px 14px;'
    'background:rgba(22,40,68,0.6);'
    'border-radius:8px 8px 8px 2px;'
    'border-left:2px solid #00CEC9;">'
    '<div style="font-family:\'JetBrains Mono\',monospace;font-size:10px;'
    'color:#8892A4;text-transform:uppercase;letter-spacing:.08em;">Thinking…</div>'
    '</div></div>'
)

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
    st.markdown(
        '<div style="height:1px;background:rgba(255,255,255,0.08);margin:8px 0 12px;"></div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.messages and not st.session_state.pending_prompt:
        st.markdown(
            '<p style="font-family:Inter,sans-serif;font-size:12px;'
            'color:#8892A4;text-align:center;padding:32px 0;">'
            'Your conversation will appear here.</p>',
            unsafe_allow_html=True,
        )
    else:
        # Generate response if one is pending — pending_prompt cleared AFTER ask() returns
        if st.session_state.pending_prompt:
            pending = st.session_state.pending_prompt
            st.markdown(_THINKING_HTML, unsafe_allow_html=True)
            agent = _agent()
            response, updated_history = ask(agent, pending, st.session_state.agent_history)
            # Only clear pending_prompt once we have the response — prevents silent drop
            # if the connection is interrupted mid-generation
            st.session_state.pending_prompt = None
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.session_state.agent_history = updated_history
            st.rerun()

        # Render conversation history — newest message at top
        for msg in reversed(st.session_state.messages):
            st.markdown(_chat_bubble(msg["role"], msg["content"]), unsafe_allow_html=True)
