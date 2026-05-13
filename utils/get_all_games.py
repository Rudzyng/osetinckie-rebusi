from typing import TypedDict, List, Optional
import requests
from constants import API_URL, API_SECRET_KEY


class Game(TypedDict):
    gameTitle: str
    gameId: int
    gamePublicationDate: str


def get_all_games() -> List[Game]:
    """Получает список всех игр пользователя"""
    headers = {
        "X-API-Key": API_SECRET_KEY
    }

    try:
        response = requests.get(f"{API_URL}/games/my", headers=headers)
        if response.status_code != 200:
            print(f"Ошибка получения игр: статус {response.status_code}")
            return []

        data = response.json()

        if isinstance(data, list):
            valid_games = []
            for game in data:
                if isinstance(game, dict) and 'gameId' in game and 'gameTitle' in game:
                    valid_games.append(game)
            return valid_games
        elif isinstance(data, dict) and 'games' in data and isinstance(data['games'], list):
            return data['games']
        else:
            return []

    except requests.exceptions.RequestException as e:
        return []
    except ValueError as e:
        return []
    except Exception as e:
        return []