from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import json
import os
import random
import string
import time
import uuid


ROOT = Path(__file__).resolve().parent
HOST = "0.0.0.0"
DEFAULT_PORT = 8000
PORT = int(os.environ.get("PORT", DEFAULT_PORT))
IS_RENDER = "PORT" in os.environ
MAX_PLAYERS = 7
ROOMS = {}

GAMES = {
    "thulla": {
        "name": "Famous Thulla",
        "description": "Match rank or suit. Draw when stuck. Empty hand wins.",
    },
    "bluff": {
        "name": "Bluff",
        "description": "Play face-down cards with a declared rank. Friends may call bluff.",
    },
    "daketi": {
        "name": "Daketi",
        "description": "Match rank or suit. Matching the top rank steals another turn.",
    },
    "gandu": {
        "name": "Gandu Pataa",
        "description": "Fast wild-card mode with skips, reverses, and draw-twos.",
    },
}

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["spades", "hearts", "diamonds", "clubs"]
SUIT_SYMBOLS = {
    "spades": "S",
    "hearts": "H",
    "diamonds": "D",
    "clubs": "C",
}


def make_deck():
    deck = [{"rank": rank, "suit": suit, "id": f"{rank}-{suit}"} for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def room_code():
    while True:
        code = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(5))
        if code not in ROOMS:
            return code


def public_room(room, player_id=None):
    player_index = next((i for i, p in enumerate(room["players"]) if p["id"] == player_id), -1)
    hand = room["hands"].get(player_id, [])
    return {
        "code": room["code"],
        "game": room["game"],
        "gameName": GAMES[room["game"]]["name"],
        "description": GAMES[room["game"]]["description"],
        "maxPlayers": room["max_players"],
        "hostId": room["host_id"],
        "status": room["status"],
        "players": [
            {
                "id": p["id"],
                "name": p["name"],
                "host": p["id"] == room["host_id"],
                "cards": len(room["hands"].get(p["id"], [])),
                "score": p.get("score", 0),
            }
            for p in room["players"]
        ],
        "you": player_id,
        "yourIndex": player_index,
        "hand": hand,
        "pileTop": room["pile"][-1] if room["pile"] else None,
        "pileCount": len(room["pile"]),
        "deckCount": len(room["deck"]),
        "currentPlayerId": current_player(room),
        "direction": room["direction"],
        "lastPlay": room["last_play"],
        "winner": room["winner"],
        "log": room["log"][-12:],
        "serverTime": int(time.time()),
    }


def current_player(room):
    if not room["players"]:
        return None
    room["current"] %= len(room["players"])
    return room["players"][room["current"]]["id"]


def add_log(room, message):
    room["log"].append({"time": int(time.time()), "message": message})


def next_turn(room, steps=1):
    if not room["players"]:
        return
    room["current"] = (room["current"] + (steps * room["direction"])) % len(room["players"])


def draw_cards(room, player_id, amount=1):
    drawn = []
    for _ in range(amount):
        if not room["deck"]:
            if len(room["pile"]) <= 1:
                break
            top = room["pile"].pop()
            room["deck"] = room["pile"]
            room["pile"] = [top]
            random.shuffle(room["deck"])
        if room["deck"]:
            drawn.append(room["deck"].pop())
    room["hands"].setdefault(player_id, []).extend(drawn)
    return len(drawn)


def remove_cards(hand, indexes):
    indexes = sorted(set(int(i) for i in indexes), reverse=True)
    selected = []
    for index in indexes:
        if index < 0 or index >= len(hand):
            raise ValueError("Selected card is no longer in your hand.")
        selected.append(hand.pop(index))
    selected.reverse()
    return selected


def can_play_on_top(card, top, game):
    if top is None:
        return True
    if game == "gandu" and card["rank"] == "J":
        return True
    return card["rank"] == top["rank"] or card["suit"] == top["suit"]


def start_room(room):
    room["deck"] = make_deck()
    room["pile"] = []
    room["hands"] = {p["id"]: [] for p in room["players"]}
    room["current"] = 0
    room["direction"] = 1
    room["winner"] = None
    room["last_play"] = None
    room["status"] = "playing"
    cards_each = 5 if room["game"] == "bluff" else 7
    for _ in range(cards_each):
        for player in room["players"]:
            draw_cards(room, player["id"], 1)
    if room["game"] != "bluff":
        room["pile"].append(room["deck"].pop())
    add_log(room, f"{GAMES[room['game']]['name']} started with {len(room['players'])} players.")


def finish_if_winner(room, player_id):
    if not room["hands"].get(player_id):
        room["winner"] = player_id
        room["status"] = "finished"
        winner = next(p for p in room["players"] if p["id"] == player_id)
        winner["score"] = winner.get("score", 0) + 1
        add_log(room, f"{winner['name']} won this round.")
        return True
    return False


