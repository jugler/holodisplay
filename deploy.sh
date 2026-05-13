#!/bin/zsh

set -e

REMOTE_DIR="~/HoloDisplay"
PROJECT_DIR="/Users/jugler/code/HoloDisplay"
PEOPLE_DIR="$PROJECT_DIR/people"

if [[ ! -d "$PEOPLE_DIR" ]]; then
  echo "No existe la carpeta people/ en $PEOPLE_DIR. Crea people/*.toml (p. ej. export_people.py -o people/main_people.toml)" >&2
  exit 1
fi

typeset -A HOST_CONFIGS
HOST_CONFIGS=(
  "pi@frame" "$PROJECT_DIR/config.frame.toml"
  "pi@holoframe" "$PROJECT_DIR/config.holoframe.toml"
  #"pi@holothot.local" "$PROJECT_DIR/config.holothot.toml"
)

for REMOTE_HOST CONFIG_PATH in ${(kv)HOST_CONFIGS}; do
  if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "No existe el archivo de configuracion para $REMOTE_HOST: $CONFIG_PATH" >&2
    exit 1
  fi

  echo "Deploy a $REMOTE_HOST usando $(basename "$CONFIG_PATH")"

  ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DIR"
rsync -av \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "$PROJECT_DIR/HoloDisplay.py" \
  "$PROJECT_DIR/splashscreen.py" \
  "$PROJECT_DIR/holo_display" \
  "$PROJECT_DIR/center_guide.py" \
  "$PROJECT_DIR/export_people.py" \
  "$PROJECT_DIR/HoloConfigServer.py" \
  "$PROJECT_DIR/assets" \
  "$REMOTE_HOST:$REMOTE_DIR/"
  rsync -av \
    "$CONFIG_PATH" \
    "$REMOTE_HOST:$REMOTE_DIR/"
  rsync -av \
    "$PROJECT_DIR/people" \
    "$REMOTE_HOST:$REMOTE_DIR/"
  ssh "$REMOTE_HOST" "mv $REMOTE_DIR/$(basename "$CONFIG_PATH") $REMOTE_DIR/config.toml"
done
