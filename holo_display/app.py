from __future__ import annotations

import sys

from .cli import build_config
from .display import FramebufferDisplay, PygameDisplay
from .image_processing import ImageProcessor
from .immich_client import ImmichClient
from .slideshow import SlideshowApp


def build_display(config):
    if config.display_backend == "pygame":
        return PygameDisplay(
            screen_width=config.screen_width,
            screen_height=config.screen_height,
            transition_ms=config.transition_ms,
        )
    return FramebufferDisplay()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    try:
        config = build_config(args)
    except ValueError as error:
        print(error)
        return 1

    app = SlideshowApp(
        config=config,
        config_loader=lambda: build_config(args),
        client=ImmichClient(config),
        processor=ImageProcessor(
            screen_width=config.screen_width,
            screen_height=config.screen_height,
        ),
        display_builder=build_display,
        display=build_display(config),
    )
    app.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