def play_cards(room, player_id, payload):
    if room["status"] != "playing":
        raise ValueError("Start the game first.")
    if current_player(room) != player_id:
        raise ValueError("It is not your turn yet.")
    indexes = payload.get("indexes", [])
    if not indexes:
        raise ValueError("Select at least one card.")
    hand = room["hands"][player_id]

    if room["game"] == "bluff":
        declared_rank = payload.get("declaredRank")
        if declared_rank not in RANKS:
            raise ValueError("Choose the rank you are claiming.")
        cards = remove_cards(hand, indexes)
        if len(cards) > 4:
            hand.extend(cards)
            raise ValueError("Bluff allows up to 4 cards in one play.")
        room["pile"].extend(cards)
        player = next(p for p in room["players"] if p["id"] == player_id)
        room["last_play"] = {
            "playerId": player_id,
            "playerName": player["name"],
            "declaredRank": declared_rank,
            "count": len(cards),
            "cards": cards,
            "canChallenge": True,
        }
        add_log(room, f"{player['name']} played {len(cards)} card(s), claiming {declared_rank}.")
        if not finish_if_winner(room, player_id):
            next_turn(room)
        return

    if len(indexes) != 1:
        raise ValueError("Play one card at a time in this mode.")
    card = hand[indexes[0]]
    top = room["pile"][-1] if room["pile"] else None
    if not can_play_on_top(card, top, room["game"]):
        raise ValueError("That card must match rank or suit.")
    played = remove_cards(hand, indexes)[0]
    room["pile"].append(played)
    player = next(p for p in room["players"] if p["id"] == player_id)
    room["last_play"] = {
        "playerId": player_id,
        "playerName": player["name"],
        "declaredRank": played["rank"],
        "count": 1,
        "cards": [played],
        "canChallenge": False,
    }
    add_log(room, f"{player['name']} played {played['rank']}{SUIT_SYMBOLS[played['suit']]}.")
    if finish_if_winner(room, player_id):
        return

    if room["game"] == "daketi" and top and played["rank"] == top["rank"]:
        add_log(room, f"{player['name']} stole another turn.")
        return

    if room["game"] == "gandu":
        if played["rank"] == "A":
            room["direction"] *= -1
            add_log(room, "Direction reversed.")
        if played["rank"] == "2" and len(room["players"]) > 1:
            next_turn(room)
            target_id = current_player(room)
            amount = draw_cards(room, target_id, 2)
            target = next(p for p in room["players"] if p["id"] == target_id)
            add_log(room, f"{target['name']} drew {amount} card(s).")
        if played["rank"] == "8":
            next_turn(room, 2)
            add_log(room, "Next player was skipped.")
            return

    next_turn(room)


def call_bluff(room, player_id):
    if room["game"] != "bluff" or room["status"] != "playing":
        raise ValueError("Bluff calls only work in Bluff mode.")
    last = room["last_play"]
    if not last or not last.get("canChallenge"):
        raise ValueError("There is no active claim to challenge.")
    if last["playerId"] == player_id:
        raise ValueError("You cannot challenge your own claim.")
    challenger = next(p for p in room["players"] if p["id"] == player_id)
    liar = next(p for p in room["players"] if p["id"] == last["playerId"])
    honest = all(card["rank"] == last["declaredRank"] for card in last["cards"])
    if honest:
        room["hands"].setdefault(player_id, []).extend(room["pile"])
        add_log(room, f"{challenger['name']} called bluff and was wrong. They took the pile.")
    else:
        room["hands"].setdefault(last["playerId"], []).extend(room["pile"])
        add_log(room, f"{challenger['name']} caught {liar['name']} bluffing. {liar['name']} took the pile.")
    room["pile"] = []
    room["last_play"]["canChallenge"] = False
    room["current"] = next((i for i, p in enumerate(room["players"]) if p["id"] == player_id), room["current"])


