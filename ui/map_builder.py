"""
Folium choropleth map for the MiaNoise Streamlit UI.
"""

import branca.colormap as cm
import folium
import geopandas as gpd

MIAMI_CENTER = [25.7617, -80.1918]
ZOOM_START = 12


def build_map(gdf: gpd.GeoDataFrame) -> folium.Map:
    """
    Build a Folium choropleth map coloured by composite_score.

    Args:
        gdf: GeoDataFrame with 'name', 'geometry', and 'composite_score' columns.

    Returns:
        folium.Map ready for st_folium.
    """
    max_score = float(gdf["composite_score"].max()) or 1.0
    colormap = cm.LinearColormap(
        colors=["#2ecc71", "#f1c40f", "#e74c3c"],
        vmin=0.0,
        vmax=max_score,
        caption="Noise Score  (0 = quiet · 1 = loud)",
    )

    m = folium.Map(
        location=MIAMI_CENTER,
        zoom_start=ZOOM_START,
        tiles="CartoDB Voyager",
    )

    plot = gdf.copy()
    plot["score_label"] = (plot["composite_score"] * 100).round(0).astype(int).astype(str) + "%"

    folium.GeoJson(
        data=plot[["name", "composite_score", "score_label", "geometry"]].__geo_interface__,
        style_function=lambda f: {
            "fillColor": colormap(f["properties"].get("composite_score") or 0.0),
            "fillOpacity": 0.65,
            "color": "white",
            "weight": 1,
        },
        highlight_function=lambda f: {
            "fillColor": colormap(f["properties"].get("composite_score") or 0.0),
            "fillOpacity": 0.9,
            "color": "#444",
            "weight": 2,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["name", "score_label"],
            aliases=["Neighborhood", "Noise Score"],
            style="font-size:13px; padding:6px;",
        ),
    ).add_to(m)

    colormap.add_to(m)

    return m
