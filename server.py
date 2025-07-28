#!/usr/bin/env python3
"""
Serwer gry "Guess the Number" - demonstracja systemu rozproszonego
Wymagania: pip install websockets asyncio
"""

import asyncio
import websockets
import json
import random
import logging
from typing import Dict, Set, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Player:
    websocket: websockets.WebSocketServerProtocol
    name: str
    score: int = 0
    guesses: int = 0


@dataclass
class GameState:
    secret_number: int
    min_range: int = 1
    max_range: int = 100
    max_guesses: int = 10
    is_active: bool = True
    winner: Optional[str] = None
    round_number: int = 1


class DistributedGameServer:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.game_state = GameState(secret_number=random.randint(1, 100))
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()

    async def register_player(self, websocket, name: str):
        """Rejestracja nowego gracza"""
        if name in self.players:
            await self.send_message(websocket, {
                "type": "error",
                "message": f"Gracz o nazwie '{name}' już istnieje!"
            })
            return False

        self.players[name] = Player(websocket=websocket, name=name)
        self.connected_clients.add(websocket)

        logger.info(f"Gracz {name} dołączył do gry")

        # Powiadom gracza o dołączeniu
        await self.send_message(websocket, {
            "type": "joined",
            "message": f"Witaj {name}! Zgadnij liczbę od {self.game_state.min_range} do {self.game_state.max_range}",
            "game_info": {
                "range": [self.game_state.min_range, self.game_state.max_range],
                "max_guesses": self.game_state.max_guesses,
                "round": self.game_state.round_number
            }
        })

        # Powiadom wszystkich o nowym graczu
        await self.broadcast_message({
            "type": "player_joined",
            "player": name,
            "total_players": len(self.players)
        }, exclude=websocket)

        # Wyślij aktualny stan gry
        await self.send_game_state(websocket)
        return True

    async def handle_guess(self, websocket, player_name: str, guess: int):
        """Obsługa zgadywania liczby"""
        if not self.game_state.is_active:
            await self.send_message(websocket, {
                "type": "error",
                "message": "Gra nie jest aktywna!"
            })
            return

        if player_name not in self.players:
            return

        player = self.players[player_name]
        player.guesses += 1

        # Sprawdź czy zgadł
        if guess == self.game_state.secret_number:
            player.score += max(1, self.game_state.max_guesses - player.guesses + 1)
            self.game_state.winner = player_name
            self.game_state.is_active = False

            await self.broadcast_message({
                "type": "game_won",
                "winner": player_name,
                "secret_number": self.game_state.secret_number,
                "guesses_taken": player.guesses,
                "points_earned": max(1, self.game_state.max_guesses - player.guesses + 1)
            })

            # Automatycznie rozpocznij nową rundę po 5 sekundach
            asyncio.create_task(self.start_new_round())

        elif player.guesses >= self.game_state.max_guesses:
            await self.send_message(websocket, {
                "type": "out_of_guesses",
                "message": f"Wykorzystałeś wszystkie próby! Liczba to: {self.game_state.secret_number}"
            })
        else:
            hint = "za duża" if guess > self.game_state.secret_number else "za mała"
            remaining = self.game_state.max_guesses - player.guesses

            await self.send_message(websocket, {
                "type": "guess_result",
                "guess": guess,
                "hint": hint,
                "remaining_guesses": remaining,
                "message": f"Liczba {guess} jest {hint}. Pozostało prób: {remaining}"
            })

            # Powiadom innych o próbie
            await self.broadcast_message({
                "type": "player_guessed",
                "player": player_name,
                "guess": guess,
                "remaining": remaining
            }, exclude=websocket)

    async def start_new_round(self):
        """Rozpocznij nową rundę"""
        await asyncio.sleep(5)  # Pauza między rundami

        self.game_state.secret_number = random.randint(
            self.game_state.min_range,
            self.game_state.max_range
        )
        self.game_state.is_active = True
        self.game_state.winner = None
        self.game_state.round_number += 1

        # Zresetuj liczbę prób dla wszystkich graczy
        for player in self.players.values():
            player.guesses = 0

        await self.broadcast_message({
            "type": "new_round",
            "round": self.game_state.round_number,
            "message": f"Nowa runda #{self.game_state.round_number}! Zgadnij nową liczbę!"
        })

        logger.info(
            f"Rozpoczęto rundę #{self.game_state.round_number}, sekretna liczba: {self.game_state.secret_number}")

    async def send_game_state(self, websocket):
        """Wyślij aktualny stan gry"""
        leaderboard = sorted(
            [(name, player.score) for name, player in self.players.items()],
            key=lambda x: x[1],
            reverse=True
        )

        await self.send_message(websocket, {
            "type": "game_state",
            "round": self.game_state.round_number,
            "is_active": self.game_state.is_active,
            "leaderboard": leaderboard,
            "total_players": len(self.players)
        })

    async def send_message(self, websocket, message: dict):
        """Wyślij wiadomość do konkretnego klienta"""
        try:
            await websocket.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            pass

    async def broadcast_message(self, message: dict, exclude=None):
        """Wyślij wiadomość do wszystkich klientów"""
        if not self.connected_clients:
            return

        message["timestamp"] = datetime.now().isoformat()

        disconnected = set()
        for websocket in self.connected_clients:
            if websocket != exclude:
                try:
                    await websocket.send(json.dumps(message))
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(websocket)

        # Usuń rozłączonych klientów
        for websocket in disconnected:
            await self.remove_player(websocket)

    async def remove_player(self, websocket):
        """Usuń gracza z gry"""
        self.connected_clients.discard(websocket)

        # Znajdź gracza po websocket
        player_to_remove = None
        for name, player in self.players.items():
            if player.websocket == websocket:
                player_to_remove = name
                break

        if player_to_remove:
            del self.players[player_to_remove]
            logger.info(f"Gracz {player_to_remove} opuścił grę")

            await self.broadcast_message({
                "type": "player_left",
                "player": player_to_remove,
                "total_players": len(self.players)
            })

    async def handle_client(self, websocket):
        """Obsługa połączenia klienta"""
        logger.info(f"Nowe połączenie: {websocket.remote_address}")

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    action = data.get("action")

                    if action == "join":
                        player_name = data.get("name", "").strip()
                        if not player_name:
                            await self.send_message(websocket, {
                                "type": "error",
                                "message": "Nazwa gracza nie może być pusta!"
                            })
                            continue

                        await self.register_player(websocket, player_name)

                    elif action == "guess":
                        player_name = data.get("player")
                        guess = data.get("guess")

                        if not isinstance(guess, int):
                            await self.send_message(websocket, {
                                "type": "error",
                                "message": "Zgadywana wartość musi być liczbą!"
                            })
                            continue

                        if not (self.game_state.min_range <= guess <= self.game_state.max_range):
                            await self.send_message(websocket, {
                                "type": "error",
                                "message": f"Liczba musi być z zakresu {self.game_state.min_range}-{self.game_state.max_range}!"
                            })
                            continue

                        await self.handle_guess(websocket, player_name, guess)

                    elif action == "get_state":
                        await self.send_game_state(websocket)

                except json.JSONDecodeError:
                    await self.send_message(websocket, {
                        "type": "error",
                        "message": "Nieprawidłowy format wiadomości!"
                    })

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.remove_player(websocket)


async def main():
    server = DistributedGameServer()

    logger.info("Uruchamianie serwera gry na porcie 8765...")
    logger.info(f"Sekretna liczba w pierwszej rundzie: {server.game_state.secret_number}")

    start_server = websockets.serve(server.handle_client, "localhost", 8765)
    logger.info("Serwer uruchomiony! Oczekiwanie na graczy...")

    await start_server
    await asyncio.Future()  # Uruchom w nieskończoność


if __name__ == "__main__":
    asyncio.run(main())