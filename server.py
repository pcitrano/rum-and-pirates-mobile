from flask import Flask, request, Response, send_from_directory
from flask_socketio import SocketIO, join_room, emit, disconnect
import uuid
import json, os
import time
import threading
from server_game_setup import ServerGameSetup
from server_gameplay import ServerGameplay

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

rooms = {}  # { room_id: { "game_state": {}, "players": [] } }

STATS_FILE = "/data/stats.json"
board_setup = ServerGameSetup(tiles_dir="assets/tiles", cards_path="assets/cards.json")
gameplay = ServerGameplay()

# ── Static assets ─────────────────────────────────────────────────────────────

@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory("assets", filename)

@app.route("/assets/tiles")
def get_tile_data():
    tile_data = []
    for i in range(1, 10):
        path = f"assets/tiles/tile_{i}.json"
        if os.path.exists(path):
            with open(path) as f:
                tile_data.append(json.load(f))
    return Response(json.dumps(tile_data), mimetype="application/json")

# ── Main Lobby and Game ─────────────────────────────────────────────────────────────────────
@app.route("/")
def lobby():
    with open("lobby.html") as f:
        return f.read()

@app.route("/game")
def game():
    with open("game.html") as f:
        return f.read()

# ── Rooms ─────────────────────────────────────────────────────────────────────

@app.route("/rooms")
def get_rooms():
    open_rooms = []
    for room_id, room in rooms.items():
        if room["game_state"] is None:
            open_rooms.append({
                "room_id": room_id,
                "players": [p["name"] for p in room["players"] if p.get("connected")]
            })
    return Response(json.dumps(open_rooms), mimetype="application/json")

@app.route("/games")
def get_games():
    active_games = []
    for room_id, room in rooms.items():
        game_state = room.get("game_state")
        if game_state is not None and game_state.get("phase") != "game_over":
            active_games.append({
                "room_id": room_id,
                "players": [p["name"] for p in room["players"]]
            })
    return Response(json.dumps(active_games), mimetype="application/json")

# ── Socket events ─────────────────────────────────────────────────────────────

@socketio.on("create_room")
def on_create_room(data):
    room_id = str(uuid.uuid4())[:6].upper()
    rooms[room_id] = {
        "game_state": None,
        "players": [{"name": data["name"], "sid": request.sid, "connected": True}],
        "disconnected": {},
        "created_at": time.time()
    }
    join_room(room_id)
    emit("room_created", {"room_id": room_id})

@socketio.on("join_room")
def on_join_room(data):
    room_id = data["room_id"]
    if room_id not in rooms:
        emit("error", {"message": "Room not found"})
        return

    # Check for rejoin
    for i, player in enumerate(rooms[room_id]["players"]):
        if player["name"] == data["name"] and not player["connected"]:
            rooms[room_id]["players"][i]["sid"] = request.sid
            rooms[room_id]["players"][i]["connected"] = True
            join_room(room_id)
            emit("room_joined", {"room_id": room_id, "player_index": i, "reconnected": True})
            if rooms[room_id]["game_state"]:
                emit("state_updated", {"game_state": rooms[room_id]["game_state"]})
            socketio.emit("player_reconnected", {"name": data["name"]}, room=room_id)
            return

    # New player joining
    player_index = len(rooms[room_id]["players"])
    rooms[room_id]["players"].append({"name": data["name"], "sid": request.sid, "connected": True})
    join_room(room_id)
    emit("room_joined", {"room_id": room_id, "player_index": player_index, "reconnected": False})
    socketio.emit("player_joined", {"players": [p["name"] for p in rooms[room_id]["players"]]}, room=room_id)

    if data.get("web_client"):
        rooms[room_id].setdefault("web_players", set()).add(player_index)

@socketio.on("update_state")
def on_update_state(data):
    room_id = data["room_id"]
    rooms[room_id]["game_state"] = data["game_state"]
    emit("state_updated", {"game_state": data["game_state"]}, room=room_id, include_self=False)

