from __future__ import annotations

from datetime import date

import requests

from .config import AppConfig


class ImmichClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.asset_details_cache: dict[str, dict] = {}

    def fetch_assets(self) -> list[dict]:
        if self.config.search_mode == "memories":
            print("Consultando memories...")
            results = self._fetch_memories_assets()
            print("Assets cargados:", len(results))
            return results
        if self.config.search_mode == "random":
            print("Consultando random...")
            results = self._fetch_random_assets()
            print("Assets cargados:", len(results))
            return results

        if self.config.search_mode == "smart":
            print("Consultando smart search...")
        else:
            print("Consultando biblioteca...")

        results: list[dict] = []
        next_page: str | int | None = 1

        while next_page is not None:
            response = requests.post(
                self._search_url(),
                headers=self.config.headers,
                json=self._search_payload(next_page),
                timeout=15,
            )

            if response.status_code != 200:
                print("Error en search:", response.text)
                return []

            payload = response.json()
            results.extend(self._extract_assets(payload))
            next_page = self._extract_next_page(payload)

        if self.config.search_mode != "memories":
            self._shuffle_assets(results)
        print("Assets cargados:", len(results))
        return results

    def fetch_thumbnail(self, asset_id: str) -> bytes:
        response = requests.get(
            f"{self.config.immich_url}/assets/{asset_id}/thumbnail?size=preview",
            headers=self.config.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.content

    def fetch_asset_details(self, asset_id: str) -> dict:
        cached = self.asset_details_cache.get(asset_id)
        if cached is not None:
            return cached

        response = requests.get(
            f"{self.config.immich_url}/assets/{asset_id}",
            headers=self.config.headers,
            timeout=30,
        )

        if response.status_code != 200:
            print("Error en asset details:", response.text)
            details = {}
        else:
            payload = response.json()
            details = payload if isinstance(payload, dict) else {}

        self.asset_details_cache[asset_id] = details
        return details

    def _search_url(self) -> str:
        if self.config.search_mode == "smart":
            return f"{self.config.immich_url}/search/smart"
        return f"{self.config.immich_url}/search/metadata"

    def _search_payload(self, page: str | int) -> dict:
        if self.config.search_mode == "smart":
            payload = {
                "query": self.config.smart_query,
                "size": str(self.config.search_size),
                "page": page,
            }
            if self.config.smart_city:
                payload["city"] = self.config.smart_city
            return payload

        return {
            "personIds": list(self.config.person_ids),
            "size": self.config.search_size,
            "type": "IMAGE",
            "order": "asc",
            "withExif": True,
            "withPeople": True,
            "page": page,
        }

    def _extract_assets(self, payload: dict) -> list[dict]:
        assets = payload.get("assets")
        if isinstance(assets, dict):
            items = assets.get("items", [])
            if isinstance(items, list):
                return items

        if isinstance(assets, list):
            return assets

        items = payload.get("items", [])
        if isinstance(items, list):
            return items

        return []

    def _extract_next_page(self, payload: dict) -> str | int | None:
        assets = payload.get("assets")
        if isinstance(assets, dict):
            return assets.get("nextPage")
        return None

    def _fetch_memories_assets(self) -> list[dict]:
        memory_date = self._today_memory_date()
        print("Desplegando memorias de", memory_date)

        response = requests.get(
            f"{self.config.immich_url}/memories",
            headers=self.config.headers,
            params={
                "type": "on_this_day",
                "for": memory_date,
            },
            timeout=30,
        )

        if response.status_code != 200:
            print("Error en memories:", response.text)
            return []

        payload = response.json()
        memories = payload if isinstance(payload, list) else []
        self._print_memories_summary(memories)
        assets_by_id: dict[str, dict] = {}

        for memory in memories:
            if not isinstance(memory, dict):
                continue

            assets = memory.get("assets", [])
            if not isinstance(assets, list):
                continue

            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                asset_id = asset.get("id")
                if not isinstance(asset_id, str) or not asset_id:
                    continue
                if asset.get("type") != "IMAGE":
                    continue
                assets_by_id.setdefault(asset_id, asset)

        ordered_assets = list(assets_by_id.values())
        ordered_assets.sort(key=self._asset_sort_key, reverse=True)
        return ordered_assets

    def _print_memories_summary(self, memories: list[dict]) -> None:
        years: list[str] = []
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            memory_at = memory.get("memoryAt")
            if isinstance(memory_at, str) and len(memory_at) >= 4:
                year = memory_at[:4]
                if year.isdigit():
                    years.append(year)

        if years:
            print(f"{len(memories)} memorias, {', '.join(years)}")
        else:
            print(f"{len(memories)} memorias")

    def _fetch_random_assets(self) -> list[dict]:
        response = requests.post(
            f"{self.config.immich_url}/search/random",
            headers=self.config.headers,
            json={
                "size": self.config.search_size,
                "type": "IMAGE",
                "withExif": True,
                "withPeople": True,
            },
            timeout=30,
        )

        if response.status_code != 200:
            print("Error en random:", response.text)
            return []

        payload = response.json()
        if not isinstance(payload, list):
            return []

        return [asset for asset in payload if isinstance(asset, dict)]

    def _today_memory_date(self) -> str:
        return date.today().isoformat()

    def _asset_sort_key(self, asset: dict) -> tuple[str, str]:
        file_created_at = asset.get("fileCreatedAt")
        if not isinstance(file_created_at, str):
            file_created_at = ""
        asset_id = asset.get("id")
        if not isinstance(asset_id, str):
            asset_id = ""
        return (file_created_at, asset_id)

    def _shuffle_assets(self, assets: list[dict]) -> None:
        import random

        random.shuffle(assets)
