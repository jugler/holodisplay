from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import (
    AppConfig,
    BROWSE_USER_CHOICES,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DISPLAY_TIME,
    DEFAULT_TRANSITION_MS,
    FileConfig,
    ORIENTATION_CHOICES,
    ROTATION_DEGREES_CHOICES,
    DEFAULT_ROTATION_DEGREES,
    effective_api_key,
    load_file_config,
    _expand_people,
)


def build_config(argv: list[str] | None = None) -> AppConfig:
    args = list(sys.argv[1:] if argv is None else argv)
    config_path = _extract_config_path(args)
    file_config = load_file_config(config_path, argv=args)
    parser = _build_parser(file_config)
    namespace = parser.parse_args(args)

    effective_user = (
        namespace.browse_user.strip()
        if isinstance(namespace.browse_user, str) and namespace.browse_user.strip()
        else file_config.active_user
    )
    if effective_user not in BROWSE_USER_CHOICES:
        raise ValueError(
            f"active_user (--user) debe ser uno de: {', '.join(sorted(BROWSE_USER_CHOICES))}"
        )

    search_mode = file_config.search_mode
    if search_mode == "person":
        active_people = _expand_people(
            file_config.default_people, file_config.persons, file_config.aliases
        )
        active_person = active_people[0]
        person_ids = tuple(file_config.persons[name] for name in active_people)
        person_id = person_ids[0]
    else:
        active_people = ()
        active_person = None
        person_ids = ()
        person_id = None
    smart_query = file_config.smart_query
    orientation = namespace.orientation or file_config.orientation
    rotation_degrees = namespace.rotation if namespace.rotation is not None else file_config.rotation_degrees

    if namespace.person is not None:
        search_mode = "person"
        active_people = _expand_people(tuple(namespace.person), file_config.persons, file_config.aliases)
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

    api_key_value = effective_api_key(
        file_config,
        active_user=effective_user,
    )

    return AppConfig(
        immich_url=file_config.immich_url,
        api_key=api_key_value,
        display_time=namespace.seconds,
        grayscale=file_config.grayscale,
        brightness=file_config.brightness,
        show_year_overlay=file_config.show_year_overlay,
        show_info_overlay=file_config.show_info_overlay,
        overlay_layout=file_config.overlay_layout,
        year_overlay_font_size=file_config.year_overlay_font_size,
        info_overlay_font_size=file_config.info_overlay_font_size,
        year_overlay_x=file_config.year_overlay_x,
        year_overlay_y=file_config.year_overlay_y,
        info_overlay_x=file_config.info_overlay_x,
        info_overlay_y=file_config.info_overlay_y,
        show_clock_overlay=file_config.show_clock_overlay,
        clock_overlay_position=file_config.clock_overlay_position,
        clock_overlay_font_size=file_config.clock_overlay_font_size,
        clock_overlay_margin=file_config.clock_overlay_margin,
        clock_overlay_space=file_config.clock_overlay_space,
        clock_overlay_show_background=file_config.clock_overlay_show_background,
        clock_overlay_x=file_config.clock_overlay_x,
        clock_overlay_y=file_config.clock_overlay_y,
        pics_dir=file_config.pics_dir,
        screen_width=file_config.screen_width,
        screen_height=file_config.screen_height,
        orientation=orientation,
        rotation_degrees=rotation_degrees,
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
        smart_result_limit=file_config.smart_result_limit,
        active_user=effective_user,
        people_source_path=file_config.people_source_path,
        immediate_next=file_config.immediate_next,
        config_path=Path(config_path).expanduser(),
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
    parser.add_argument(
        "--user",
        "--active-user",
        dest="browse_user",
        default=None,
        metavar="main|phone|art|nsfw",
        help="Biblioteca activa (immich.active_user): main, phone, art o nsfw. Por defecto el valor en config.",
    )

    search_group = parser.add_mutually_exclusive_group()
    search_group.add_argument(
        "--person",
        action="append",
        default=None,
        choices=sorted(set(file_config.persons.keys()) | set(file_config.aliases.keys())),
        help="Persona o alias a buscar en Immich. Se puede repetir varias veces.",
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

    parser.set_defaults(
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
    parser.add_argument(
        "--orientation",
        choices=sorted(ORIENTATION_CHOICES),
        help="Forzar el modo de orientacion (portrait o landscape).",
    )
    parser.add_argument(
        "--rotation",
        type=int,
        choices=sorted(ROTATION_DEGREES_CHOICES),
        help="Rotar el render final (0, 90, 180, 270); se aplica cuando orientation=portrait.",
    )

    return parser
