import re

def get_str_from_food_dict(food_dict: dict):
    """Convert a dictionary of food items and quantities to a string."""
    return ", ".join([f"{int(value)} {key}" for key, value in food_dict.items()])

def extract_session_id(session_str: str):
    """Extract the session ID from a session string."""
    match = re.search(r"/sessions/([^/]+)/contexts/", session_str)
    if match:
        return match.group(1)  # Return only the session ID part
    return ""
