# -*- coding: utf-8 -*-
import os
import re
import io
import json
import time
import uuid
import asyncio
import unicodedata
from typing import Optional, Tuple

import numpy as np
import simpleaudio as sa
import speech_recognition as sr
from pydub import AudioSegment

# —— Gemini ——
from google import genai

# —— Google Assistant SDK (gRPC) ——
import grpc
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.transport.grpc import AuthMetadataPlugin
from google.assistant.embedded.v1alpha2 import embedded_assistant_pb2 as assistant_pb2
from google.assistant.embedded.v1alpha2 import embedded_assistant_pb2_grpc as assistant_grpc

# ====================== CẤU HÌNH =======================
WAKE_WORDS = [
    "ly ơi", "li ơi", "ly ới", "li ới", "ly oi", "li oi"
]
WAV_RATE = 16_000
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API_KEY   = os.getenv("GEMINI_API_KEY", "x")  # → nên đặt ENV GEMINI_API_KEY

# Assistant SDK
ASSISTANT_API_ENDPOINT = "embeddedassistant.googleapis.com"
TOKENS_PATH = os.getenv("ASSIST_TOKENS", "tokens.json")
CLIENT_CREDS_PATH = os.getenv("ASSIST_CREDS", "credentials.json")
DEVICE_MODEL_ID = os.getenv("ASSIST_DEVICE_MODEL_ID", "python-client")
DEVICE_ID       = os.getenv("ASSIST_DEVICE_ID", "python-device")
LANG_CODE       = os.getenv("LANG_CODE", "vi-VN")      # STT language
ASSISTANT_LANG  = os.getenv("ASSISTANT_LANG", "en-US")  # Mặc định trả lời tiếng Việt

# =================== TIỆN ÍCH CHUẨN HÓA ==================

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()

# =================== SPEECH → TEXT ======================

def speech_to_text(lang: str = "vi-VN", device_index: Optional[int] = None) -> Optional[str]:
    r = sr.Recognizer()
    with sr.Microphone(device_index=device_index) as source:
        print("Bạn nói đi, tôi đang nghe…")
        audio = r.listen(source)
        print("Đang xử lý…")
    try:
        text = r.recognize_google(audio, language=lang)
        print("Bạn vừa nói:", text)
        return text
    except Exception as e:
        print("Không nhận dạng được:", e)
        return None

# =================== TTS (Edge) – phát PCM trực tiếp ==================
import edge_tts

_DEF_VOICE = "vi-VN-HoaiMyNeural"

async def speak_stream(text: str, voice: str = _DEF_VOICE, rate: str = "+0%", pitch: str = "+0Hz", volume: str = "+0%"):
    """
    Stream audio từ edge-tts (MP3 bytes) -> giải mã trong RAM -> phát PCM 16kHz/16bit/mono ngay, không ghi file.
    """
    if not text:
        return
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch, volume=volume)
    mp3_buf = io.BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3_buf.write(chunk["data"])
    # Giải mã MP3 trong RAM rồi resample -> PCM 16k/16bit/mono
    mp3_buf.seek(0)
    seg = AudioSegment.from_file(mp3_buf, format="mp3").set_frame_rate(WAV_RATE).set_sample_width(2).set_channels(1)
    raw = seg.raw_data
    # Phát thẳng raw PCM (không file)
    wave_obj = sa.WaveObject(raw, num_channels=1, bytes_per_sample=2, sample_rate=WAV_RATE)
    play = wave_obj.play()
    play.wait_done()

def speak(text: str, voice: str = _DEF_VOICE):
    asyncio.run(speak_stream(text, voice))

# =================== GEMINI (ngắn gọn) ==================
SYS_BRIEF = (
    "Bạn là trợ lý trả lời gọn, súc tích, nếu là kĩ thuật thì trả lời thẳng vào vấn đề. "
)

def gemini_answer(prompt_text: str, api_key: str, model_name: str = MODEL_NAME) -> str:
    if not api_key:
        return "(Thiếu GEMINI_API_KEY)"
    try:
        client = genai.Client(api_key=api_key)
        text_in = f"{SYS_BRIEF}\n\nCâu hỏi: {prompt_text}"
        resp = client.models.generate_content(model=model_name, contents=text_in)
        return (getattr(resp, "text", None) or "").strip() or "(trống)"
    except Exception as e:
        print("Lỗi khi gọi Gemini:", e)
        return "Không lấy được trả lời từ Gemini!"

