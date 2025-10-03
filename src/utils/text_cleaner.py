import re

def remove_think_tags(text: str) -> str:
    """Remove <thinking>...</thinking> tags from the text."""
    return re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()