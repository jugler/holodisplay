from __future__ import annotations

import re
import time
from collections import deque
from datetime import date, datetime
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Callable
import json

from .config import AppConfig

COUNTRY_ALIASES = {
    "United States of America": "USA",
    "United Kingdom": "UK",
}
from .display import DisplayBackend
from .image_processing import ImageProcessor
from .immich_client import ImmichClient


@dataclass
class PreparedFrame:
    asset: dict
    image: object
    width: int
    height: int


class SlideshowApp:
    def __init__(
        self,
        config: AppConfig,
        config_loader: Callable[[], AppConfig],
        client: ImmichClient,
        processor: ImageProcessor,
        display_builder: Callable[[AppConfig], DisplayBackend],
        display: DisplayBackend,
    ) -> None:
        self.config = config
        self.config_loader = config_loader
        self.client = client
        self.processor = processor
        self.display_builder = display_builder
        self.display = display
        self.seen = deque(maxlen=config.seen_buffer_size)
        self.asset_buffer: deque[dict] = deque()
        self.state_lock = Lock()

    def run_forever(self) -> None:
        self._reset_immediate_next()
        self._print_config_summary()

        with ThreadPoolExecutor(max_workers=1) as executor:
            next_frame_future = self._submit_next_frame(executor)

            while True:
                try:
                    prepared = next_frame_future.result()
                    if prepared is None:
                        time.sleep(5)
                        next_frame_future = self._submit_next_frame(executor)
                        continue

                    self._print_asset_info(
                        prepared.asset,
                        prepared.width,
                        prepared.height,
                    )

                    prepared.image.save(self.config.tmp_path)
                    self.config.tmp_path.replace(self.config.image_path)
                    self._write_metadata(prepared.asset)

                    current_display = self.display
                    current_display_time = self.config.display_time
                    self._mark_seen(prepared.asset["id"])
                    self._reload_config_if_needed()
                    next_frame_future = self._submit_next_frame(executor)

                    stop_event = Event()
                    watcher = self._start_config_watcher(stop_event)

                    current_display.show_image(
                        self.config.image_path,
                        current_display_time,
                        stop_event=stop_event,
                    )

                    changed = stop_event.is_set()
                    stop_event.set()
                    watcher.join(timeout=0.2)

                    if changed:
                        if not next_frame_future.done():
                            next_frame_future.cancel()
                        self._reload_config_if_needed()
                        next_frame_future = self._submit_next_frame(executor)

                except Exception as error:
                    print("Error:", error)
                    time.sleep(5)
                    next_frame_future = self._submit_next_frame(executor)

    def _next_asset(self) -> dict | None:
        with self.state_lock:
            if not self.asset_buffer:
                fetched_assets = self.client.fetch_assets()
                if self._should_reset_seen(fetched_assets):
                    self.seen.clear()
                self.asset_buffer = deque(fetched_assets)

            if not self.asset_buffer:
                return None

            asset = self.asset_buffer.popleft()
            if self.config.search_mode == "memories":
                self.asset_buffer.append(asset)
            return asset

    def _submit_next_frame(
        self,
        executor: ThreadPoolExecutor,
    ) -> Future[PreparedFrame | None]:
        return executor.submit(self._prepare_next_frame)

    def _prepare_next_frame(self) -> PreparedFrame | None:
        while True:
            asset = self._next_asset()
            if asset is None:
                return None

            asset_id = asset["id"]
            if self._was_seen(asset_id):
                continue

            overlay_asset = self._asset_with_details(asset)

            pre_dims = self._asset_dimensions(overlay_asset)
            if pre_dims is not None and not self._matches_orientation(*pre_dims):
                print(
                    f"Descartada por orientacion (pre): {pre_dims[0]}x{pre_dims[1]} "
                    f"(orientation={self.config.orientation})"
                )
                continue

            image_bytes = self.client.fetch_thumbnail(asset_id)

            try:
                image, (width, height) = self.processor.prepare(
                    image_bytes,
                    allow_vertical=(
                        self.config.search_mode == "memories"
                        or self.config.orientation == "portrait"
                    ),
                )
            except ValueError as error:
                if str(error) == "vertical_image":
                    continue
                raise

            filename = overlay_asset.get("originalFileName", "unknown")
            if not self._matches_orientation(width, height):
                continue

            if self.config.search_mode == "memories":
                image = self.processor.add_person_overlay(
                    image,
                    year=self._memory_year(overlay_asset),
                    people=None,
                    location=self._asset_location_label(overlay_asset),
                    layout=self.config.overlay_layout,
                    show_year=self.config.show_year_overlay,
                    show_info=self.config.show_info_overlay,
                )
            elif (
                self.config.search_mode in {"person", "random"}
                and not self.config.use_art_api_key
                and (self.config.show_year_overlay or self.config.show_info_overlay)
            ):
                image = self.processor.add_person_overlay(
                    image,
                    year=self._memory_year(overlay_asset),
                    people=self._asset_people_label(overlay_asset),
                    location=self._asset_location_label(overlay_asset),
                    layout=self.config.overlay_layout,
                    show_year=self.config.show_year_overlay,
                    show_info=self.config.show_info_overlay,
                )

            image = self.processor.apply_brightness(image)

            if self.config.orientation == "portrait" and self.config.rotation_degrees:
                image = image.rotate(self.config.rotation_degrees, expand=True)
                width, height = image.size

            return PreparedFrame(
                asset=overlay_asset,
                image=image,
                width=width,
                height=height,
            )

    def _was_seen(self, asset_id: str) -> bool:
        if self.config.search_mode == "memories":
            return False
        with self.state_lock:
            return asset_id in self.seen

    def _mark_seen(self, asset_id: str) -> None:
        if self.config.search_mode == "memories":
            return
        with self.state_lock:
            self.seen.append(asset_id)

    def _should_reset_seen(self, assets: list[dict]) -> bool:
        if self.config.search_mode == "memories":
            return False
        if not assets or not self.seen:
            return False

        asset_ids = [
            asset_id
            for asset in assets
            if isinstance(asset, dict)
            for asset_id in [asset.get("id")]
            if isinstance(asset_id, str) and asset_id
        ]
        if not asset_ids:
            return False

        return all(asset_id in self.seen for asset_id in asset_ids)

    def _matches_orientation(self, width: int, height: int) -> bool:
        orientation = self.config.orientation
        if orientation == "portrait":
            return height >= width
        if orientation == "landscape":
            return width >= height
        return True

    def _print_asset_info(self, asset: dict, width: int, height: int) -> None:
        filename = asset.get("originalFileName", "unknown")
        date = asset.get("fileCreatedAt", "unknown")
        location = self._asset_location_label(asset) or "sin ubicacion"
        overlay_label = self._overlay_label()

        print("")
        print("Nueva imagen")
        print("Archivo:", filename)
        print("Fecha:", date)
        print("Ubicacion:", location)
        print("Overlays:", overlay_label)
        print("Grayscale:", "si" if self.config.grayscale else "no")
        print("Resolucion:", width, "x", height)
        print("")

    def _memory_year(self, asset: dict) -> str | None:
        file_created_at = asset.get("fileCreatedAt")
        if not isinstance(file_created_at, str) or len(file_created_at) < 4:
            return None
        year = file_created_at[:4]
        if not year.isdigit():
            return None
        return year

    def _asset_people_label(self, asset: dict) -> str | None:
        people = asset.get("people")
        if not isinstance(people, list):
            return None

        names: list[str] = []
        for person in people:
            if not isinstance(person, dict):
                continue
            name = person.get("name")
            birthdate = person.get("birthDate")
            label = self._format_person_label(name, birthdate, asset.get("fileCreatedAt"))
            if label:
                names.append(label)

        if not names:
            return None
        return ", ".join(dict.fromkeys(names))

    def _asset_location_label(self, asset: dict) -> str | None:
        exif_info = asset.get("exifInfo")
        city = asset.get("city")
        country = asset.get("country")

        if isinstance(exif_info, dict):
            city = exif_info.get("city", city)
            country = exif_info.get("country", country)

        location_parts: list[str] = []
        for value in (city, country):
            if isinstance(value, str) and value.strip():
                trimmed = value.strip()
                location_parts.append(COUNTRY_ALIASES.get(trimmed, trimmed))

        unique_parts = list(dict.fromkeys(location_parts))
        if not unique_parts:
            return None
        if self.config.orientation == "landscape":
            return ", ".join(unique_parts[:2])
        if len(unique_parts) >= 2:
            return "\n".join(unique_parts[:2])
        return unique_parts[0]

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

    def _format_person_label(self, name: object, birthdate: object, file_created_at: object) -> str | None:
        if not isinstance(name, str) or not name.strip():
            return None
        clean_name = name.strip().split()[0]
        age_info = self._compute_age(file_created_at, birthdate)
        if age_info is None:
            return clean_name
        if "months" in age_info:
            return f"{clean_name} ({age_info['months']} meses)"
        return f"{clean_name} ({age_info['years']})"

    def _compute_age(self, photo_date_raw: object, birthdate_raw: object) -> dict[str, int] | None:
        if not isinstance(photo_date_raw, str) or not isinstance(birthdate_raw, str):
            return None
        try:
            photo_date = datetime.fromisoformat(photo_date_raw.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                photo_date = date.fromisoformat(photo_date_raw[:10])
            except Exception:
                return None
        try:
            birth_date = date.fromisoformat(birthdate_raw[:10])
        except Exception:
            return None
        years = photo_date.year - birth_date.year
        if (photo_date.month, photo_date.day) < (birth_date.month, birth_date.day):
            years -= 1
        if years < 0 or years > 150:
            return None
        if years > 0:
            return {"years": years}

        # Months old (only when under 1 year)
        months = (photo_date.year - birth_date.year) * 12 + (photo_date.month - birth_date.month)
        if photo_date.day < birth_date.day:
            months -= 1
        if months < 0 or months > 24:
            return None
        return {"months": months}

    def _asset_with_details(self, asset: dict) -> dict:
        if self.config.search_mode != "memories":
            return asset

        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id:
            return asset

        details = self.client.fetch_asset_details(asset_id)
        if not details:
            return asset

        merged = dict(asset)
        merged.update(details)
        return merged

    def _reload_config_if_needed(self) -> None:
        try:
            new_config = self.config_loader()
        except ValueError as error:
            print("No se pudo recargar la configuracion:", error)
            return

        if new_config == self.config:
            return

        previous_config = self.config
        self.config = new_config
        search_changed = self._has_search_changed(previous_config, new_config)
        client_changed = (
            search_changed
            or previous_config.api_key != new_config.api_key
            or previous_config.immich_url != new_config.immich_url
            or previous_config.use_art_api_key != new_config.use_art_api_key
        )

        if client_changed:
            self.client = ImmichClient(new_config)
        else:
            # Keep the cache but point the client to the updated config.
            self.client.config = new_config
        self.processor = ImageProcessor(
            screen_width=new_config.logical_width,
            screen_height=new_config.logical_height,
            grayscale=new_config.grayscale,
            brightness=new_config.brightness,
            year_overlay_font_size=new_config.year_overlay_font_size,
            info_overlay_font_size=new_config.info_overlay_font_size,
            year_overlay_x=new_config.year_overlay_x,
            year_overlay_y=new_config.year_overlay_y,
            info_overlay_x=new_config.info_overlay_x,
            info_overlay_y=new_config.info_overlay_y,
        )
        if self._requires_display_rebuild(previous_config, new_config):
            self.display = self.display_builder(new_config)
        self.config.pics_dir.mkdir(parents=True, exist_ok=True)

        with self.state_lock:
            if search_changed:
                self.asset_buffer.clear()
                self.seen = deque(maxlen=new_config.seen_buffer_size)
            else:
                self.seen = deque(self.seen, maxlen=new_config.seen_buffer_size)

        print("")
        print("Configuracion recargada")
        print("Modo anterior:", previous_config.search_mode)
        print("Modo nuevo:", new_config.search_mode)
        self._print_config_summary()

    def _requires_display_rebuild(
        self,
        previous_config: AppConfig,
        new_config: AppConfig,
    ) -> bool:
        return (
            previous_config.display_backend != new_config.display_backend
            or previous_config.screen_width != new_config.screen_width
            or previous_config.screen_height != new_config.screen_height
            or previous_config.transition_ms != new_config.transition_ms
        )

    def _has_search_changed(self, previous_config: AppConfig, new_config: AppConfig) -> bool:
        return (
            previous_config.search_mode != new_config.search_mode
            or previous_config.active_people != new_config.active_people
            or previous_config.person_ids != new_config.person_ids
            or previous_config.smart_query != new_config.smart_query
            or previous_config.smart_city != new_config.smart_city
            or previous_config.search_size != new_config.search_size
        )

    def _print_config_summary(self) -> None:
        self.config.pics_dir.mkdir(parents=True, exist_ok=True)

        if self.config.search_mode == "smart":
            print("Busqueda inteligente:", self.config.search_label)
        elif self.config.search_mode == "memories":
            print("Modo memories:", self.config.search_label)
        elif self.config.search_mode == "random":
            print("Modo random:", self.config.search_label)
        else:
            print("Personas seleccionadas:", self.config.search_label)
        print("Tiempo por foto:", self.config.display_time, "segundos")
        print("Backend de display:", self.config.display_backend)

    def _start_config_watcher(self, stop_event: Event) -> Thread:
        watcher = Thread(target=self._watch_config_changes, args=(stop_event,), daemon=True)
        watcher.start()
        return watcher

    def _watch_config_changes(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            time.sleep(0.5)
            try:
                new_config = self.config_loader()
            except ValueError:
                continue

            if new_config != self.config:
                if new_config.immediate_next:
                    self._reset_immediate_next()
                stop_event.set()
                break

    def _overlay_label(self) -> str:
        parts: list[str] = []
        if self.config.show_year_overlay:
            parts.append("año")
        if self.config.show_info_overlay:
            parts.append("info")
        overlays = ", ".join(parts) if parts else "ninguno"
        return f"{overlays} (layout={self.config.overlay_layout})"

    def _reset_immediate_next(self) -> None:
        """Reset [immediate_actions].next to 0 in the current config file."""
        path = self.config.config_path
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as error:
            print(f"No se pudo leer config para resetear immediate_actions: {error}")
            return

        # Replace existing setting if present; otherwise append section.
        pattern = r"(\[immediate_actions\][^\[]*?next\s*=\s*)1"
        replaced, count = re.subn(pattern, r"\g<1>0", text, flags=re.IGNORECASE | re.DOTALL)

        if count == 0:
            # Append section
            if not text.endswith("\n"):
                text += "\n"
            replaced += "\n[immediate_actions]\nnext = 0\n"

        try:
            path.write_text(replaced, encoding="utf-8")
        except Exception as error:
            print(f"No se pudo escribir config para resetear immediate_actions: {error}")

    def _write_metadata(self, asset: dict) -> None:
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id:
            return
        is_favorite = asset.get("isFavorite", asset.get("is_favorite", False))
        metadata = {
            "asset_id": asset_id,
            "isFavorite": bool(is_favorite),
        }
        try:
            metadata_path = self.config.pics_dir / "immich.data"
            metadata_path.write_text(json.dumps(metadata) + "\n", encoding="utf-8")
        except Exception as error:
            print(f"No se pudo escribir immich.data: {error}")
