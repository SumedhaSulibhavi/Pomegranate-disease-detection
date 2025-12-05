from flask import Blueprint, request, jsonify
import os
import requests
import io
import base64
import tempfile
import speech_recognition as sr
from pydub import AudioSegment
from gtts import gTTS

from dotenv import load_dotenv   # ✅ ADD THIS
load_dotenv() 

from chatbot_backend.knowledge_base import get_knowledge_base


# -------------------------------------------------
#  BLUEPRINT SETUP (replaces app = Flask())
# -------------------------------------------------
chatbot_bp = Blueprint("chatbot_bp", __name__, url_prefix="/")


# --- Config ---
OPENROUTER_API_KEY = os.environ.get(
    "OPENROUTER_API_KEY",
    ""
)
OPENROUTER_MODEL = "google/gemma-2-9b-it"
knowledge_base = get_knowledge_base()


# -------------------------------------------------
#  AI HELPER
# -------------------------------------------------
def get_ai_response(prompt, model_name=OPENROUTER_MODEL):
    if not OPENROUTER_API_KEY:
        return "ERROR: OpenRouter API key is not configured."

    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return f"ERROR: OpenRouter request failed: {e}"


# -------------------------------------------------
#  TRANSLATION
# -------------------------------------------------
def translate_text(text, target_language):
    if not text:
        return ""

    tl = (target_language or "").lower()
    if tl in ["kn", "kannada"]:
        prompt = f"Translate this text strictly into Kannada script only: {text}"
    elif tl in ["hi", "hindi"]:
        prompt = f"Translate this text strictly into Hindi (Devanagari script): {text}"
    else:
        prompt = f"Translate this text into English: {text}"

    return get_ai_response(prompt)


# -------------------------------------------------
#  SPEECH-TO-TEXT
# -------------------------------------------------
def speech_to_text(audio_file, language_code="en"):
    recognizer = sr.Recognizer()
    try:
        raw = audio_file.read()
        audio_bytes = io.BytesIO(raw)
        audio_segment = AudioSegment.from_file(audio_bytes, format="webm")

        wav_io = io.BytesIO()
        audio_segment.export(wav_io, format="wav")
        wav_io.seek(0)

        with sr.AudioFile(wav_io) as source:
            audio = recognizer.record(source)

        lang_map = {"en": "en-US", "hi": "hi-IN", "kn": "kn-IN"}
        lang = lang_map.get(language_code.lower(), "en-US")

        return recognizer.recognize_google(audio, language=lang)
    except Exception as e:
        return f"ERROR: Audio processing failed. Details: {e}"


# -------------------------------------------------
#  TEXT-TO-SPEECH
# -------------------------------------------------
def text_to_speech(text, lang_code="en"):
    try:
        lang_map = {"en": "en", "hi": "hi", "kn": "kn"}
        lang = lang_map.get(lang_code.lower(), "en")
        tts = gTTS(text=text, lang=lang)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
            tts.save(temp_audio.name)
            with open(temp_audio.name, "rb") as f:
                audio_data = f.read()
        return audio_data
    except Exception as e:
        print(f"[TTS] Error generating speech: {e}")
        return None


# -------------------------------------------------
#  CORE CHAT LOGIC
# -------------------------------------------------
def get_bot_response(user_input, user_language="en"):
    user_language = (user_language or "en").lower()

    greetings = {
        "en": ["hi", "hello", "hey"],
        "hi": ["नमस्ते", "नमस्कार", "हाय", "हेलो"],
        "kn": ["ಹಾಯ್", "ಹೈ", "ನಮಸ್ಕಾರ", "ಹಲೋ"],
    }
    clean_input = user_input.strip().lower()
    if clean_input in greetings.get(user_language, []):
        if user_language == "kn":
            return "ಹಾಯ್! ದಾಳಿಂಬೆ ಬೆಳೆ ಅಥವಾ ರೋಗಗಳ ಬಗ್ಗೆ ಏನಾದರೂ ಕೇಳಿ."
        elif user_language == "hi":
            return "नमस्ते! अनार की खेती या रोगों के बारे में कुछ भी पूछिए।"
        else:
            return "Hi! Ask me anything about pomegranate farming or diseases."

    if user_language != "en":
        user_input_en = translate_text(user_input, "en")
    else:
        user_input_en = user_input

    response_data = None
    for key, value in knowledge_base.items():
        if key.lower() in user_input_en.lower():
            response_data = value
            break

    kb_hit = response_data is not None

    if kb_hit:
        if isinstance(response_data, dict):
            response = response_data.get(user_language) or response_data.get("en", "")
        else:
            response = response_data
    else:
        prompt = (
            "You are a specialized assistant for pomegranate plant health. "
            f"User asked: '{user_input_en}'. Provide an accurate, clear answer."
        )
        response = get_ai_response(prompt)

    needs_translation = (
        user_language != "en"
        and not response.startswith("ERROR:")
        and (not kb_hit or (isinstance(response_data, dict) and user_language not in response_data))
    )

    if needs_translation:
        response = translate_text(response, user_language)

    return response


# -------------------------------------------------
#  BLUEPRINT ROUTES
# -------------------------------------------------
@chatbot_bp.route("/chat", methods=["POST"])
def chat_route():
    data = request.json or {}
    user_message = data.get("user_message", "")
    language_code = data.get("language_code", "en")
    from_voice = data.get("from_voice", False)

    bot_response = get_bot_response(user_message, language_code)

    audio_base64 = None
    if from_voice:
        audio_data = text_to_speech(bot_response, language_code)
        if audio_data:
            audio_base64 = base64.b64encode(audio_data).decode("utf-8")

    return jsonify({"bot_response": bot_response, "audio_response": audio_base64})


@chatbot_bp.route("/speech", methods=["POST"])
def speech_route():
    if "file" not in request.files:
        return jsonify({"transcribed_text": "ERROR: No audio file uploaded"}), 400

    audio_file = request.files["file"]
    language_code = (request.form.get("language_code") or "en").lower()
    transcribed_text = speech_to_text(audio_file, language_code)

    if transcribed_text.startswith("ERROR:"):
        return jsonify({"transcribed_text": transcribed_text}), 500

    return jsonify({"transcribed_text": transcribed_text})
