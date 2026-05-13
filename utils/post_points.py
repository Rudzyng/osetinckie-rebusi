import requests
from constants import API_SECRET_KEY, API_URL
from utils.get_all_games import get_all_games


def post_points(user_id: str, amount: int) -> int:
    """Отправляет очки пользователя"""
    if not user_id:
        raise Exception("Не передан user_id")

    try:
        games = get_all_games()
        game_id = None

        for game in games:
            if game.get("gameTitle") == "Тестовая игра":
                game_id = game.get("gameId")
                break

        if not game_id:
            print("Игра 'Тестовая игра' не найдена, создаем новую?")
            return 0

        headers = {
            "X-API-Key": API_SECRET_KEY
        }

        response = requests.post(
            f"{API_URL}/users/{user_id}/games/{game_id}/points",
            json={"amount": amount},
            headers=headers
        )

        if response.status_code != 200:
            return 0

        data = response.json()
        return data.get("newTotalPoints", 0)

    except Exception as e:
        return 0