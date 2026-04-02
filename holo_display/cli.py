from __future__ import annotations

import argparse
import sys

from .config import (
    AppConfig,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DISPLAY_BACKEND,
    DEFAULT_DISPLAY_TIME,
    DEFAULT_TRANSITION_MS,
    FileConfig,
    load_file_config,
)


def build_config(argv: list[str] | None = None) -> AppConfig:
    args = list(sys.argv[1:] if argv is None else argv)
    config_path = _extract_config_path(args)
    file_config = load_file_config(config_path)
    parser = _build_parser(file_config)
    namespace = parser.parse_args(args)

    search_mode = file_config.search_mode
    active_people = tuple(file_config.default_people)
    active_person = active_people[0]
    person_ids = tuple(file_config.persons[name] for name in active_people)
    person_id = person_ids[0]
    smart_query = file_config.smart_query

    if search_mode == "smart":
        search_mode = "smart"
        active_person = None
        active_people = ()
        person_id = None
        person_ids = ()
    elif search_mode == "memories":
        search_mode = "memories"
        active_person = None
        active_people = ()
        person_id = None
        person_ids = ()
    elif search_mode == "random":
        search_mode = "random"
        active_person = None
        active_people = ()
        person_id = None
        person_ids = ()

    if namespace.person is not None:
        search_mode = "person"
        active_people = tuple(namespace.person)
        active_person = active_people[0]
        person_ids = tuple(file_config.persons[name] for name in active_people)
        person_id = person_ids[0]
        smart_query = None
    elif namespace.smart is not None:
        search_mode = "smart"
        active_person = None
        active_people = ()
        person_id = None
        person_ids = ()
        smart_query = namespace.smart
    elif namespace.memories:
        search_mode = "memories"
        active_person = None
        active_people = ()
        person_id = None
        person_ids = ()
        smart_query = None
    elif namespace.random:
        search_mode = "random"
        active_person = None
        active_people = ()
        person_id = None
        person_ids = ()
        smart_query = None

    return AppConfig(
        immich_url=file_config.immich_url,
        api_key=file_config.api_key,
        display_time=namespace.seconds,
        display_backend=namespace.backend,
        show_person_overlay=file_config.show_person_overlay,
        overlay_layout=file_config.overlay_layout,
        year_overlay_font_size=file_config.year_overlay_font_size,
        info_overlay_font_size=file_config.info_overlay_font_size,
        pics_dir=file_config.pics_dir,
        screen_width=file_config.screen_width,
        screen_height=file_config.screen_height,
        active_person=active_person,
        active_people=active_people,
        person_id=person_id,
        person_ids=person_ids,
        search_mode=search_mode,
        smart_query=smart_query,
        smart_city=file_config.smart_city,
        transition_ms=namespace.speed,
        search_size=file_config.search_size,
        seen_buffer_size=file_config.seen_buffer_size,
    )


def _extract_config_path(args: list[str]) -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    namespace, _ = parser.parse_known_args(args)
    return namespace.config


def _build_parser(file_config: FileConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="HoloDisplay.py",
        description="Muestra fotos de Immich en modo persona o smart search.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Ruta al archivo TOML de configuracion.",
    )

    search_group = parser.add_mutually_exclusive_group()
    search_group.add_argument(
        "--person",
        action="append",
        default=None,
        choices=sorted(file_config.persons.keys()),
        help="Persona a buscar en Immich. Se puede repetir varias veces.",
    )
    search_group.add_argument(
        "--smart",
        metavar="QUERY",
        help="Query para smart search en Immich.",
    )
    search_group.add_argument(
        "--memories",
        action="store_true",
        help="Muestra los assets devueltos por el endpoint de memories.",
    )
    search_group.add_argument(
        "--random",
        action="store_true",
        help="Muestra fotos aleatorias de toda la libreria.",
    )

    backend_group = parser.add_mutually_exclusive_group()
    backend_group.add_argument(
        "--pygame",
        dest="backend",
        action="store_const",
        const="pygame",
        help="Usa el backend pygame.",
    )
    backend_group.add_argument(
        "--framebuffer",
        dest="backend",
        action="store_const",
        const="framebuffer",
        help="Usa el backend framebuffer.",
    )

    parser.set_defaults(
        backend=file_config.display_backend or DEFAULT_DISPLAY_BACKEND,
        seconds=file_config.display_time or DEFAULT_DISPLAY_TIME,
        speed=file_config.transition_ms or DEFAULT_TRANSITION_MS,
    )
    parser.add_argument(
        "--seconds",
        type=int,
        help="Segundos que cada foto permanece en pantalla.",
    )
    parser.add_argument(
        "--speed",
        type=int,
        help="Velocidad de cambio en milisegundos para la transicion.",
    )

    return parser
