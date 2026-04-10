from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Tuple

import subprocess
import tomllib
import json
import requests
from flask import Flask, request, render_template_string, send_from_directory, abort

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.toml"
PEOPLE_PATH = BASE_DIR / "people.toml"
ASSETS_DIR = BASE_DIR / "assets"


@app.route("/assets/<path:filename>")
def serve_asset(filename: str):
    target = ASSETS_DIR / filename
    if not target.exists() or not target.is_file():
        abort(404)
    return send_from_directory(ASSETS_DIR, filename)


def _current_frame_path_from_display(display_section: dict[str, object]) -> Path | None:
    pics_dir = display_section.get("pics_dir")
    if not isinstance(pics_dir, str):
        return None
    base = Path(pics_dir).expanduser()
    return base / "frame.jpg"


def _read_frame_metadata(frame_path: Path | None) -> tuple[bool, str | None]:
    if frame_path is None:
        return False, None
    metadata_path = frame_path.parent / "immich.data"
    if not metadata_path.exists():
        return False, None
    try:
        raw = metadata_path.read_text(encoding="utf-8").strip()
        if not raw:
            return False, None
        data = json.loads(raw)
        return bool(data.get("isFavorite")), data.get("asset_id")
    except Exception:
        return False, None


def _write_frame_metadata(frame_path: Path | None, asset_id: str, is_favorite: bool) -> None:
    if frame_path is None:
        return
    metadata_path = frame_path.parent / "immich.data"
    try:
        metadata_path.write_text(json.dumps({"asset_id": asset_id, "isFavorite": bool(is_favorite)}) + "\n", encoding="utf-8")
    except Exception:
        pass


def _append_text(original: str | None, addition: str | None) -> str | None:
    if not addition:
        return original
    if original:
        return f"{original} / {addition}"
    return addition


