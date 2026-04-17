import logging
import os

import geopandas as gpd
import pandas as pd
import requests

from ingestion.db import load_neighborhood_geodataframe
from .base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)

# Miami-Dade Code Compliance Violation open dataset.
# Note: Miami-Dade County 311 datasets (data_311_YYYY) categorise only waste
# and infrastructure requests — noise complaints are handled by Code Compliance.
# This endpoint returns open violations; filter PROBLEM_DESC for noise.
FEATURE_SERVICE_URL = (
    "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services"
    "/CodeComplianceViolation_Open_View/FeatureServer/0/query"
)

NOISE_WHERE = "UPPER(PROBLEM_DESC) LIKE '%NOISE%'"
PAGE_SIZE = 2000


class Complaints311(NoiseSource):
    """Miami-Dade Code Compliance — open noise regulation violations per neighborhood."""

    source_id = "complaints_311"
    weight = 0.5
    required_env_vars = []  # public dataset — no key required

    def fetch(self) -> list[NeighborhoodScore]:
        neighborhoods = load_neighborhood_geodataframe()[["name", "geometry"]]

        records = self._fetch_all_records()
        if not records:
            logger.warning("complaints_311: no records returned — returning zero scores")
            return self._zero_scores(neighborhoods)

        # ArcGIS returns geometry in the requested outSR; x=lon, y=lat
        df = pd.DataFrame([
            {"longitude": f["geometry"]["x"], "latitude": f["geometry"]["y"]}
            for f in records
            if f.get("geometry") and f["geometry"].get("x") and f["geometry"].get("y")
        ])

        if df.empty:
            logger.warning("complaints_311: no usable coordinates in response")
            return self._zero_scores(neighborhoods)

        complaints_gdf = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
            crs="EPSG:4326",
        )

        joined = gpd.sjoin(
            complaints_gdf[["geometry"]],
            neighborhoods,
            how="left",
            predicate="within",
        )
        counts = (
            joined.groupby("name").size().reindex(neighborhoods["name"], fill_value=0)
        )

        max_count = counts.max()
        if max_count == 0:
            return self._zero_scores(neighborhoods)

        logger.info(
            "complaints_311: %d violations mapped across %d neighborhoods",
            counts.sum(),
            (counts > 0).sum(),
        )
        return [
            NeighborhoodScore(
                neighborhood=name,
                normalized_score=round(count / max_count, 6),
                raw_value=float(count),
                source_id=self.source_id,
                metadata={"raw_count": int(count)},
            )
            for name, count in counts.items()
        ]

    def _fetch_all_records(self) -> list[dict]:
        """Paginate through the ArcGIS feature service and return all matching features."""
        records = []
        offset = 0
        headers = {}
        app_token = os.getenv("MIAMI_DATA_APP_TOKEN")
        if app_token:
            headers["X-App-Token"] = app_token

        while True:
            params = {
                "where": NOISE_WHERE,
                "outFields": "PROBLEM_DESC",
                "outSR": "4326",      # return geometry in WGS84
                "resultRecordCount": PAGE_SIZE,
                "resultOffset": offset,
                "f": "json",
            }
            try:
                resp = requests.get(
                    FEATURE_SERVICE_URL, params=params, headers=headers, timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("complaints_311 API error at offset %d: %s", offset, exc)
                break

            features = data.get("features", [])
            records.extend(features)
            logger.debug("complaints_311: %d records at offset=%d", len(features), offset)

            if not data.get("exceededTransferLimit") or len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        logger.info("complaints_311: %d total noise violation records fetched", len(records))
        return records

    @staticmethod
    def _zero_scores(neighborhoods: gpd.GeoDataFrame) -> list[NeighborhoodScore]:
        return [
            NeighborhoodScore(
                neighborhood=row["name"],
                normalized_score=0.0,
                raw_value=0.0,
                source_id="complaints_311",
                metadata={"raw_count": 0},
            )
            for _, row in neighborhoods.iterrows()
        ]
