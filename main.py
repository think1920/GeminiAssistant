import speech_recognition as sr
import google as genai
import time
import asyncio
import edge_tts
import os
import re
from playsound import playsound  

WAKE_WORDS = ["ly ơi", "li ơi", "ly ới", "li ới", "ly oi", "li oi"]

api_key = "Ur api" 
if not api_key:
    print("Lỗi: Bạn chưa cấu hình API key Gemini!")
    exit()

def speech_to_text(lang='vi-VN'):
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Bạn nói đi, tôi đang nghe...")
        audio = r.listen(source)
        print("Đang xử lý...")
    try:
        text = r.recognize_google(audio, language=lang)
        print("Bạn vừa nói:", text)
        return text
    except Exception as e:
        print("Không nhận dạng được:", e)
        return None

def get_gemini_response(prompt_text, api_key, model_name="gemini-2.5-flash"):
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt_text
        )
        return response.text
    except Exception as e:
        print("Lỗi khi gọi Gemini:", e)
        return "Không lấy được trả lời từ Gemini!"

def clean_markdown(text):
    text = re.sub(r"\*\*|\*", "", text)
    text = text.replace("•", "-")
    return text

def split_by_200_words_and_sentence(text: str, max_words: int = 36):
    """
    Chia chuỗi thành các khối ≤ `max_words` từ,
    nhưng luôn cắt ở ranh giới câu ('.', '!', '?') hoặc xuống dòng.
    """
    tokens = re.findall(r'\S+|\n', text)
    
    blocks, current, word_count = [], [], 0
    for tok in tokens:
        current.append(tok)

        if tok != '\n':
            word_count += 1

        reached_limit = word_count >= max_words
        sentence_end  = tok == '\n' or tok.endswith(('.', '!', '?'))
        if reached_limit and sentence_end:
            blocks.append(_normalize_block(current))
            current, word_count = [], 0

    if current:
        blocks.append(_normalize_block(current))

    return blocks

def _normalize_block(token_list):
    """Ghép token giữ nguyên xuống dòng, xoá thừa dấu cách."""
    block = ' '.join(token_list)
    block = (block.replace(' \n', '\n')     
                   .replace('\n ', '\n')     
                   .strip())
    # gộp nhiều khoảng trắng liên tiếp
    block = re.sub(r'[ ]{2,}', ' ', block)
    return block

async def _tts_producer(blocks, voice, q: asyncio.Queue):
    """Sinh file TTS và đẩy tên file vào hàng đợi."""
    for i, block in enumerate(blocks):
        fn = f"tts_temp_{i}.mp3"
        await edge_tts.Communicate(block, voice).save(fn)
        await q.put(fn)         
    await q.put(None)           


async def _audio_player(q: asyncio.Queue):
    """Nhận file từ hàng đợi, phát rồi xoá."""
    while True:
        fn = await q.get()
        if fn is None:        
            break
        await asyncio.to_thread(playsound, fn)
        os.remove(fn)


async def speak_blocks(text, voice="vi-VN-HoaiMyNeural", max_words=36):
    blocks = split_by_200_words_and_sentence(text, max_words=max_words)
    queue  = asyncio.Queue(maxsize=3)   

    producer_task = asyncio.create_task(_tts_producer(blocks, voice, queue))
    await _audio_player(queue)
    await producer_task          


def speak(text, voice="vi-VN-HoaiMyNeural", max_words=36):
    asyncio.run(speak_blocks(text, voice, max_words))


if __name__ == "__main__":
    print("Nói 'Ly ơi' để kích hoạt trợ lý...")

    while True:
        user_text = speech_to_text(lang='vi-VN')
        if user_text:
            user_text_lower = user_text.lower()
            if any(w in user_text_lower for w in WAKE_WORDS):
                print("Wake word đã kích hoạt!")
                speak("Dạ, em nghe nè, bạn hỏi gì ạ?", voice="vi-VN-HoaiMyNeural")

                question = speech_to_text(lang='vi-VN')
                if question:
                    reply = get_gemini_response(question, api_key)
                    reply_to_read = clean_markdown(reply)
                else:
                    reply_to_read = "Em chưa nghe rõ câu hỏi của bạn!"
                print("Gemini trả lời:", reply)
                speak(reply_to_read, voice="vi-VN-HoaiMyNeural")
                print("Chờ bạn gọi 'Ly ơi' lần nữa...\n")
            else:
                print("Không phải wake word, tiếp tục lắng nghe...\n")
        else:
            print("Không nhận diện được tiếng nói...\n")
        time.sleep(0.5)
