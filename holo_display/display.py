from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from threading import Event
from typing import Protocol


class DisplayBackend(Protocol):
    def show_image(self, path: Path, display_time: int, stop_event: Event | None = None) -> None:
        ...


class FramebufferDisplay:
    def show_image(self, path: Path, display_time: int, stop_event: Event | None = None) -> None:
        subprocess.run(["killall", "fbi"], stderr=subprocess.DEVNULL, check=False)
        process = subprocess.Popen(
            [
                "fbi",
                "-T",
                "1",
                "-d",
                "/dev/fb0",
                "-a",
                "-noverbose",
                str(path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.2)

        end_time = time.time() + display_time
        while time.time() < end_time:
            if stop_event is not None and stop_event.is_set():
                break
            time.sleep(0.1)

        # Try to stop the running viewer early when requested.
        try:
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            process.kill()


class PygameDisplay:
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        transition_ms: int,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.transition_ms = transition_ms
        self._pygame = None
        self._screen = None
        self._clock = None
        self._current_surface = None
        self._selected_driver = None

    def show_image(self, path: Path, display_time: int, stop_event: Event | None = None) -> None:
        pygame = self._init_pygame()
        target_width, target_height = self._screen.get_size()
        next_surface = pygame.image.load(str(path)).convert()
        next_surface = pygame.transform.scale(next_surface, (target_width, target_height))

        transition_seconds = min(display_time, self.transition_ms / 1000)
        transition_elapsed = self._run_transition(next_surface, transition_seconds, stop_event)
        hold_seconds = max(0, display_time - transition_elapsed)

        self._screen.blit(next_surface, (0, 0))
        pygame.display.flip()
        self._current_surface = next_surface
        self._wait(hold_seconds, stop_event)

    def _init_pygame(self):
        if self._pygame is not None:
            return self._pygame

        try:
            import pygame
        except ImportError as error:
            raise RuntimeError(
                "El backend pygame requiere instalar pygame en el dispositivo."
            ) from error

        driver_candidates = self._candidate_drivers()
        errors: list[str] = []

        for driver in driver_candidates:
            try:
                self._initialize_with_driver(pygame, driver)
                break
            except pygame.error as error:
                errors.append(f"{driver}: {error}")
                pygame.quit()
        else:
            joined_errors = " | ".join(errors) if errors else "sin detalles"
            raise RuntimeError(
                f"No se pudo iniciar pygame con ningun driver SDL. {joined_errors}"
            )

        self._pygame = pygame
        detected_width, detected_height = self._screen.get_size()
        print(
            "Pygame display detectado:",
            f"{detected_width}x{detected_height}",
        )
        print("SDL video driver:", self._selected_driver)
        self._draw_startup_test_pattern()
        return pygame

    def _candidate_drivers(self) -> list[str]:
        configured = os.environ.get("IMMICH_SDL_DRIVER")
        if configured:
            return [item.strip() for item in configured.split(",") if item.strip()]
        return ["kmsdrm", "fbcon", "x11"]

    def _initialize_with_driver(self, pygame, driver: str) -> None:
        os.environ["SDL_VIDEODRIVER"] = driver
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

        if driver == "fbcon":
            os.environ.setdefault("SDL_FBDEV", "/dev/fb0")

        pygame.init()
        pygame.display.set_caption("HoloDisplay")
        pygame.mouse.set_visible(False)
        self._screen = pygame.display.set_mode(
            (0, 0),
            pygame.FULLSCREEN | pygame.NOFRAME,
        )
        self._clock = pygame.time.Clock()
        self._selected_driver = pygame.display.get_driver()
        print(f"Intentando SDL_VIDEODRIVER={driver} -> OK")

    def _draw_startup_test_pattern(self) -> None:
        pygame = self._pygame
        width, height = self._screen.get_size()
        self._screen.fill((20, 20, 20))
        pygame.draw.rect(self._screen, (220, 40, 40), (0, 0, width // 2, height // 2))
        pygame.draw.rect(
            self._screen,
            (40, 180, 60),
            (width // 2, 0, width // 2, height // 2),
        )
        pygame.draw.rect(
            self._screen,
            (40, 90, 220),
            (0, height // 2, width // 2, height // 2),
        )
        pygame.draw.rect(
            self._screen,
            (230, 200, 40),
            (width // 2, height // 2, width // 2, height // 2),
        )
        pygame.display.flip()
        time.sleep(1)

    def _run_transition(self, next_surface, duration_seconds: float, stop_event: Event | None = None) -> float:
        pygame = self._pygame
        if self._current_surface is None or duration_seconds <= 0:
            self._screen.blit(next_surface, (0, 0))
            pygame.display.flip()
            return 0.0

        start = time.monotonic()
        next_surface.set_alpha(0)
        while True:
            self._pump_events()
            if stop_event is not None and stop_event.is_set():
                break
            elapsed = time.monotonic() - start
            if elapsed >= duration_seconds:
                break

            progress = elapsed / duration_seconds

            self._screen.blit(self._current_surface, (0, 0))
            next_surface.set_alpha(int(progress * 255))
            self._screen.blit(next_surface, (0, 0))
            pygame.display.flip()
            self._clock.tick(30)
        next_surface.set_alpha(None)
        return time.monotonic() - start

    def _wait(self, seconds: float, stop_event: Event | None = None) -> None:
        end_time = time.monotonic() + seconds
        while time.monotonic() < end_time:
            if stop_event is not None and stop_event.is_set():
                break
            self._pump_events()
            self._clock.tick(30)

    def _pump_events(self) -> None:
        for event in self._pygame.event.get():
            if event.type == self._pygame.QUIT:
                raise SystemExit(0)
