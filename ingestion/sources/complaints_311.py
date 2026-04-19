import logging

import geopandas as gpd
import pandas as pd
import requests

from ingestion.db import load_neighborhood_geodataframe
from .base import NeighborhoodScore, NoiseSource

logger = logging.getLogger(__name__)

# City of Miami 311 Service Requests (since 2015).
# Separate from Miami-Dade County 311 (different jurisdiction, different system).
# City of Miami covers Wynwood, Brickell, Little Havana, Downtown, etc. — our
# exact target neighborhoods (lat ~25.73–25.85).
FEATURE_SERVICE_URL = (
    "https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services"
    "/City_of_Miami_311_Service_Requests_Since_2015/FeatureServer/0/query"
)

PAGE_SIZE = 2000


class Complaints311(NoiseSource):
    """City of Miami 311 — noise violation service requests (NOISEVIO) per neighborhood."""

    source_id = "complaints_311"
    weight = 0.3
    required_env_vars = []  # public dataset — no key required

    def fetch(self) -> list[NeighborhoodScore]:
        neighborhoods = load_neighborhood_geodataframe()[["name", "geometry"]]
        records = self._fetch_all_records()

        if not records:
            logger.warning("complaints_311: no records returned — returning zero scores")
            return self._zero_scores(neighborhoods)

        df = pd.DataFrame(records)
        df["latitude"]  = pd.to_numeric(df.get("latitude"),  errors="coerce")
        df["longitude"] = pd.to_numeric(df.get("longitude"), errors="coerce")
        df = df.dropna(subset=["latitude", "longitude"])

        if df.empty:
            logger.warning("complaints_311: all records missing coordinates")
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
            "complaints_311: %d violations across %d neighborhoods (max=%d)",
            int(counts.sum()), int((counts > 0).sum()), int(max_count),
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
        """Fetch all City of Miami NOISEVIO records, paginated.

        No date filter: the dataset last updated August 2024 and the ArcGIS
        endpoint rejects epoch-ms comparisons, so we use all 578 historical
        records. The spatial join still provides neighborhood-level signal.
        """
        where = "issue_type = 'NOISEVIO'"

        records, offset = [], 0
        while True:
            params = {
                "where": where,
                "outFields": "issue_type,latitude,longitude,ticket_created_date_time",
                "resultRecordCount": PAGE_SIZE,
                "resultOffset": offset,
                "f": "json",
            }
            try:
                resp = requests.get(
                    FEATURE_SERVICE_URL, params=params, timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("complaints_311 API error at offset %d: %s", offset, exc)
                break

            features = data.get("features", [])
            records.extend(f["attributes"] for f in features)
            logger.debug("complaints_311: %d records at offset=%d", len(features), offset)

            if not data.get("exceededTransferLimit") or len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        logger.info("complaints_311: %d NOISEVIO records (all time)", len(records))
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
