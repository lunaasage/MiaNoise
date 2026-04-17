import logging
import os

import geopandas as gpd
import pandas as pd
import requests

from ingestion.db import load_neighborhood_geodataframe
from .base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)

# Miami-Dade 311 ArcGIS Feature Service (2022 dataset).
# If a more recent annual dataset is published at gis-mdc.opendata.arcgis.com,
# update the URL to e.g. /data_311_2023/FeatureServer/0/query.
FEATURE_SERVICE_URL = (
    "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services"
    "/data_311_2022/FeatureServer/0/query"
)

# Matches any issue_type containing "NOISE" (ArcGIS SQL, case-insensitive on server)
NOISE_WHERE = "issue_type LIKE '%NOISE%'"

PAGE_SIZE = 2000  # ArcGIS default maxRecordCount


class Complaints311(NoiseSource):
    """Miami-Dade 311 ArcGIS — noise complaint density per neighborhood."""

    source_id = "complaints_311"
    weight = 0.5
    required_env_vars = []  # public dataset — no key required

    def fetch(self) -> list[NeighborhoodScore]:
        neighborhoods = load_neighborhood_geodataframe()[["name", "geometry"]]

        records = self._fetch_all_records()
        if not records:
            logger.warning("complaints_311: no records returned — returning zero scores")
            return self._zero_scores(neighborhoods)

        df = pd.DataFrame(records)
        df = df.dropna(subset=["latitude", "longitude"])
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df = df.dropna(subset=["latitude", "longitude"])

        if df.empty:
            logger.warning("complaints_311: all records missing coordinates")
            return self._zero_scores(neighborhoods)

        complaints_gdf = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
            crs="EPSG:4326",
        )

        # Spatial join: assign each complaint to the neighborhood polygon it falls within
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
        """Paginate through the ArcGIS feature service and return all matching records."""
        records = []
        offset = 0
        headers = {}

        # Optional Socrata-era app token still accepted by some Miami endpoints
        app_token = os.getenv("MIAMI_DATA_APP_TOKEN")
        if app_token:
            headers["X-App-Token"] = app_token

        while True:
            params = {
                "where": NOISE_WHERE,
                "outFields": "issue_type,latitude,longitude",
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
                logger.warning(
                    "complaints_311 API error at offset %d: %s", offset, exc
                )
                break

            features = data.get("features", [])
            records.extend(f["attributes"] for f in features)
            logger.debug(
                "complaints_311: fetched %d records (offset=%d)", len(features), offset
            )

            if not data.get("exceededTransferLimit") or len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        logger.info("complaints_311: %d total noise records fetched", len(records))
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