# ============ Router: Ưu tiên Assistant cho realtime queries =============
ROUTE_SYS = (
    "Bạn là bộ phân loại ý định cho trợ lý song công. "
    "Chỉ trả JSON một dòng với khóa: route, intent, confidence (0..1). "
    "route = 'assistant' nếu câu hỏi cần dữ liệu thời gian thực/thiết bị: thời tiết, giờ/ngày, tin tức, tỉ giá/giá vàng, "
    "kết quả trận đấu, điều khiển thiết bị/nhà thông minh, nhạc, hẹn giờ/báo thức/nhắc, điều hướng/chỉ đường, gọi/nhắn tin, lịch. "
    "Ngược lại route = 'gemini'."
)

ASSISTANT_KEYWORDS = [
    # thời gian/ngày
    r"mấy giờ", r"bây giờ", r"giờ hiện tại", r"hôm nay", r"thứ mấy", r"ngày bao nhiêu",
    # thời tiết
    r"thời tiết", r"nhiệt độ", r"mưa không", r"dự báo",
    # tin tức / realtime
    r"tin tức", r"tin mới", r"tỉ giá", r"giá vàng", r"giá usd", r"tỉ số", r"kết quả (trận|bóng)",
    # điều khiển thiết bị / nhà thông minh
    r"bật ", r"tắt ", r"đèn", r"quạt", r"máy lạnh", r"điều hòa", r"ổ cắm", r"thiết bị",
    # media/nhạc
    r"mở nhạc", r"phát nhạc", r"pause", r"tiếp tục", r"youtube", r"spotify",
    # hẹn giờ/nhắc việc
    r"hẹn giờ", r"báo thức", r"nhắc (.*)",
    # điều hướng/gọi/nhắn
    r"chỉ đường", r"đường đi", r"gọi ", r"nhắn tin",
    # lịch
    r"lịch", r"sự kiện", r"cuộc hẹn",
]

_ASSISTANT_REGEX = re.compile("|".join(ASSISTANT_KEYWORDS), re.IGNORECASE)


def is_assistant_query(utter: str) -> bool:
    return bool(_ASSISTANT_REGEX.search(utter or ""))


def decide_route_with_llm(utter: str, api_key: str, model_name: str = MODEL_NAME) -> dict:
    if not api_key:
        # Fallback đơn giản khi thiếu API
        return {"route": "assistant" if is_assistant_query(utter) else "gemini", "intent": "fallback", "confidence": 1}
    client = genai.Client(api_key=api_key)
    prompt = (
        f"{ROUTE_SYS}\n\n"
        f"Người dùng nói: \"{utter}\"\n"
        "Trả duy nhất JSON: {\"route\":\"assistant|gemini\",\"intent\":\"...\",\"confidence\":0.0..1.0}\n"
    )
    try:
        resp = client.models.generate_content(model=model_name, contents=prompt)
        raw = getattr(resp, "text", "").strip()
        j = json.loads(raw) if raw.startswith("{") else {}
    except Exception:
        j = {}
    if "route" not in j:
        j = {"route": "assistant" if is_assistant_query(utter) else "gemini", "intent": "fallback", "confidence": 1}
    return j

# ============ Google Assistant (text_query) =============
class AssistantClient:
    def __init__(self,
                 tokens_path: str = TOKENS_PATH,
                 client_creds_path: str = CLIENT_CREDS_PATH,
                 device_model_id: str = DEVICE_MODEL_ID,
                 device_id: str = DEVICE_ID):
        self.tokens_path = tokens_path
        self.client_creds_path = client_creds_path
        self.device_model_id = device_model_id
        self.device_id = device_id
        self.channel = None
        self.stub = None
        self._conv_state: Optional[bytes] = None
        self._init_grpc()

    def _load_credentials(self) -> Credentials:
        with open(self.tokens_path, 'r', encoding='utf-8') as f:
            token_data = json.load(f)
        client_id = token_data.get("client_id")
        client_secret = token_data.get("client_secret")
        if not client_id or not client_secret:
            with open(self.client_creds_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            installed = raw.get("installed") or raw.get("web") or {}
            client_id = installed.get("client_id")
            client_secret = installed.get("client_secret")
        creds = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/assistant-sdk-prototype"],
        )
        if not creds.valid:
            creds.refresh(Request())
        return creds

    def _init_grpc(self):
        creds = self._load_credentials()
        auth_plugin = AuthMetadataPlugin(creds, Request())
        ssl_creds = grpc.ssl_channel_credentials()
        auth_creds = grpc.metadata_call_credentials(auth_plugin)
        composite = grpc.composite_channel_credentials(ssl_creds, auth_creds)
        self.channel = grpc.secure_channel(ASSISTANT_API_ENDPOINT, composite)
        self.stub = assistant_grpc.EmbeddedAssistantStub(self.channel)

    def text_query(self, query: str, language_code: str = ASSISTANT_LANG) -> Tuple[str, bytes]:
        """Gửi text_query tới Assistant. Trả về (display_text, audio_pcm16)."""
        cfg = assistant_pb2.AssistConfig(
            audio_out_config=assistant_pb2.AudioOutConfig(
                encoding=assistant_pb2.AudioOutConfig.LINEAR16,
                sample_rate_hertz=WAV_RATE,
                volume_percentage=100,
            ),
            dialog_state_in=assistant_pb2.DialogStateIn(
                language_code=language_code,
                is_new_conversation=False if self._conv_state else True,
                conversation_state=self._conv_state or b"",
            ),
            device_config=assistant_pb2.DeviceConfig(
                device_id=self.device_id,
                device_model_id=self.device_model_id,
            ),
            text_query=query,
        )
        req = assistant_pb2.AssistRequest(config=cfg)
        audio_buf = bytearray()
        display_text = ""
        try:
            for resp in self.stub.Assist(iter([req])):
                if resp.dialog_state_out.conversation_state:
                    self._conv_state = resp.dialog_state_out.conversation_state
                if resp.dialog_state_out.supplemental_display_text:
                    display_text = resp.dialog_state_out.supplemental_display_text
                if resp.audio_out.audio_data:
                    audio_buf.extend(resp.audio_out.audio_data)
        except Exception as e:
            raise RuntimeError(f"Assistant lỗi: {e}")
        return display_text.strip(), bytes(audio_buf)

