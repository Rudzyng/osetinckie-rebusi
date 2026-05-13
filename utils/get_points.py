import requests
from constants import API_SECRET_KEY, API_URL


def get_points(user_id: str) -> int:
    """Получает очки пользователя по его ID"""
    headers = {
        "X-API-Key": API_SECRET_KEY
    }

    if not user_id:
        raise Exception("Не передан user_id")

    try:
        response = requests.get(f"{API_URL}/users/{user_id}/points", headers=headers)

        if response.status_code != 200:
            return 0

        data = response.json()

        if isinstance(data, int):
            return data
        elif isinstance(data, dict):
            return data.get("points", 0)

        return 0
    except Exception as e:
        return 0