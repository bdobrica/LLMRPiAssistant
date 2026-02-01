#!/bin/bash
# Generate audio prompts using OpenAI TTS API

# Output directory
OUTPUT_DIR="$(dirname "$0")"

# Config file path (relative to this script)
CONFIG_FILE="$OUTPUT_DIR/../../config.ini"

# Default values
DEFAULT_VOICE="alloy"
DEFAULT_API_KEY="your-api-key-here"

# Read from config.ini if it exists
if [ -f "$CONFIG_FILE" ]; then
  echo "Reading configuration from $CONFIG_FILE"
  
  # Extract tts_voice from config.ini (under [openai] section)
  VOICE=$(grep -A 20 '^\[openai\]' "$CONFIG_FILE" | grep '^tts_voice' | cut -d'=' -f2 | tr -d ' ' | head -n1)
  
  # Extract api_key from config.ini (under [openai] section)
  API_KEY=$(grep -A 20 '^\[openai\]' "$CONFIG_FILE" | grep '^api_key' | cut -d'=' -f2 | tr -d ' ' | head -n1)
  
  # Use extracted values or fall back to defaults
  VOICE="${VOICE:-$DEFAULT_VOICE}"
  OPENAI_API_KEY="${API_KEY:-$OPENAI_API_KEY}"
else
  echo "Config file not found at $CONFIG_FILE, using defaults"
  VOICE="$DEFAULT_VOICE"
fi

# Allow environment variable to override
OPENAI_API_KEY="${OPENAI_API_KEY:-$DEFAULT_API_KEY}"
VOICE="${VOICE:-$DEFAULT_VOICE}"

echo "Generating audio prompts with voice: $VOICE"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Generate offline.mp3
echo "Generating offline.mp3..."
curl -X POST "https://api.openai.com/v1/audio/speech" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "input": "Hey! I'\''m having trouble connecting to the internet. Could you check my connection?",
    "voice": "'"$VOICE"'",
    "response_format": "mp3"
  }' \
  --output "$OUTPUT_DIR/offline.mp3"

if [ -f "$OUTPUT_DIR/offline.mp3" ]; then
  echo "✓ offline.mp3 created ($(du -h "$OUTPUT_DIR/offline.mp3" | cut -f1))"
else
  echo "✗ Failed to create offline.mp3"
fi

echo ""

# Generate online.mp3
echo "Generating online.mp3..."
curl -X POST "https://api.openai.com/v1/audio/speech" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "input": "All set — I'\''m back online! What can I help you with?",
    "voice": "'"$VOICE"'",
    "response_format": "mp3"
  }' \
  --output "$OUTPUT_DIR/online.mp3"

if [ -f "$OUTPUT_DIR/online.mp3" ]; then
  echo "✓ online.mp3 created ($(du -h "$OUTPUT_DIR/online.mp3" | cut -f1))"
else
  echo "✗ Failed to create online.mp3"
fi

echo ""
echo "Done! Audio prompts generated."