# ======================= PHÁT ÂM THANH ASSISTANT =========

def play_pcm16_mono(audio_bytes: bytes, sample_rate: int = WAV_RATE):
    if not audio_bytes:
        return
    wave_obj = sa.WaveObject(audio_bytes, num_channels=1, bytes_per_sample=2, sample_rate=sample_rate)
    play = wave_obj.play()
    play.wait_done()

# =========================== MAIN LOOP ===================
SYS_PROMPT = "Nói đi"

def main_loop(mic_device_index: Optional[int] = 0):
    if not API_KEY:
        print("[CẢNH BÁO] Chưa thiết lập GEMINI_API_KEY. Đặt biến môi trường hoặc sửa mã.")

    try:
        assistant = AssistantClient()
    except Exception as e:
        print("[Assistant] KHÔNG khởi tạo được:", e)
        assistant = None

    print("Nói 'Ly ơi' để kích hoạt trợ lý…")

    while True:
        heard = speech_to_text(lang=LANG_CODE, device_index=mic_device_index)
        if not heard:
            print("Không nhận diện được tiếng nói…\n"); time.sleep(0.4); continue

        low = strip_accents(heard)
        if any(strip_accents(w) in low for w in WAKE_WORDS):
            print("Wake word đã kích hoạt!")
            speak(SYS_PROMPT)

            question = speech_to_text(lang=LANG_CODE, device_index=mic_device_index)
            if not question:
                speak("Em chưa nghe rõ câu hỏi của bạn!")
                continue

            # 1) Router: ưu tiên Assistant cho realtime queries
            force_assistant = is_assistant_query(question)
            route = decide_route_with_llm(question, api_key=API_KEY)
            try:
                conf = float(route.get("confidence", 0) or 0)
            except Exception:
                conf = 0.0
            print(f"→ Router (LLM): {route} | force_assistant={force_assistant}")

            try_assistant = (force_assistant or (route.get("route") == "assistant" and conf >= 0.50)) and (assistant is not None)

            if try_assistant:
                print("→ Dùng Google Assistant")
                try:
                    display_text, audio = assistant.text_query(question, language_code=ASSISTANT_LANG)
                    if audio:
                        play_pcm16_mono(audio, WAV_RATE)
                    if display_text:
                        print("Assistant:", display_text)
                    else:
                        print("Assistant: (không có text, đã phát audio)")
                except Exception as e:
                    print("Assistant lỗi, fallback Gemini:", e)
                    reply = gemini_answer(question, api_key=API_KEY)
                    print("Gemini:", reply)
                    speak(reply)
            else:
                if (route.get("route") == "assistant" and assistant is None):
                    print("→ Muốn dùng Assistant nhưng client chưa sẵn sàng → fallback Gemini")
                else:
                    print("→ Dùng Gemini")
                reply = gemini_answer(question, api_key=API_KEY)
                print("Gemini:", reply)
                speak(reply)

            print("Chờ bạn gọi 'Ly ơi' lần nữa…\n")

        else:
            print("Không phải wake word, tiếp tục lắng nghe…\n")
        time.sleep(0.3)

# ========================= CHẠY THỬ =====================
if __name__ == "__main__":
    # Đổi chỉ số micro nếu cần (dùng sr.Microphone.list_microphone_names() để liệt kê)
    main_loop(mic_device_index=0)