@socketio.on("player_action")
def on_player_action(data):

    room_id = data["room_id"]
    action_type = data.get("type")

    if room_id not in rooms or rooms[room_id]["game_state"] is None:
        emit("error", {"message": "Room not found or game not started"})
        return

    game_state = rooms[room_id]["game_state"]

    if action_type == "move":
        destination_id = data.get("destination_id")
        result = gameplay.move_captain(game_state, destination_id)

        if result is None:
            emit("error", {"message": "Dark alley moves aren't supported yet"})
            return
        if result is False:
            emit("error", {"message": "Illegal move"})
            return

        gameplay.confirm_move(game_state)

    elif action_type == "rest":
        gameplay.rest(game_state)

    elif action_type == "go_on_board":
        gameplay.go_on_board(game_state)

    elif action_type == "move_again":
        gameplay.move_again(game_state)

    elif action_type == "avast":
        gameplay.avast_turn(game_state)

    elif action_type == "roll":
        roller_index = data.get("player_index")
        if game_state.get("next_roller") != roller_index:
            emit("error", {"message": "It's not your turn to roll"})
            return
        gameplay.roll(game_state, roller_index)

    elif action_type == "confirm_roll":
        gameplay.resolve_roll(game_state)

    elif action_type == "reroll":
        gameplay.resolve_reroll(game_state)

    elif action_type == "confirm_rendezvous":
        gameplay.confirm_rendezvous(game_state)

    elif action_type == "supply_choice":
        gameplay.resolve_supply_choice(game_state, data.get("keep_card", False))

    elif action_type == "har_supply_choice":
        gameplay.resolve_har_supply(game_state, data.get("chosen_index"))

    elif action_type == "answer_pub_invite":
        gameplay.answer_pub_invite(game_state, data.get("joined", False))

    else:
        # Not yet migrated — relay to other clients (e.g. desktop host)
        emit("action_received", data, room=room_id, include_self=False)
        return

    rooms[room_id]["game_state"] = game_state
    socketio.emit("state_updated", {"game_state": game_state}, room=room_id)

@socketio.on("start_game")
def on_start_game(data):
    """
    Legacy path — desktop client still builds and sends its own game_state.
    Kept for backward compatibility while the migration is in progress.
    """
    room_id = data["room_id"]
    game_state = data["game_state"]
    rooms[room_id]["game_state"] = game_state
    socketio.emit("state_updated", {"game_state": game_state}, room=room_id)

@socketio.on("new_game")
def on_new_game(data):
    """
    Fully server-driven game start. The server builds the entire initial
    game_state — players, characters (if enabled), decks, tableau, and
    board — using only the connected players' names from the room.
    """
    room_id = data["room_id"]
    if room_id not in rooms:
        emit("error", {"message": "Room not found"})
        return

    play_with_characters = data.get("play_with_characters", False)
    random_start = data.get("random_start", False)

    player_names = [p["name"] for p in rooms[room_id]["players"]]

    game_state = board_setup.new_game_state(
        player_names,
        play_with_characters=play_with_characters,
        random_start=random_start
    )

    rooms[room_id]["game_state"] = game_state
    socketio.emit("state_updated", {"game_state": game_state}, room=room_id)

@socketio.on("confirm_character")
def on_confirm_character(data):
    """
    A player confirms their character pick. Once all players have
    confirmed, the server assigns characters, applies bonuses, generates
    the board, and starts the game.
    """
    room_id = data["room_id"]
    player_index = data["player_index"]
    selected_name = data["selected_name"]
    random_start = data.get("random_start", False)

    if room_id not in rooms or rooms[room_id]["game_state"] is None:
        emit("error", {"message": "Room not found or game not started"})
        return

    game_state = rooms[room_id]["game_state"]
    game_state["character_selections"][player_index] = selected_name
    game_state["character_confirmed"][player_index] = True

    if all(game_state["character_confirmed"]):
        game_state = board_setup.finish_character_select(game_state, random_start=random_start)

    rooms[room_id]["game_state"] = game_state
    socketio.emit("state_updated", {"game_state": game_state}, room=room_id)

@socketio.on("disconnect")
def on_disconnect():
    for room_id, room in rooms.items():
        for i, player in enumerate(room.get("players", [])):
            if player.get("sid") == request.sid:
                print(f"[server] {player['name']} disconnected from room {room_id}")
                room["disconnected"][i] = player
                room["players"][i]["connected"] = False
                break

@socketio.on("rejoin_room")
def on_rejoin_room(data):
    room_id = data["room_id"]
    name = data["name"]

    if room_id not in rooms:
        emit("rejoin_error", {"message": "Room not found"})
        return

    room = rooms[room_id]
    player = next((p for p in room["players"] if p["name"] == name), None)

    if player is None:
        emit("rejoin_error", {"message": "Player not found in this game"})
        return

    player["sid"] = request.sid
    player["connected"] = True
    join_room(room_id)
    emit("rejoined", {"room_id": room_id})
    emit("game_state_update", room["game_state"])

