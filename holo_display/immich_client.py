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

        # Persona OR: si hay mas de un ID, hacemos una consulta por cada uno y unimos resultados.
        if self.config.search_mode == "person" and len(self.config.person_ids) > 1:
            results = self._fetch_person_or_assets()
            self._shuffle_assets(results)
            print("Assets cargados:", len(results))
            return results

        results: list[dict] = []
        seen_ids: set[str] = set()
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
            assets = self._extract_assets(payload)
            kept, skipped = self._filter_by_orientation(assets)
            added = 0
            for asset in kept:
                asset_id = asset.get("id")
                if not isinstance(asset_id, str):
                    continue
                if asset_id in seen_ids:
                    continue
                seen_ids.add(asset_id)
                results.append(asset)
                added += 1
            if assets:
                print(
                    f"Search page {next_page}: {added} orientacion ok, "
                    f"{skipped} descartadas. Total {len(results)}"
                )
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

    def _search_payload(self, page: str | int, person_id: str | None = None) -> dict:
        if self.config.search_mode == "smart":
            payload = {
                "query": self.config.smart_query,
                "size": str(self.config.search_size),
                "page": page,
            }
            if self.config.smart_city:
                payload["city"] = self.config.smart_city
            return payload

        person_ids = [person_id] if person_id is not None else list(self.config.person_ids)
        return {
            "personIds": person_ids,
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
        filtered: list[dict] = []
        seen_ids: set[str] = set()
        attempts = 0
        max_attempts = 6
        target = self.config.search_size

        while len(filtered) < target and attempts < max_attempts:
            attempts += 1
            response = requests.post(
                f"{self.config.immich_url}/search/random",
                headers=self.config.headers,
                json={
                    "size": target,
                    "type": "IMAGE",
                    "withExif": True,
                    "withPeople": True,
                },
                timeout=30,
            )

            if response.status_code != 200:
                print("Error en random:", response.text)
                break

            payload = response.json()
            if not isinstance(payload, list):
                break

            assets = [asset for asset in payload if isinstance(asset, dict)]
            print(f"Random intento {attempts}: descargados {len(assets)} assets")
            kept, skipped = self._filter_by_orientation(assets)
            added = 0
            for asset in kept:
                asset_id = asset.get("id")
                if not isinstance(asset_id, str):
                    continue
                if asset_id in seen_ids:
                    continue
                seen_ids.add(asset_id)
                filtered.append(asset)
                added += 1
            print(
                f"Random intento {attempts}: {added} orientacion ok, "
                f"{skipped} descartadas. Total acumulado {len(filtered)}/{target}"
            )

            if not assets:
                break

        if not filtered:
            print("Random: sin assets con orientacion aceptable")
        elif len(filtered) < target:
            print(f"Random: {len(filtered)} assets con orientacion correcta, faltan {target - len(filtered)}")

        return filtered

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

    def _filter_by_orientation(self, assets: list[dict]) -> tuple[list[dict], int]:
        kept: list[dict] = []
        skipped = 0
        for asset in assets:
            dims = self._asset_dimensions(asset)
            if dims is None:
                # Si no hay dimensiones, dejamos pasar solo si orientation = any
                if self.config.orientation == "any":
                    kept.append(asset)
                else:
                    skipped += 1
                continue
            width, height = dims
            if self._matches_orientation(width, height):
                kept.append(asset)
            else:
                skipped += 1
        return kept, skipped

    def _matches_orientation(self, width: int, height: int) -> bool:
        orientation = self.config.orientation
        if orientation == "portrait":
            return height >= width
        if orientation == "landscape":
            return width >= height
        return True

    def _asset_dimensions(self, asset: dict) -> tuple[int, int] | None:
        exif_info = asset.get("exifInfo")
        if isinstance(exif_info, dict):
            width = exif_info.get("exifImageWidth") or exif_info.get("imageWidth")
            height = exif_info.get("exifImageHeight") or exif_info.get("imageHeight")
            if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
                return width, height
        width = asset.get("width")
        height = asset.get("height")
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            return width, height
        return None

    def _fetch_person_or_assets(self) -> list[dict]:
        """Consulta /search/metadata por cada persona individualmente y une resultados (OR)."""
        assets_by_id: dict[str, dict] = {}

        for person_id in self.config.person_ids:
            next_page: str | int | None = 1
            while next_page is not None:
                response = requests.post(
                    self._search_url(),
                    headers=self.config.headers,
                    json=self._search_payload(next_page, person_id),
                    timeout=15,
                )

                if response.status_code != 200:
                    print(f"Error en search para {person_id}:", response.text)
                    break

                payload = response.json()
                for asset in self._extract_assets(payload):
                    if not isinstance(asset, dict):
                        continue
                    asset_id = asset.get("id")
                    if isinstance(asset_id, str) and asset_id:
                        assets_by_id.setdefault(asset_id, asset)

                next_page = self._extract_next_page(payload)

        return list(assets_by_id.values())
