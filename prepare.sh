#!/bin/bash

SRC="$1"
DST="$2"

if [ -z "$SRC" ] || [ -z "$DST" ]; then
  echo "Uso: ./prepare_pi_videos.sh origen destino"
  exit 1
fi

mkdir -p "$DST"

for file in "$SRC"/*.mp4; do
  name=$(basename "$file")

  echo "Procesando $name"

  ffmpeg -y -i "$file" \
  -vf "transpose=2,scale=1080:1920,fps=30" \
  -c:v libx264 \
  -profile:v high \
  -level 4.0 \
  -preset fast \
  -b:v 4M \
  -maxrate 4M \
  -bufsize 8M \
  -pix_fmt yuv420p \
  -movflags +faststart \
  -an \
  "$DST/$name"

done

echo "Listo."