# ── Stats ─────────────────────────────────────────────────────────────────────

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    return {"games": [], "players": {}}

def save_stats(data):
    with open(STATS_FILE, "w") as f:
        json.dump(data, f, indent=2)

@app.route("/stats", methods=["GET"])
def get_stats():
    return Response(json.dumps(load_stats()), mimetype="application/json")

@app.route("/stats/add_game", methods=["POST"])
def add_game():
    data = request.get_json()
    stats = load_stats()

    sorted_players = sorted(data["players"], key=lambda p: p["scores"]["total"], reverse=True)
    ranks = {}
    for i, player in enumerate(sorted_players):
        ranks[player["name"]] = i + 1

    players_with_elo = []
    for player in data["players"]:
        name = player["name"]
        if name not in stats["players"]:
            stats["players"][name] = {
                "wins": 0,
                "games_played": 0,
                "current_streak": 0,
                "best_streak": 0,
                "elo": 1200,
                "category_totals": {k: 0 for k in player["scores"] if k != "total"}
            }
        players_with_elo.append({
            "name": name,
            "elo": stats["players"][name].get("elo", 1200)
        })

    new_elos = calculate_elo(players_with_elo, ranks)

    game_index = len(stats["games"])
    stats["games"].append({
        "game_index": game_index,
        "date": data["date"],
        "winner": data["winner"],
        "players": [
            {**p, "rank": ranks[p["name"]],
             "elo_before": next(e["elo"] for e in players_with_elo if e["name"] == p["name"]),
             "elo_after": new_elos[p["name"]]}
            for p in data["players"]
        ]
    })

    for player in data["players"]:
        name = player["name"]
        won = player["won"]
        scores = player["scores"]
        p = stats["players"][name]

        p["games_played"] += 1
        p["elo"] = new_elos[name]

        if won:
            p["wins"] += 1
            p["current_streak"] += 1
            p["best_streak"] = max(p["best_streak"], p["current_streak"])
        else:
            p["current_streak"] = 0

        for category, value in scores.items():
            if category != "total":
                p["category_totals"][category] = p["category_totals"].get(category, 0) + value

    save_stats(stats)
    return Response(json.dumps({"ok": True, "new_elos": new_elos}), mimetype="application/json")

@app.route("/stats/reset", methods=["POST"])
def reset_stats():
    save_stats({"games": [], "players": {}})
    return Response(json.dumps({"ok": True}), mimetype="application/json")

# ── ELO ───────────────────────────────────────────────────────────────────────

def calculate_elo(players_with_elo, ranks):
    K = 32
    n = len(players_with_elo)
    elo_map = {p["name"]: p["elo"] for p in players_with_elo}
    deltas = {p["name"]: 0 for p in players_with_elo}

    for i in range(n):
        for j in range(i + 1, n):
            a = players_with_elo[i]["name"]
            b = players_with_elo[j]["name"]
            ra, rb = elo_map[a], elo_map[b]

            ea = 1 / (1 + 10 ** ((rb - ra) / 400))
            eb = 1 - ea

            rank_a, rank_b = ranks[a], ranks[b]
            if rank_a < rank_b:
                sa, sb = 1, 0
            elif rank_a > rank_b:
                sa, sb = 0, 1
            else:
                sa, sb = 0.5, 0.5

            deltas[a] += K * (sa - ea)
            deltas[b] += K * (sb - eb)

    pairs = n * (n - 1) / 2
    return {name: round(elo_map[name] + delta / pairs * (n - 1))
            for name, delta in deltas.items()}

# ── Cleanup threads ───────────────────────────────────────────────────────────

def cleanup_inactive_rooms():
    while True:
        time.sleep(120)
        now = time.time()
        stale = [
            room_id for room_id, room in list(rooms.items())
            if room["game_state"] is None and now - room.get("created_at", now) > 1200
        ]
        for room_id in stale:
            del rooms[room_id]
            print(f"Removed inactive room {room_id}")

threading.Thread(target=cleanup_inactive_rooms, daemon=True).start()

def cleanup_old_games():
    while True:
        time.sleep(3600)
        now = time.time()
        stale = [
            room_id for room_id, room in list(rooms.items())
            if now - room.get("created_at", now) > 5 * 24 * 60 * 60
        ]
        for room_id in stale:
            del rooms[room_id]
            print(f"Removed old room {room_id}")

threading.Thread(target=cleanup_old_games, daemon=True).start()

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)