def draw_action(room, player_id):
    if room["status"] != "playing":
        raise ValueError("Start the game first.")
    if current_player(room) != player_id:
        raise ValueError("It is not your turn yet.")
    amount = draw_cards(room, player_id, 1)
    player = next(p for p in room["players"] if p["id"] == player_id)
    add_log(room, f"{player['name']} drew {amount} card(s).")
    next_turn(room)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        if self.path.startswith("/api/state"):
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
            code = params.get("code", "").upper()
            player_id = params.get("playerId")
            room = ROOMS.get(code)
            if not room:
                self.send_json({"error": "Room not found."}, 404)
                return
            self.send_json(public_room(room, player_id))
            return

        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        file_path = (ROOT / path.lstrip("/")).resolve()
        if ROOT not in file_path.parents and file_path != ROOT:
            self.send_json({"error": "Not found."}, 404)
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_json({"error": "Not found."}, 404)
            return
        content_type = "text/html"
        if file_path.suffix == ".css":
            content_type = "text/css"
        elif file_path.suffix == ".js":
            content_type = "application/javascript"
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            data = self.read_json()
            if self.path == "/api/create":
                name = str(data.get("name", "Host")).strip()[:20] or "Host"
                game = data.get("game", "thulla")
                if game not in GAMES:
                    raise ValueError("Unknown game.")
                max_players = max(2, min(MAX_PLAYERS, int(data.get("maxPlayers", MAX_PLAYERS))))
                player_id = uuid.uuid4().hex
                code = room_code()
                ROOMS[code] = {
                    "code": code,
                    "game": game,
                    "max_players": max_players,
                    "host_id": player_id,
                    "status": "lobby",
                    "players": [{"id": player_id, "name": name, "score": 0}],
                    "hands": {},
                    "deck": [],
                    "pile": [],
                    "current": 0,
                    "direction": 1,
                    "last_play": None,
                    "winner": None,
                    "log": [],
                    "created": time.time(),
                }
                add_log(ROOMS[code], f"{name} created the room.")
                self.send_json({"room": public_room(ROOMS[code], player_id), "playerId": player_id})
                return

            if self.path == "/api/join":
                code = str(data.get("code", "")).upper().strip()
                name = str(data.get("name", "Player")).strip()[:20] or "Player"
                room = ROOMS.get(code)
                if not room:
                    raise ValueError("Room not found.")
                if room["status"] != "lobby":
                    raise ValueError("This game has already started.")
                if len(room["players"]) >= room["max_players"]:
                    raise ValueError("Room is full.")
                player_id = uuid.uuid4().hex
                room["players"].append({"id": player_id, "name": name, "score": 0})
                add_log(room, f"{name} joined the room.")
                self.send_json({"room": public_room(room, player_id), "playerId": player_id})
                return

            code = str(data.get("code", "")).upper().strip()
            player_id = data.get("playerId")
            room = ROOMS.get(code)
            if not room:
                raise ValueError("Room not found.")
            if player_id not in [p["id"] for p in room["players"]]:
                raise ValueError("You are not in this room.")

            if self.path == "/api/start":
                if player_id != room["host_id"]:
                    raise ValueError("Only the host can start.")
                if len(room["players"]) < 2:
                    raise ValueError("At least 2 players are needed.")
                start_room(room)
                self.send_json({"room": public_room(room, player_id)})
                return

            if self.path == "/api/action":
                action = data.get("action")
                if action == "play":
                    play_cards(room, player_id, data)
                elif action == "draw":
                    draw_action(room, player_id)
                elif action == "call_bluff":
                    call_bluff(room, player_id)
                else:
                    raise ValueError("Unknown action.")
                self.send_json({"room": public_room(room, player_id)})
                return

            if self.path == "/api/reset":
                if player_id != room["host_id"]:
                    raise ValueError("Only the host can reset.")
                room["status"] = "lobby"
                room["hands"] = {}
                room["deck"] = []
                room["pile"] = []
                room["winner"] = None
                room["last_play"] = None
                add_log(room, "Room reset to lobby.")
                self.send_json({"room": public_room(room, player_id)})
                return

            if self.path == "/api/leave":
                leaving = next(p for p in room["players"] if p["id"] == player_id)
                if player_id == room["host_id"] or len(room["players"]) == 1:
                    del ROOMS[code]
                    self.send_json({"left": True, "roomDeleted": True})
                    return

                player_index = next(i for i, p in enumerate(room["players"]) if p["id"] == player_id)
                room["players"] = [p for p in room["players"] if p["id"] != player_id]
                room["hands"].pop(player_id, None)
                if room["players"]:
                    room["current"] %= len(room["players"])
                    if player_index <= room["current"] and room["current"] > 0:
                        room["current"] -= 1
                add_log(room, f"{leaving['name']} left the room.")
                self.send_json({"left": True, "roomDeleted": False})
                return

            raise ValueError("Unknown endpoint.")
        except Exception as exc:
            self.send_json({"error": str(exc)}, 400)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    if IS_RENDER:
        selected_port = PORT
        server = ThreadingHTTPServer((HOST, selected_port), Handler)
    else:
        server = None
        selected_port = PORT
        for candidate_port in range(PORT, PORT + 20):
            try:
                server = ThreadingHTTPServer((HOST, candidate_port), Handler)
                selected_port = candidate_port
                break
            except OSError:
                continue
        if server is None:
            raise SystemExit("No free port found from 8000 to 8019.")
    print(f"Thulla.com is running at http://localhost:{selected_port}")
    if IS_RENDER:
        print("Render deployment is live on the service URL.")
    else:
        print(f"Friends on the same Wi-Fi/hotspot can join with http://YOUR-IP:{selected_port}")
    server.serve_forever()
