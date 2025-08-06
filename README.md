# LyOi: Vietnamese Voice Assistant using Gemini AI & Edge TTS

**LyOi** is a simple Vietnamese voice assistant for your computer. Just say "Ly ơi" (or similar wake words), ask any question in Vietnamese, and get a natural voice answer powered by Google's Gemini AI and Microsoft's Edge TTS.

---

## Features

- **Hotword/Wake Word**: Listens for Vietnamese wake words (e.g., "Ly ơi", "Li ơi", etc.)
- **Speech Recognition**: Converts your voice to text (Google Speech Recognition, Vietnamese supported)
- **AI Response**: Sends your question to Gemini AI (Google Generative AI) and retrieves an intelligent answer
- **Text-to-Speech (TTS)**: Speaks the answer back in a natural Vietnamese voice (Edge TTS)
- **Async, Non-blocking Playback**: Supports long answers, splits text into natural blocks and reads aloud in sequence

---

## Requirements

- **Python 3.8+**
- **Microphone** for input, **Speakers** for output

### Python Packages

Install all requirements using pip:
```bash
pip install speechrecognition edge-tts playsound google-generativeai
