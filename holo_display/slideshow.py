from __future__ import annotations

import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Callable

from .config import AppConfig
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

                    current_display = self.display
                    current_display_time = self.config.display_time
                    self._mark_seen(prepared.asset["id"])
                    self._reload_config_if_needed()
                    next_frame_future = self._submit_next_frame(executor)

                    current_display.show_image(
                        self.config.image_path,
                        current_display_time,
                    )

                except Exception as error:
                    print("Error:", error)
                    time.sleep(5)
                    next_frame_future = self._submit_next_frame(executor)

    def _next_asset(self) -> dict | None:
        with self.state_lock:
            if not self.asset_buffer:
                self.asset_buffer = deque(self.client.fetch_assets())

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
            image_bytes = self.client.fetch_thumbnail(asset_id)

            try:
                image, (width, height) = self.processor.prepare(
                    image_bytes,
                    allow_vertical=self.config.search_mode == "memories",
                )
            except ValueError as error:
                if str(error) == "vertical_image":
                    continue
                raise

            if self.config.search_mode == "memories":
                image = self.processor.add_person_overlay(
                    image,
                    year=self._memory_year(overlay_asset),
                    people=None,
                    location=self._asset_location_label(overlay_asset),
                    layout=self.config.overlay_layout,
                )
            elif self.config.search_mode in {"person", "random"} and self.config.show_person_overlay:
                image = self.processor.add_person_overlay(
                    image,
                    year=self._memory_year(overlay_asset),
                    people=self._asset_people_label(overlay_asset),
                    location=self._asset_location_label(overlay_asset),
                    layout=self.config.overlay_layout,
                )

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

    def _print_asset_info(self, asset: dict, width: int, height: int) -> None:
        filename = asset.get("originalFileName", "unknown")
        date = asset.get("fileCreatedAt", "unknown")
        location = self._asset_location_label(asset) or "sin ubicacion"

        print("")
        print("Nueva imagen")
        print("Archivo:", filename)
        print("Fecha:", date)
        print("Ubicacion:", location)
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
            if isinstance(name, str) and name.strip():
                names.append(name.strip().split()[0])

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
                location_parts.append(value.strip())

        if not location_parts:
            return None
        return ", ".join(dict.fromkeys(location_parts))

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
        self.client = ImmichClient(new_config)
        self.processor = ImageProcessor(
            screen_width=new_config.screen_width,
            screen_height=new_config.screen_height,
        )
        self.display = self.display_builder(new_config)
        self.config.pics_dir.mkdir(parents=True, exist_ok=True)

        with self.state_lock:
            self.asset_buffer.clear()
            self.seen = deque(maxlen=new_config.seen_buffer_size)

        print("")
        print("Configuracion recargada")
        print("Modo anterior:", previous_config.search_mode)
        print("Modo nuevo:", new_config.search_mode)
        self._print_config_summary()

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