def _process_favorite_action(
    immediate_section: dict[str, object],
    display_section: dict[str, object],
    immich_section: dict[str, object],
) -> tuple[str | None, str | None]:
    raw_value = immediate_section.get("favorite", 0)
    if isinstance(raw_value, bool):
        trigger = raw_value
    elif isinstance(raw_value, int):
        trigger = raw_value == 1
    else:
        trigger = False
    if not trigger:
        return None, None

    frame_path = _current_frame_path_from_display(display_section)
    _, asset_id = _read_frame_metadata(frame_path)
    if not asset_id:
        return None, "No hay asset actual para marcar favorito"

    immich_url = immich_section.get("url")
    api_key = immich_section.get("api_key")
    if not isinstance(immich_url, str) or not immich_url.strip():
        return None, "No se ha configurado la URL de Immich"
    if not isinstance(api_key, str) or not api_key.strip():
        return None, "No se ha configurado la API key de Immich"

    try:
        response = requests.put(
            f"{immich_url.rstrip('/')}/assets",
            headers={"x-api-key": api_key.strip()},
            json={"ids": [asset_id], "isFavorite": True},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return None, f"Error marcando favorito: {exc}"

    _apply_updates([("immediate_actions", "favorite", "0")])
    _write_frame_metadata(frame_path, asset_id, True)
    return "Favorito sincronizado", None


@app.route("/current-frame")
def current_frame() -> str:
    try:
        display_section, _, _, _, _, _ = _read_config_sections()
    except ValueError:
        abort(404)
    frame_path = _current_frame_path_from_display(display_section)
    if frame_path is None or not frame_path.exists():
        abort(404)
    return send_from_directory(frame_path.parent, frame_path.name)


@app.route("/current-frame/meta")
def current_frame_meta() -> str:
    try:
        display_section, _, _, _, _, _ = _read_config_sections()
    except ValueError:
        abort(404)
    frame_path = _current_frame_path_from_display(display_section)
    is_favorite, _ = _read_frame_metadata(frame_path)
    return json.dumps({"isFavorite": is_favorite})


MODE_OPTIONS: list[tuple[str, str]] = [
    ("person", "Personas"),
    ("smart", "Smart"),
    ("memories", "Memories"),
    ("random", "Random"),
    ("art", "Art"),
]


PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="apple-touch-icon" sizes="180x180" href="assets/icon-180.png">
    <title>Control HoloDisplay</title>
    <style>
        :root {
            font-family: -apple-system, system-ui, sans-serif;
            background: #0b0b0b;
            color: #f8fafc;
        }
        body {
            margin: 0;
            min-height: 100vh;
            background: linear-gradient(160deg, #1c1c1c, #0a0a0a 65%, #050505);
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 1rem;
        }
        main {
            width: min(640px, 100%);
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
        }
        header {
            text-align: center;
        }
        h1 {
            font-size: 1.8rem;
            margin: 0;
        }
        .card {
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 18px;
            padding: 1.25rem;
            box-shadow: 0 20px 40px rgba(15, 23, 42, 0.45);
        }
        .thumbnail-card {
            padding: 0;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .thumbnail-inner {
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .thumbnail-card img {
            max-width: 100%;
            max-height: 320px;
            display: block;
        }
        .thumbnail-card.portrait-preview .thumbnail-inner {
            min-height: 360px;
        }
        .thumbnail-card.portrait-preview img {
            max-height: 100%;
            max-width: 100%;
            transform: rotate(90deg);
            transition: transform 0.25s ease;
        }
        .favorite-flag {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.25rem;
            margin: 0.85rem 0 0 0;
        }
        .favorite-btn {
            width: auto;
            background: transparent;
            border: none;
            padding: 0;
            cursor: pointer;
            display: inline-flex;
            color: inherit;
        }
        .favorite-btn svg {
            width: 32px;
            height: 32px;
            stroke: #fcd34d;
            stroke-width: 1;
        }
        .favorite-btn.empty svg {
            fill: transparent;
        }
        .favorite-btn.filled svg {
            fill: #fcd34d;
        }
        label {
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
            margin-bottom: 0.8rem;
            font-size: 0.95rem;
        }
        input[type="number"],
        input[type="text"],
        select {
            border-radius: 0.65rem;
            border: 1px solid rgba(226, 232, 240, 0.2);
            padding: 0.65rem 0.8rem;
            font-size: 1rem;
            background: rgba(15, 23, 42, 0.6);
            color: inherit;
        }
        .toggle-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.65rem;
        }
        .toggle-row input[type="checkbox"] {
            width: 1.2rem;
            height: 1.2rem;
        }
        button {
            width: 100%;
            border: none;
            border-radius: 0.75rem;
            padding: 0.95rem;
            font-size: 1rem;
            font-weight: 600;
            background: #38bdf8;
            color: #0f172a;
            cursor: pointer;
            transition: transform 0.2s ease;
        }
        button.danger {
            background: #dc2626;
            color: #fefefe;
        }
        button:hover {
            transform: translateY(-1px);
        }
        .alert {
            padding: 0.8rem;
            border-radius: 0.8rem;
            font-size: 0.9rem;
        }
        .alert.success {
            background: rgba(34, 197, 94, 0.15);
            border: 1px solid rgba(34, 197, 94, 0.4);
        }
        .alert.error {
            background: rgba(248, 113, 113, 0.18);
            border: 1px solid rgba(248, 113, 113, 0.5);
        }
        .status-line {
            font-size: 0.85rem;
            color: #94a3b8;
            margin: 0.4rem 0 0;
        }
        .note {
            font-size: 0.85rem;
            color: #94a3b8;
            margin-top: 0.35rem;
        }
        .conditional {
            transition: opacity 0.15s ease;
        }
        .conditional.hidden {
            display: none;
        }
    </style>
</head>
<body>
    <main>
        <header>
            <h1>{{ instance_name or "HoloDisplay" }} Control</h1>
        </header>
        {% if error %}
        <div class="alert error">{{ error }}</div>
        {% endif %}
        {% if message %}
        <div class="alert success">{{ message }}</div>
        {% endif %}
        {% if thumbnail_available %}
        <section class="card thumbnail-card{% if portrait_mode %} portrait-preview{% endif %}">
            <div class="thumbnail-inner">
                <img src="/current-frame?t={{ thumbnail_timestamp }}" alt="Foto actual" loading="lazy">
            </div>
            <div class="favorite-flag">
                <form method="post" class="favorite-form">
                    <input type="hidden" name="action" value="favorite">
                    <button class="favorite-btn {% if is_favorite %}filled{% else %}empty{% endif %}" title="Marcar como favorito" type="submit">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="presentation" aria-hidden="true"><path d="M12 17.27L18.18 21 16.54 13.97 22 9.24 14.81 8.63 12 2 9.19 8.63 2 9.24 7.46 13.97 5.82 21z"></path></svg>
                    </button>
                </form>
            </div>
        </section>
        {% endif %}
        <section class="card">
            <form method="post">
                <input type="hidden" name="action" value="next">
                <button type="submit">Siguiente foto</button>
            </form>
        </section>
        <section class="card">
            <form method="post">
                <input type="hidden" name="action" value="config">
                <h2>Display</h2>
                <div class="toggle-row">
                    <label>
                        <span>Grayscale</span>
                        <input type="checkbox" name="grayscale" {% if grayscale %}checked{% endif %}>
                    </label>
                    <label>
                        <span>Info Overlay</span>
                        <input type="checkbox" name="show_info_overlay" {% if show_info_overlay %}checked{% endif %}>
                    </label>
                </div>
                <div class="toggle-row">
                    <label>
                        <span>Year Overlay</span>
                        <input type="checkbox" name="show_year_overlay" {% if show_year_overlay %}checked{% endif %}>
                    </label>
                    <label>
                        <span>Segundos por foto</span>
                        <input type="number" name="seconds" min="1" step="1" value="{{ seconds }}">
                    </label>
                </div>
                <label>
                    <span>Brillo</span>
                    <input type="number" name="brightness" step="0.1" min="0.1" value="{{ brightness }}">
                </label>
                <div class="separator"></div>
                <h2>Modo</h2>
                <label>
                    <span>Actual</span>
                    <select name="mode" id="mode-select">
                        {% for value, label in modes %}
                        <option value="{{ value }}" {% if value == current_mode %}selected{% endif %}>{{ label }}</option>
                        {% endfor %}
                    </select>
                </label>
                <div id="smart-section" class="conditional{% if current_mode != 'smart' %} hidden{% endif %}">
                    <label>
                        <span>Smart query</span>
                        <input type="text" name="smart_query" value="{{ smart_query or '' }}" placeholder="beach, pets, etc.">
                    </label>
                </div>
                <div id="person-section" class="conditional{% if current_mode != 'person' %} hidden{% endif %}">
                    <label>
                        <span>Alias disponibles</span>
                        <select id="alias-select">
                            <option value="">«Mantener lista actual»</option>
                            {% for alias, members in aliases.items() %}
                            <option value="{{ alias }}" data-members="{{ members | join(', ') }}" {% if alias == selected_alias %}selected{% endif %}>{{ alias }}</option>
                            {% endfor %}
                        </select>
                    </label>
                    {% if people_error %}
                    <p class="note">{{ people_error }}</p>
                    {% endif %}
                    <label>
                        <span>Personas (coma separada)</span>
                        <input type="text" name="default_people" id="default-people" value="{{ default_people | join(', ') }}" placeholder="Jesus, Vero">
                        <span class="note">Ej: {{ sample_people }}</span>
                    </label>
                </div>
                <label>
                    <span>Smart limit</span>
                    <input type="number" name="smart_result_limit" min="1" step="1" value="{{ smart_limit }}">
                </label>
                <button type="submit">Guardar</button>
                <p class="status-line">Última actualización: {{ last_updated }}</p>
            </form>
        </section>
        <section class="card">
            <form method="post">
                <input type="hidden" name="action" value="restart_holoconfig">
                <button class="danger" type="submit">Reset HoloConfig</button>
            </form>
        </section>
        <section class="card">
            <form method="post">
                <input type="hidden" name="action" value="restart">
                <button class="danger" type="submit">Reset HoloDisplay</button>
            </form>
        </section>
        <section class="card">
            <form method="post" id="shutdown-form">
                <input type="hidden" name="action" value="shutdown">
                <button class="danger" type="submit">Apagar pi</button>
            </form>
        </section>
    </main>
    <script>
        const modeSelect = document.getElementById('mode-select');
        const personSection = document.getElementById('person-section');
        const smartSection = document.getElementById('smart-section');
        const aliasSelect = document.getElementById('alias-select');
        const defaultPeopleInput = document.getElementById('default-people');

        const updateSections = () => {
            if (modeSelect.value === 'person') {
                personSection.classList.remove('hidden');
            } else {
                personSection.classList.add('hidden');
            }
            if (modeSelect.value === 'smart') {
                smartSection.classList.remove('hidden');
            } else {
                smartSection.classList.add('hidden');
            }
        };

        modeSelect.addEventListener('change', updateSections);

        aliasSelect?.addEventListener('change', () => {
            const members = aliasSelect.selectedOptions[0]?.dataset?.members;
            if (members) {
                defaultPeopleInput.value = members;
            }
        });

        document.addEventListener('DOMContentLoaded', updateSections);
        const shutdownForm = document.getElementById('shutdown-form');
        shutdownForm?.addEventListener('submit', (event) => {
            if (!confirm('¿Seguro que quieres apagar la Pi?')) {
                event.preventDefault();
            }
        });
        const framePreview = document.querySelector('.thumbnail-card img');
        const favoriteButton = document.querySelector('.favorite-btn');
        if (framePreview) {
            const refreshFrame = () => {
                const timestamp = Date.now();
                framePreview.src = `/current-frame?t=${timestamp}`;
            };
            const refreshMeta = () => {
                fetch('/current-frame/meta')
                    .then((response) => response.json())
                    .then((data) => {
                        if (!favoriteButton) {
                            return;
                        }
                        if (data.isFavorite) {
                            favoriteButton.classList.add('filled');
                            favoriteButton.classList.remove('empty');
                        } else {
                            favoriteButton.classList.remove('filled');
                            favoriteButton.classList.add('empty');
                        }
                    })
                    .catch(() => {});
            };
            const intervalId = setInterval(() => {
                refreshFrame();
                refreshMeta();
            }, 5000);
            framePreview.addEventListener('error', () => clearInterval(intervalId));
            refreshMeta();
        }
    </script>
</body>
</html>
"""


def _ensure_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} debe ser un texto no vacío")
    return value.strip()


def _load_toml(path: Path) -> dict[str, object]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"No se encontró {path.name}") from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path.name} no es TOML válido: {error}") from error


def _read_config_sections() -> tuple[dict[str, object], dict[str, object], dict[str, object], float, str, dict[str, object]]:
    raw = _load_toml(CONFIG_PATH)
    display = raw.get("display")
    if not isinstance(display, dict):
        display = {}
    search = raw.get("search")
    if not isinstance(search, dict):
        search = {}
    immediate = raw.get("immediate_actions")
    if not isinstance(immediate, dict):
        immediate = {}
    instance_section = raw.get("name_of_holo_instance")
    instance_label = ""
    if isinstance(instance_section, dict):
        name_value = instance_section.get("name")
        if isinstance(name_value, str) and name_value.strip():
            instance_label = name_value.strip()
    immich_section = raw.get("immich")
    if not isinstance(immich_section, dict):
        immich_section = {}
    mtime = CONFIG_PATH.stat().st_mtime
    return display, search, immediate, mtime, instance_label, immich_section


def _load_people() -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    raw = _load_toml(PEOPLE_PATH)
    if not isinstance(raw, dict):
        raise ValueError("people.toml debe contener un mapa simple")
    aliases_raw = raw.get("aliases")
    people = {}
    for name, person_id in raw.items():
        if name == "aliases":
            continue
        person_name = _ensure_str(name, "nombre de persona")
        person_value = _ensure_str(person_id, f"persona {person_name}")
        people[person_name] = person_value
    if not people:
        raise ValueError("people.toml está vacío")
    aliases = {}
    if aliases_raw is not None:
        if not isinstance(aliases_raw, dict):
            raise ValueError("aliases debe ser un objeto")
        for alias, members in aliases_raw.items():
            alias_name = _ensure_str(alias, "alias")
            if not isinstance(members, list | tuple):
                raise ValueError(f"aliases.{alias_name} debe ser una lista")
            aliases[alias_name] = tuple(_ensure_str(member, f"aliases.{alias_name}[]") for member in members)
    return people, aliases


def _expand_people(names: Iterable[str], people: Mapping[str, str], aliases: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    expanded: list[str] = []
    seen: set[str] = set()
    for raw_name in names:
        name = raw_name.strip()
        if not name:
            continue
        if name in people:
            if name not in seen:
                expanded.append(name)
                seen.add(name)
            continue
        group = aliases.get(name)
        if group is None:
            raise ValueError(f"Persona o alias desconocido: {name}")
        for member in group:
            if member not in people:
                raise ValueError(f"El alias {name} referencia una persona inexistente: {member}")
            if member not in seen:
                expanded.append(member)
                seen.add(member)
    if not expanded:
        raise ValueError("La lista de personas quedó vacía")
    return tuple(expanded)


def _format_toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return _format_toml_string(value)
    if isinstance(value, (list, tuple)):
        items = ", ".join(_format_toml_value(item) for item in value)
        return f"[{items}]"
    raise ValueError("Tipo no soportado al escribir TOML")


def _find_section_end(lines: list[str], section: str) -> int:
    header = f"[{section}]"
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == header:
            start = idx + 1
            break
    if start is None:
        return len(lines)
    idx = start
    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        idx += 1
    return idx


def _set_or_add_value(lines: list[str], section: str, key: str, value: str) -> tuple[list[str], bool]:
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)([^#\r\n]*)(.*)$")
    current_section = None
    section_found = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped.strip("[]").strip()
        if current_section == section:
            section_found = True
            if stripped.startswith("#"):
                continue
            match = pattern.match(line)
            if match:
                prefix, _, suffix = match.groups()
                newline = ""
                if line.endswith("\r\n"):
                    newline = "\r\n"
                elif line.endswith("\n"):
                    newline = "\n"
                lines[idx] = f"{prefix}{value}{suffix}{newline}"
                return lines, True
    if not section_found:
        lines.append(f"\n[{section}]\n{key} = {value}\n")
        return lines, True
    insert_idx = _find_section_end(lines, section)
    lines.insert(insert_idx, f"{key} = {value}\n")
    return lines, True


def _apply_updates(updates: list[tuple[str, str, str]]) -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    changed = False
    for section, key, value in updates:
        lines, updated = _set_or_add_value(lines, section, key, value)
        changed = changed or updated
    if not changed:
        return
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    temp_path = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.tmp")
    temp_path.write_text("".join(lines), encoding="utf-8")
    temp_path.replace(CONFIG_PATH)


def _parse_people_field(raw: str, people: Mapping[str, str], aliases: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    parts = [segment.strip() for segment in raw.split(",") if segment.strip()]
    if not parts:
        raise ValueError("Debes indicar al menos una persona o alias")
    return _expand_people(parts, people, aliases)


def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    message = None
    error = None
    people_error = None
    try:
        display_section, search_section, immediate_section, mtime, instance_name, immich_section = _read_config_sections()
    except ValueError as exc:
        display_section = {}
        search_section = {}
        immediate_section = {}
        mtime = 0
        instance_name = ""
        immich_section = {}
        error = str(exc)
    try:
        people_map, alias_map = _load_people()
    except ValueError as exc:
        people_map = {}
        alias_map = {}
        people_error = str(exc)
    current_mode = search_section.get("mode") if isinstance(search_section.get("mode"), str) else "random"
    default_people_list = search_section.get("default_people")
    if not isinstance(default_people_list, list):
        default_people_list = []
    if request.method == "POST":
        action = request.form.get("action")
        if action == "config":
            try:
                updates = []
                grayscale = bool(request.form.get("grayscale"))
                show_year = bool(request.form.get("show_year_overlay"))
                show_info = bool(request.form.get("show_info_overlay"))
                seconds_raw = request.form.get("seconds", "")
                brightness_raw = request.form.get("brightness", "")
                mode = request.form.get("mode", current_mode)
                if mode not in [value for value, _ in MODE_OPTIONS]:
                    raise ValueError("Modo inválido")
                try:
                    seconds = int(seconds_raw)
                except ValueError as exc:
                    raise ValueError("Duración debe ser un número entero") from exc
                if seconds < 1:
                    raise ValueError("La duración debe ser mayor o igual a 1")
                try:
                    brightness = float(brightness_raw)
                except ValueError as exc:
                    raise ValueError("Brillo debe ser un número") from exc
                if brightness <= 0:
                    raise ValueError("Brillo debe ser mayor que 0")
                smart_limit_raw = (request.form.get("smart_result_limit") or "").strip()
                smart_limit_current = search_section.get("smart_result_limit")
                if isinstance(smart_limit_current, int) and smart_limit_current > 0:
                    smart_limit_value = smart_limit_current
                else:
                    smart_limit_value = 100
                if smart_limit_raw:
                    try:
                        smart_limit_value = int(smart_limit_raw)
                    except ValueError as exc:
                        raise ValueError("Smart limit debe ser un número entero") from exc
                    if smart_limit_value < 1:
                        raise ValueError("Smart limit debe ser al menos 1")
                updates.extend([
                    ("display", "grayscale", _format_toml_value(grayscale)),
                    ("display", "seconds", _format_toml_value(seconds)),
                    ("display", "brightness", _format_toml_value(brightness)),
                    ("display", "show_year_overlay", _format_toml_value(show_year)),
                    ("display", "show_info_overlay", _format_toml_value(show_info)),
                ])
                updates.append(("search", "mode", _format_toml_string(mode)))
                if mode == "smart":
                    smart_query = (request.form.get("smart_query") or "").strip()
                    if not smart_query:
                        raise ValueError("Es necesario indicar una smart query")
                    updates.append(("search", "smart_query", _format_toml_string(smart_query)))
                updates.append(("search", "smart_result_limit", _format_toml_value(smart_limit_value)))
                default_people_raw = request.form.get("default_people", "")
                resolved = _parse_people_field(default_people_raw, people_map, alias_map)
                updates.append(("search", "default_people", _format_toml_value(resolved)))
                _apply_updates(updates)
                message = "Configuración guardada"
                display_section, search_section, immediate_section, mtime, instance_name, immich_section = _read_config_sections()
                default_people_list = search_section.get("default_people")
                if not isinstance(default_people_list, list):
                    default_people_list = []
                current_mode = search_section.get("mode") if isinstance(search_section.get("mode"), str) else current_mode
            except ValueError as exc:
                error = str(exc)
        elif action == "next":
            try:
                _apply_updates([("immediate_actions", "next", "1")])
                message = "Siguiente foto solicitada"
                _, _, immediate_section, _, _, _ = _read_config_sections()
            except ValueError as exc:
                error = str(exc)
        elif action == "favorite":
            try:
                _apply_updates([("immediate_actions", "favorite", "1")])
                display_section, search_section, immediate_section, mtime, instance_name, immich_section = _read_config_sections()
                message = "Favorito solicitado"
            except ValueError as exc:
                error = str(exc)
        elif action == "restart_holoconfig":
            try:
                subprocess.run(
                    ["sudo", "systemctl", "restart", "holoconfig.service"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                message = "holoconfig.service reiniciado"
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.strip() if exc.stderr else ""
                error = f"Error reiniciando HoloConfig: {stderr or exc}"
        elif action == "restart":
            try:
                subprocess.run(
                    ["sudo", "systemctl", "restart", "holodisplay.service"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                message = "holodisplay.service reiniciado"
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.strip() if exc.stderr else ""
                error = f"Error reiniciando servicio: {stderr or exc}"
        elif action == "shutdown":
            try:
                subprocess.run(
                    ["sudo", "shutdown", "now"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                message = "La Pi se está apagando"
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.strip() if exc.stderr else ""
                error = f"Error apagando la Pi: {stderr or exc}"
        else:
            error = "Acción desconocida"
    selected_alias = None
    favorite_note, favorite_err = _process_favorite_action(
        immediate_section,
        display_section,
        immich_section,
    )
    if favorite_note:
        display_section, search_section, immediate_section, mtime, instance_name, immich_section = _read_config_sections()
    message = _append_text(message, favorite_note)
    error = _append_text(error, favorite_err)
    for alias_name, members in alias_map.items():
        if len(members) == len(default_people_list) and set(members) == set(default_people_list):
            selected_alias = alias_name
            break
    frame_path = _current_frame_path_from_display(display_section)
    thumbnail_available = bool(frame_path and frame_path.exists())
    thumbnail_timestamp = frame_path.stat().st_mtime if thumbnail_available else 0
    portrait_mode = str(display_section.get("orientation", "")).lower() == "portrait"
    is_favorite, _ = _read_frame_metadata(frame_path)
    smart_limit_value = search_section.get("smart_result_limit")
    if not isinstance(smart_limit_value, int) or smart_limit_value < 1:
        smart_limit_value = 100
    context = {
        "grayscale": bool(display_section.get("grayscale")),
        "show_year_overlay": bool(display_section.get("show_year_overlay")),
        "show_info_overlay": bool(display_section.get("show_info_overlay")),
        "seconds": int(display_section.get("seconds", 15)) if isinstance(display_section.get("seconds"), int) else 15,
        "brightness": float(display_section.get("brightness", 1.0)) if isinstance(display_section.get("brightness"), (int, float)) else 1.0,
        "current_mode": current_mode,
        "modes": MODE_OPTIONS,
        "smart_query": search_section.get("smart_query") if isinstance(search_section.get("smart_query"), str) else "",
        "default_people": default_people_list,
        "aliases": alias_map,
        "selected_alias": selected_alias,
        "people_error": people_error,
        "immediate_next": bool(immediate_section.get("next", 0)),
        "last_updated": _format_timestamp(mtime) if mtime else "Desconocido",
        "message": message,
        "error": error,
        "sample_people": ", ".join(default_people_list[:3]) if default_people_list else "Jesus, Vero",
        "thumbnail_available": thumbnail_available,
        "thumbnail_timestamp": thumbnail_timestamp,
        "portrait_mode": portrait_mode,
        "is_favorite": is_favorite,
        "smart_limit": smart_limit_value,
        "instance_name": instance_name,
    }
    return render_template_string(PAGE_TEMPLATE, **context)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
