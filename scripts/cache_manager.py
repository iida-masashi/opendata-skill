import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, cast

import polars as pl


class CacheManager:
    """
    Manages local caching of OpenData API responses using Parquet files.
    """

    def __init__(self, cache_dir: str = ".cache"):
        # Resolve path relative to opendata-skill root if possible
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> dict[str, Any]:
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, encoding="utf-8") as f:
                    return cast(dict[str, Any], json.load(f))
            except Exception as e:
                logging.warning(f"Failed to load cache metadata: {e}")
        return {}

    def _save_metadata(self) -> None:
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logging.warning(f"Failed to save cache metadata: {e}")

    def _generate_key(self, source: str, params: dict[str, Any]) -> str:
        """Generates a unique key based on source and parameters."""
        param_str = json.dumps(params, sort_keys=True)
        hash_obj = hashlib.md5(f"{source}_{param_str}".encode())
        return hash_obj.hexdigest()

    def get(self, source: str, params: dict[str, Any]) -> pl.DataFrame | None:
        """Retrieves data from cache if available and not expired."""
        key = self._generate_key(source, params)
        entry = self.metadata.get(key)

        if not entry:
            return None

        # Check expiration
        expires_at = entry.get("expires_at", 0)
        if time.time() > expires_at:
            logging.info(f"Cache expired for {source} with key {key}")
            return None

        file_path = self.cache_dir / f"{key}.parquet"
        if not file_path.exists():
            return None

        try:
            return pl.read_parquet(file_path)
        except Exception as e:
            logging.warning(f"Failed to read cache file {file_path}: {e}")
            return None

    def set(self, source: str, params: dict[str, Any], df: pl.DataFrame, ttl_hours: int = 24) -> None:
        """Saves data to cache with a specified TTL."""
        if df.is_empty():
            return

        key = self._generate_key(source, params)
        file_path = self.cache_dir / f"{key}.parquet"

        try:
            df.write_parquet(file_path)

            self.metadata[key] = {
                "source": source,
                "params": params,
                "created_at": time.time(),
                "expires_at": time.time() + (ttl_hours * 3600),
                "rows": len(df)
            }
            self._save_metadata()
            logging.info(f"Cached {len(df)} rows for {source} (expires in {ttl_hours}h)")
        except Exception as e:
            logging.warning(f"Failed to save cache for {source}: {e}")

    def clear(self) -> None:
        """Clears all cached data."""
        for file in self.cache_dir.glob("*.parquet"):
            file.unlink()
        self.metadata = {}
        self._save_metadata()
