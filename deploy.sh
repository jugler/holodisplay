#!/bin/zsh

set -e

REMOTE_HOST="pi@holodisplay"
REMOTE_DIR="~/HoloDisplay"

ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DIR"
rsync -av \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  /Users/jugler/code/HoloDisplay/HoloDisplay.py \
  /Users/jugler/code/HoloDisplay/config.toml \
  /Users/jugler/code/HoloDisplay/holo_display \
  "$REMOTE_HOST:$REMOTE_DIR/"
