#!/bin/bash
set -e

mkdir -p middleware/static/icons
BG="#0d1b2a"
SIZE="60x60"

# Twemoji unicodes
# 2600 = ☀️ (clear)
# 1f324 = 🌤️ (partly cloudy)
# 2601 = ☁️ (cloudy)
# 1f327 = 🌧️ (rain)
# 26c8 = ⛈️ (storm)
# 2744 = ❄️ (snow)

declare -A icons=(
  ["clear"]="2600"
  ["partly"]="1f324"
  ["clouds"]="2601"
  ["rain"]="1f327"
  ["storm"]="26c8"
  ["snow"]="2744"
)

for name in "${!icons[@]}"; do
  code="${icons[$name]}"
  echo "Downloading $name ($code)..."
  curl -s -L "https://raw.githubusercontent.com/twitter/twemoji/master/assets/svg/${code}.svg" -o /tmp/${name}.svg
  
  # Check if svg is empty (fallback code handling if missing)
  if [ ! -s /tmp/${name}.svg ]; then
      # Fallback to alternative names if Twemoji updated
      curl -s -L "https://raw.githubusercontent.com/twitter/twemoji/master/assets/svg/${code}-fe0f.svg" -o /tmp/${name}.svg
  fi

  echo "Converting $name to JPG..."
  # Convert SVG to PNG at desired size, then composite over background and save as JPG
  magick -background none -size $SIZE /tmp/${name}.svg /tmp/${name}.png
  magick -size $SIZE xc:"$BG" /tmp/${name}.png -composite -quality 90 middleware/static/icons/${name}.jpg
done
echo "Done!"
