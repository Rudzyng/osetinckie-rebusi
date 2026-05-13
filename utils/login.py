import requests
from constants import API_SECRET_KEY, API_URL


def login(email: str, password: str) -> str:
    headers = {
        "X-API-Key": API_SECRET_KEY
    }

    user_data = {"email": email, "password": password}

    try:
        response = requests.post(f"{API_URL}/account/login", json=user_data, headers=headers)
        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict):
            user_id = data.get("userId")
            if user_id:
                return str(user_id)

        if isinstance(data, dict) and "id" in data:
            return str(data["id"])

        raise ValueError("Не удалось получить ID пользователя из ответа API")

    except requests.exceptions.RequestException as e:
        raise Exception(f"Ошибка соединения с API: {e}")
    except ValueError as e:
        raise e
    except Exception as e:
        raise Exception(f"Неизвестная ошибка: {e}")