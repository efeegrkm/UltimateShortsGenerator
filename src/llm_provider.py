import ollama
import requests

from config import get_nanobanana2_api_key, get_ollama_base_url, get_gemini_model

_selected_model: str | None = None


def _client() -> ollama.Client:
    return ollama.Client(host=get_ollama_base_url())


def list_models() -> list[str]:
    """
    Lists all models available on the local Ollama server.

    Returns:
        models (list[str]): Sorted list of model names.
    """
    response = _client().list()
    return sorted(m.model for m in response.models)


def select_model(model: str) -> None:
    """
    Sets the model to use for all subsequent generate_text calls.

    Args:
        model (str): An Ollama model name (must be already pulled).
    """
    global _selected_model
    _selected_model = model


def get_active_model() -> str | None:
    """
    Returns the currently selected model, or None if none has been selected.
    """
    return _selected_model


def generate_text(prompt: str, model_name: str = None) -> str:
    """
    Generates text using Google's Gemini API.
    """
    api_key = get_nanobanana2_api_key()
    if not api_key:
        print("[!] Error: Google API key is not set. Please set 'nanobanana2_api_key' in config.json.")
        return ""

    if not model_name:
        model_name = get_gemini_model()
        
    if not model_name:
        model_name = "gemini-pro-latest"
    # -----------------------

    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    endpoint = f"{base_url}/{model_name}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.7,
        }
    }
    
    try:
        response = requests.post(endpoint, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        return data['candidates'][0]['content']['parts'][0]['text']
        
    except Exception as e:
        print(f"[!] Gemini API Error: {e}")
        if 'response' in locals() and response is not None:
            print(f"[!] Details: {response.text}")
        return ""
