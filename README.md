# Ly Voice Assistant: A Hybrid Duplex Voice Assistant for Vietnamese with Intent-Based Routing between Gemini and Google Assistant SDK

**Ly** is an open-source, always-listening, wake-word-activated voice assistant designed primarily for Vietnamese users. It combines the concise reasoning capabilities of Google Gemini (gemini-1.5-flash / 2.0-flash-experimental) with the real-time accuracy and device-control features of the official Google Assistant Embedded SDK, using an intelligent hybrid routing mechanism.

The system achieves near-duplex interaction (listen → route → respond → continue listening) entirely in Python, with zero intermediate audio files, low latency, and high-quality Vietnamese neural TTS.

## Key Features

- **Wake-word activation** ("Ly ơi", "Li ơi", "Ly ới", and phonetic variants) using simple offline string matching on Google STT transcriptions (robust and zero-extra dependency).
- **Hybrid backend routing**:
  - Fast regex-based pre-filter for obvious real-time intents (time, weather, news, device control, alarms, navigation, etc.).
  - LLM-based intent classifier (Gemini) for ambiguous or complex queries, outputting structured JSON `{route, intent, confidence}`.
  - Automatic fallback to Gemini if Google Assistant fails or is unavailable.
- **Real-time queries** handled by the official Google Assistant Embedded SDK (gRPC) – the same backend used by Google Nest devices).
- **General knowledge and reasoning** handled by Gemini with a concise-response system prompt.
- **High-quality streaming TTS** using Microsoft Edge-TTS (vi-VN-HoaiMyNeural default), decoded in-memory with pydub and played directly as raw PCM via simpleaudio – no temporary files, instant playback.
- **Conversational state persistence** across turns when using Google Assistant (maintains context for follow-up questions).
- Fully configurable via environment variables.

## Architecture Overview

```
Microphone → speech_recognition (Google STT, vi-VN)
          ↓
Wake-word detection (offline)
          ↓ (detected)
Speak "Nói đi" → User question → STT
          ↓
Router (regex + Gemini classifier) → "assistant" or "gemini"
          ↓
Google Assistant SDK (gRPC)          Gemini API (REST)
(text_query + audio response)        (generate_content)
          ↓                                   ↓
Play PCM 16kHz mono (simpleaudio)    edge-tts → pydub → PCM → simpleaudio
          ↓
Ready for next wake word
```

The routing layer ensures that queries requiring up-to-date information or device actions are handled by Google Assistant, while open-ended or technical questions are sent to Gemini, achieving the strengths of both systems with minimal latency.

## Requirements

- Python 3.9+
- A working microphone
- Google Cloud OAuth2 credentials for the Assistant SDK (see Setup)

Tested on Windows 11 and Linux (Ubuntu 22.04/24.04). Works on macOS with minor audio driver adjustments.

## Installation & Setup

```bash
pip install speechrecognition pydub simpleaudio edge-tts google-generativeai grpcio grpcio-tools google-auth google-auth-oauthlib
```

### 1. Gemini API Key
```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

### 2. Google Assistant SDK Credentials

1. Go to Google Cloud Console → APIs & Services → Enable "Google Assistant API"
2. Create OAuth 2.0 Client ID (Application type: Desktop app) → download `credentials.json`
3. Register a device model & device in the Actions Console:
   - Actions on Google → Develop → Device registration
   - Create Model ID and Device ID
4. Run once:
```bash
python -c "import google.oauth2.credentials, json; \
    creds = google.oauth2.credentials.Credentials(None, \
    client_id='YOUR_CLIENT_ID', \
    client_secret='YOUR_CLIENT_SECRET', \
    token_uri='https://oauth2.googleapis.com/token', \
    scopes=['https://www.googleapis.com/auth/assistant-sdk-prototype']); \
    creds.refresh(google.auth.transport.requests.Request()); \
    data = {'access_token': creds.token, 'refresh_token': creds.refresh_token, \
            'client_id': creds.client_id, 'client_secret': creds.client_secret}; \
    json.dump(data, open('tokens.json', 'w'))"
```
   (First run will open browser for consent)

5. Set environment variables (or modify script defaults):
```bash
export ASSIST_CREDS="path/to/credentials.json"
export ASSIST_TOKENS="path/to/tokens.json"
export ASSIST_DEVICE_MODEL_ID="your-model-id"
export ASSIST_DEVICE_ID="your-device-id"
export LANG_CODE="vi-VN"          # STT language
export ASSISTANT_LANG="vi-VN"     # Assistant response language (vi-VN works well)
```

## Usage

```bash
python ly_assistant.py
```

Say "Ly ơi" → wait for "Nói đi" → ask anything in Vietnamese.

Examples:

- "Ly ơi, mấy giờ rồi?" → Google Assistant (real-time clock)
- "Ly ơi, thời tiết Hà Nội hôm nay thế nào?" → Google Assistant
- "Ly ơi, giải thích transformer architecture" → Gemini (concise technical answer)
- "Ly ơi, bật đèn phòng khách" → Google Assistant (if you have linked smart home devices)

## Customization

- Change default voice: modify `_DEF_VOICE = "vi-VN-NamMinhNeural"` or pass `voice=` parameter
- Adjust TTS speed/pitch: modify `rate`, `pitch`, `volume` in `speak()` call
- Add more Assistant-only keywords in `ASSISTANT_KEYWORDS` list
- Change wake words in `WAKE_WORDS`

## Limitations & Notes

- Google Assistant SDK currently supports only a limited set of languages for audio output; Vietnamese audio works reliably as of 2025.
- Real-time queries require internet connection and valid Assistant credentials.
- The Assistant SDK is officially supported for prototyping and personal use.
