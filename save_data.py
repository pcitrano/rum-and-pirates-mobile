import json
import os
import requests

SERVER_URL = "https://rumandpirates.up.railway.app"

class save_data:
    def __init__(self):
        self.data_dir = os.path.join(os.environ["APPDATA"], "RumAndPirates")
        os.makedirs(self.data_dir, exist_ok=True)
        self.settings_path = os.path.join(self.data_dir, "settings.json")
        self.settings = self.load_settings()
        self.stats = self.load_stats_from_server()

    ################### SETTINGS ####################

    def load_settings(self):
        defaults = {
            "player_name": "",
            "resolution": [1600, 900],
            "fullscreen": False,
            "menu_background": "Menu Background.jpg",
            "game_background": "New Game Screen.jpg",
            "wrangle_view": "Classic",
            "random_start": False,
            "play_with_characters": False,
            "server_ip": "rumandpirates.up.railway.app"
        }
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r") as f:
                    saved = json.load(f)
                    defaults.update(saved)
            except Exception:
                pass
        return defaults

    def save_settings(self):
        with open(self.settings_path, "w") as f:
            json.dump(self.settings, f, indent=2)

    ################### STATS ######################

    def load_stats_from_server(self):
        try:
            resp = requests.get(f"{SERVER_URL}/stats", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {"games": [], "players": {}}

    def save_game_to_server(self, game_result):
        try:
            requests.post(f"{SERVER_URL}/stats/add_game", json=game_result, timeout=5)
        except Exception:
            pass

    def get_player_stats(self, name):
        if name not in self.stats["players"]:
            self.stats["players"][name] = {
                "wins": 0,
                "games_played": 0,
                "current_streak": 0,
                "best_streak": 0,
                "category_totals": {
                    "pubs": 0, "maps": 0, "guards": 0,
                    "treasure": 0, "scorpions": 0, "supplies": 0,
                    "rendezvous": 0, "wrangle": 0
                }
            }
        return self.stats["players"][name]

    def record_game_result(self, players):
        import datetime
        
        sorted_players = sorted(
            players,
            key=lambda p: (
                p["score"].get("total", 0),
                -p.get("pirate_reserve", 0),
                p.get("barrels", 0),
                p.get("coins", 0)
            ),
            reverse=True
        )
        
        winner = sorted_players[0]

        game_result = {
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "winner": winner["name"],
            "players": []
        }
        for player in sorted_players:
            character = player.get("character")
            game_result["players"].append({
                "name": player["name"],
                "character": character["name"] if character else None,
                "scores": {
                    "pubs": player["score"].get("pubs", 0),
                    "maps": player["score"].get("maps", 0),
                    "guards": player["score"].get("guards", 0),
                    "treasure": player["score"].get("treasure", 0),
                    "scorpions": player["score"].get("scorpions", 0),
                    "supplies": player["score"].get("supplies", 0),
                    "rendezvous": player["score"].get("rendezvous", 0),
                    "wrangle": player["score"].get("wrangle", 0),
                    "total": player["score"].get("total", 0)
                },
                "won": player["name"] == winner["name"]
            })

        # Push to server (server handles all aggregation)
        self.save_game_to_server(game_result)

        # Refresh local stats cache from server
        self.stats = self.load_stats_from_server()

    def get_averages(self, name):
        s = self.get_player_stats(name)
        games = s["games_played"]
        if games == 0:
            return {k: 0 for k in s["category_totals"]}
        return {k: round(v / games, 1) for k, v in s["category_totals"].items()}

    def get_game(self, game_index):
        if 0 <= game_index < len(self.stats["games"]):
            return self.stats["games"][game_index]
        return None

    def get_player_games(self, name):
        return [g for g in self.stats["games"] if any(p["name"] == name for p in g["players"])]
    
    def get_elo_leaderboard(self):
        players = self.stats.get("players", {})
        ranked = sorted(
            [{"name": name, "elo": data.get("elo", 1200), "games_played": data["games_played"]}
            for name, data in players.items()
            if data["games_played"] > 0],
            key=lambda p: p["elo"],
            reverse=True
        )
        return ranked