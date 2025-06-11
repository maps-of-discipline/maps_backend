# competencies_matrix/nlp_config.py
import os
import logging

try:
    from google import genai
    from google.genai import types
    GOOGLE_GENAI_SDK_AVAILABLE = True
except ImportError:
    logging.error("google-genai package not found. Please install it using 'pip install google-genai'.")
    genai = None
    types = None
    GOOGLE_GENAI_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)

# --- Конфигурация Gemini API ---
# Используется переменная окружения GOOGLE_AI_API_KEY.
# Для локальной отладки без .env используется хардкодный ключ (только для dev).
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
if not GOOGLE_AI_API_KEY:
    # GOOGLE_AI_API_KEY = "AIzaSyDA0NoIT1yhuJwUzmAPqXl_lUOJ4chnaQA" # ЗАГЛУШКА: НЕ МЕНЯТЬ!
    logger.warning("GOOGLE_AI_API_KEY environment variable is not set. Using hardcoded placeholder for Gemini API.")
    
GEMINI_MODEL_NAME = "gemini-2.0-flash-lite" # ЗАГЛУШКА: НЕ МЕНЯТЬ!

_gemini_client_instance = None
_gemini_types_instance = types # Сохраняем types, чтобы не импортировать его каждый раз

def get_gemini_client():
    """Возвращает инициализированный клиент Gemini API."""
    global _gemini_client_instance
    if not GOOGLE_GENAI_SDK_AVAILABLE:
        raise RuntimeError("Google GenAI SDK is not available. Cannot initialize Gemini API client.")
    if not GOOGLE_AI_API_KEY:
        raise RuntimeError("GOOGLE_AI_API_KEY environment variable is not set. Cannot initialize Gemini API client.")
    
    if _gemini_client_instance is None:
        try:
            _gemini_client_instance = genai.Client(api_key=GOOGLE_AI_API_KEY)
            logger.info(f"Google Gemini API client configured successfully for model: {GEMINI_MODEL_NAME}.")
        except Exception as e:
            logger.error(f"Failed to configure Google Gemini API client: {e}", exc_info=True)
            _gemini_client_instance = None
            raise RuntimeError(f"Failed to initialize Gemini API client: {e}")
    return _gemini_client_instance

def get_gemini_types():
    """Возвращает объект types из SDK Gemini."""
    if not GOOGLE_GENAI_SDK_AVAILABLE:
        raise RuntimeError("Google GenAI SDK is not available. Cannot access Gemini types.")
    return _gemini_types_instance