#!/bin/sh
# VieNeu-TTS for the assistant's voice (docs/LLM_PROVIDER.md §TTS): an OpenAI-compatible /v1/audio/speech on 127.0.0.1:8780.
# Started by ./run.sh (worker "tts"). Does nothing when it is already up or VieNeu is not installed (the web stays text-only).
# Env: VIENEU_DIR (default ~/vieneu-tts), TTS_GPU (default 5, the CUDA device index), TTS_PORT (default 8780).
DIR=${VIENEU_DIR:-$HOME/vieneu-tts}
PORT=${TTS_PORT:-8780}
[ -d "$DIR" ] || { echo "[tts] $DIR missing, skip"; exit 0; }
curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/v1/voices" && { echo "[tts] already up on :$PORT"; exit 0; }
cd "$DIR" || exit 1
CUDA_VISIBLE_DEVICES=${TTS_GPU:-5} HOST=127.0.0.1 PORT=$PORT exec uv run python -m apps.openai_speech
