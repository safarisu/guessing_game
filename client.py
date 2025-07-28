#!/usr/bin/env python3
"""
Klient gry "Guess the Number" - demonstracja systemu rozproszonego
Wymagania: pip install websockets asyncio
"""

import asyncio
import websockets
import json
import threading
from datetime import datetime


class GameClient:
    def __init__(self, server_url="ws://localhost:8765"):
        self.server_url = server_url
        self.websocket = None
        self.player_name = None
        self.connected = False
        self.game_info = {}

    async def connect(self):
        """Połącz z serwerem"""
        try:
            self.websocket = await websockets.connect(self.server_url)
            self.connected = True
            print(f"✅ Połączono z serwerem: {self.server_url}")
            return True
        except Exception as e:
            print(f"❌ Błąd połączenia: {e}")
            return False

    async def disconnect(self):
        """Rozłącz z serwerem"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            print("Rozłączono z serwerem")

    async def send_message(self, message: dict):
        """Wyślij wiadomość do serwera"""
        if self.websocket and self.connected:
            try:
                await self.websocket.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                self.connected = False
                print("Połączenie zostało przerwane")

    async def join_game(self, name: str):
        """Dołącz do gry"""
        self.player_name = name
        await self.send_message({
            "action": "join",
            "name": name
        })

    async def make_guess(self, guess: int):
        """Wykonaj zgadywanie"""
        await self.send_message({
            "action": "guess",
            "player": self.player_name,
            "guess": guess
        })

    async def get_game_state(self):
        """Pobierz aktualny stan gry"""
        await self.send_message({
            "action": "get_state"
        })

    def handle_message(self, message: dict):
        """Obsługa wiadomości od serwera"""
        msg_type = message.get("type")
        timestamp = message.get("timestamp", "")

        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime("%H:%M:%S")
            except:
                time_str = ""
        else:
            time_str = ""

        if msg_type == "joined":
            print(f"\n🎮 {message['message']}")
            self.game_info = message.get("game_info", {})
            print(f"📊 Runda: {self.game_info.get('round', 1)}")
            print(f"🎯 Zakres: {self.game_info.get('range', [1, 100])}")
            print(f"🔢 Maksymalne próby: {self.game_info.get('max_guesses', 10)}")

        elif msg_type == "error":
            print(f"❌ Błąd: {message['message']}")

        elif msg_type == "guess_result":
            guess = message['guess']
            hint = message['hint']
            remaining = message['remaining_guesses']
            print(f"\n🎯 Twoja próba: {guess}")
            print(f"💡 Wskazówka: liczba jest {hint}")
            print(f"🔢 Pozostałe próby: {remaining}")

        elif msg_type == "game_won":
            winner = message['winner']
            secret = message['secret_number']
            guesses = message['guesses_taken']
            points = message['points_earned']

            if winner == self.player_name:
                print(f"\n🏆 GRATULACJE! Wygrałeś!")
                print(f"✨ Zgadłeś liczbę {secret} w {guesses} próbach!")
                print(f"🎖️ Zdobyłeś {points} punktów!")
            else:
                print(f"\n🎉 Gracz {winner} wygrał rundę!")
                print(f"🔢 Sekretna liczba: {secret}")
                print(f"🎯 Zgadł w {guesses} próbach, zdobywając {points} punktów")

        elif msg_type == "new_round":
            round_num = message['round']
            print(f"\n🔄 {message['message']}")
            print("=" * 50)

        elif msg_type == "player_joined":
            player = message['player']
            total = message['total_players']
            if time_str:
                print(f"[{time_str}] ➕ {player} dołączył do gry (gracze: {total})")
            else:
                print(f"➕ {player} dołączył do gry (gracze: {total})")

        elif msg_type == "player_left":
            player = message['player']
            total = message['total_players']
            if time_str:
                print(f"[{time_str}] ➖ {player} opuścił grę (gracze: {total})")
            else:
                print(f"➖ {player} opuścił grę (gracze: {total})")

        elif msg_type == "player_guessed":
            player = message['player']
            guess = message['guess']
            remaining = message['remaining']
            if time_str:
                print(f"[{time_str}] 🎯 {player} zgaduje: {guess} (pozostało: {remaining})")
            else:
                print(f"🎯 {player} zgaduje: {guess} (pozostało: {remaining})")

        elif msg_type == "out_of_guesses":
            print(f"\n💥 {message['message']}")
            print("Poczekaj na nową rundę...")

        elif msg_type == "game_state":
            self.display_game_state(message)

    def display_game_state(self, state):
        """Wyświetl stan gry"""
        print(f"\n📊 STAN GRY - Runda {state['round']}")
        print(f"🎮 Status: {'Aktywna' if state['is_active'] else 'Nieaktywna'}")
        print(f"👥 Graczy online: {state['total_players']}")

        if state['leaderboard']:
            print("\n🏆 RANKING:")
            for i, (name, score) in enumerate(state['leaderboard'], 1):
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔸"
                marker = " <- TY" if name == self.player_name else ""
                print(f"  {emoji} {i}. {name}: {score} pkt{marker}")
        print()

    async def message_listener(self):
        """Nasłuchuj wiadomości od serwera"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    self.handle_message(data)
                except json.JSONDecodeError:
                    print("Otrzymano nieprawidłową wiadomość")
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            print("\n❌ Połączenie z serwerem zostało przerwane")


def input_thread(client):
    """Wątek do obsługi wejścia użytkownika"""
    asyncio.set_event_loop(asyncio.new_event_loop())

    def get_input():
        while client.connected:
            try:
                user_input = input().strip()
                if user_input:
                    asyncio.run_coroutine_threadsafe(
                        handle_user_input(client, user_input),
                        client.loop
                    )
            except (EOFError, KeyboardInterrupt):
                break

    threading.Thread(target=get_input, daemon=True).start()


async def handle_user_input(client, user_input):
    """Obsługa wejścia użytkownika"""
    if user_input.lower() in ['quit', 'exit', 'q']:
        await client.disconnect()
        return
    elif user_input.lower() in ['state', 'status', 's']:
        await client.get_game_state()
        return
    elif user_input.lower() in ['help', 'h']:
        print_help()
        return

    try:
        guess = int(user_input)
        await client.make_guess(guess)
    except ValueError:
        print("❌ Wpisz liczbę, 'state' (stan gry), 'help' (pomoc), lub 'quit' (wyjście)")


def print_help():
    """Wyświetl pomoc"""
    print("""
📋 DOSTĘPNE KOMENDY:
• Wpisz liczbę - wykonaj zgadywanie
• 'state' lub 's' - pokaż aktualny stan gry i ranking
• 'help' lub 'h' - pokaż tę pomoc
• 'quit', 'exit' lub 'q' - wyjdź z gry
""")


async def main():
    print("🎮 GUESS THE NUMBER - Klient gry")
    print("=" * 40)

    # Pobierz nazwę gracza
    while True:
        name = input("Podaj swoją nazwę gracza: ").strip()
        if name:
            break
        print("Nazwa nie może być pusta!")

    # Utwórz klienta i połącz
    client = GameClient()

    if not await client.connect():
        return

    client.loop = asyncio.get_event_loop()

    # Dołącz do gry
    await client.join_game(name)

    # Uruchom wątek do obsługi wejścia
    input_thread(client)

    print("\n🎯 Wpisz liczbę aby zgadywać, 'help' aby zobaczyć pomoc")
    print("=" * 50)

    # Rozpocznij nasłuchiwanie wiadomości
    try:
        await client.message_listener()
    except KeyboardInterrupt:
        print("\n👋 Zamykanie klienta...")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Do widzenia!")