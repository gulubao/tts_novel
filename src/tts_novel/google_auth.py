"""Google authentication helpers shared by realtime and batch Gemini clients."""

from google.genai import errors


def is_api_key_invalid_error(exc: BaseException) -> bool:
    """Return whether a google-genai exception is an invalid API-key failure."""
    if not isinstance(exc, errors.ClientError):
        return False
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        error = details.get("error")
        if isinstance(error, dict):
            for detail in error.get("details", []):
                if isinstance(detail, dict) and detail.get("reason") == "API_KEY_INVALID":
                    return True
            message = error.get("message")
            if isinstance(message, str) and "API key expired" in message:
                return True
    return "API_KEY_INVALID" in str(exc)
