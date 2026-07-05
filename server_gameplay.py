"""
server_gameplay.py

Server-side port of gameplay.py, covering:
  - Captain movement (move_captain / confirm_move / cancel_move)
  - Legal move refresh + teleport-on-stuck logic
  - Simple space resolutions: barrels, coin, recruit
  - Core turn flow needed so a move doesn't dead-end: rest, go_on_board,
    avast_turn, move_again

Everything else (pubs, guards, maps, supply, rendezvous cards, treasure,
scorpions, wrangle) is NOT yet migrated — resolve_space only dispatches to
the three simple space types for now. Any other space type just logs and
moves to post_move so the turn can still complete without crashing.
"""

import random

class ServerGameplay:
    def __init__(self):
        pass

    # ── Logging ──────────────────────────────────────────────────────────

    def log_action(self, game_state, text):
        game_state["action_log"].append(text)

    # ── Player helpers ──────────────────────────────────────────────────

    def player_can_act(self, player):
        return player["board_position"] == 0 and player["pirates"] > 0

    def sort_hand(self, player):
        for group in ["treasure", "scorpions", "large_guard", "small_guard"]:
            player[group].sort(key=lambda c: -c["points"])
        player["pubs"].sort(key=lambda c: (c["color"], -c["points"]))
        player["maps"].sort(key=lambda c: (c["color"], -c["points"]))
        player["supplies"].sort(key=lambda c: (c["category"], -c["points"]))
        player["rendezvous"].sort(key=lambda c: (c["destination"], -c["points"]))
        wrangle_order = {"bunk": 0, "hammock": 1, "bedroll": 2}

        def wrangle_key(c):
            for w_type in wrangle_order:
                if w_type in c["image_file"].lower():
                    return (wrangle_order[w_type], -c["points"])
            return (99, -c["points"])

        player["wrangles"].sort(key=wrangle_key)
        return player

    # ── Scoring ──────────────────────────────────────────────────────────

    def score_maps(self, maps, character=None):
        total = 0
        by_color = {}
        for card in maps:
            by_color.setdefault(card["color"], []).append(card)

        unpaired = []
        for color, cards in by_color.items():
            cards = sorted(cards, key=lambda c: c.get("points", 0), reverse=True)
            for i in range(0, len(cards) - 1, 2):
                pair = cards[i:i + 2]
                total += pair[0]["points"] + pair[1]["points"]
            if len(cards) % 2 != 0:
                unpaired.append(cards[-1])

        is_cutthroat = (
            isinstance(character, dict) and
            character.get("name") == "Captain Cutthroat the Cartographer"
        )
        if is_cutthroat and unpaired:
            unpaired_sorted = sorted(unpaired, key=lambda c: c.get("points", 0), reverse=True)
            for card in unpaired_sorted[:2]:
                total += card["points"]

        return total

    def score_players(self, game_state):
        for player in game_state["players"]:
            total = pubs = maps = guards = rendezvous = treasure = scorpions = supplies = wrangle = 0

            for card in player.get("pubs", []):
                total += card.get("points", 0)
                pubs += card.get("points", 0)
            for card in player.get("large_guard", []) + player.get("small_guard", []):
                total += card.get("points", 0)
                guards += card.get("points", 0)
            for card in player.get("treasure", []):
                total += card.get("points", 0)
                treasure += card.get("points", 0)
            for card in player.get("scorpions", []):
                is_sullivan = (
                    player["character"] is not None and
                    player["character"]["name"] == "Captain Sullivan the Scorpion Tamer"
                )
                if is_sullivan:
                    total -= card.get("points", 0)
                    scorpions -= card.get("points", 0)
                else:
                    total += card.get("points", 0)
                    scorpions += card.get("points", 0)
            for card in player.get("wrangles", []):
                total += card.get("points", 0)
                wrangle += card.get("points", 0)
            for card in player.get("rendezvous", []):
                if card.get("completed"):
                    total += card.get("points", 0)
                    rendezvous += card.get("points", 0)

            map_cards = player.get("maps", [])
            if map_cards:
                map_score = self.score_maps(map_cards, character=player.get("character"))
                total += map_score
                maps += map_score

            is_har = player["character"] is not None and player["character"]["name"] == "Captain Har the Hoarder"
            if is_har:
                for card in player.get("supplies", []):
                    total += card.get("points", 0)
                    supplies += card.get("points", 0)
            else:
                category_best = {}
                for card in player.get("supplies", []):
                    cat = card.get("category")
                    pts = card.get("points", 0)
                    if cat not in category_best or pts > category_best[cat]:
                        category_best[cat] = pts
                supplies = sum(category_best.values())
                total += supplies

            player["score"] = {
                "total": total, "pubs": pubs, "maps": maps, "guards": guards,
                "rendezvous": rendezvous, "treasure": treasure, "scorpions": scorpions,
                "supplies": supplies, "wrangle": wrangle
            }

    # ── Movement helpers ─────────────────────────────────────────────────

    def get_legal_moves_from_space(self, game_state, captain_space_id):
        occupied_spaces = set()
        for occupied_path in game_state["occupied_paths"]:
            occupied_spaces.update(occupied_path["path"])

        legal_moves = []
        for move in game_state["captain_graph"][str(captain_space_id)] \
                if str(captain_space_id) in game_state["captain_graph"] \
                else game_state["captain_graph"][captain_space_id]:
            if not any(space_id in occupied_spaces for space_id in move["path"]):
                legal_moves.append(move)
        return legal_moves

    def refresh_legal_moves(self, game_state):
        legal_moves = self.get_legal_moves_from_space(game_state, game_state["captain_space"])
        game_state["legal_moves"] = legal_moves
        return legal_moves

    def find_next_coin_space(self, game_state):
        current_space = game_state["space_lookup"][game_state["captain_space"]]
        current_tile = current_space["tile_num"]

        for offset in range(1, 10):
            tile_num = ((current_tile - 1 + offset) % 9) + 1
            coin_space_id = game_state["coin_lookup"].get(tile_num) or game_state["coin_lookup"].get(str(tile_num))
            if coin_space_id is None:
                continue
            legal_moves = self.get_legal_moves_from_space(game_state, coin_space_id)
            if legal_moves:
                return coin_space_id
        return None

    def rendezvous_check(self, card, space):
        space_type = space["type"]
        dest = card["destination"]
        if dest == "pub":
            return space_type in ("red_pub", "blue_pub", "green_pub")
        return space_type == dest

    def teleport_captain(self, game_state):
        legal_moves = self.refresh_legal_moves(game_state)
        if legal_moves:
            return game_state

        old_space = game_state["space_lookup"][game_state["captain_space"]]
        old_space["captain"] = False

        new_space_id = self.find_next_coin_space(game_state)
        if new_space_id is None:
            return game_state

        new_space = game_state["space_lookup"][new_space_id]
        game_state["captain_space"] = new_space_id
        new_space["captain"] = True
        game_state["legal_moves"] = self.refresh_legal_moves(game_state)
        return game_state

    # ── Core movement ────────────────────────────────────────────────────

    def move_captain(self, game_state, destination_id):

        players = game_state["players"]
        current = game_state["active_player"]

        selected_move = next(
            (m for m in game_state["legal_moves"] if m["destination"] == destination_id),
            None
        )
        if selected_move is None:
            return False

        if selected_move["destination_type"] == "dark_alley":
            # Dark alley routing isn't migrated yet — reject cleanly rather
            # than leaving the game_state in a half-built dark_alley phase.
            return None

        player = players[current]
        if player["pirates"] < selected_move["cost"]:
            return False

        old_space = game_state["space_lookup"][game_state["captain_space"]]
        game_state["pending_move"] = {
            "selected_move": selected_move,
            "destination_id": destination_id,
            "old_space_id": old_space["id"],
            "new_space_id": destination_id,
            "cost": selected_move["cost"],
            "path": selected_move["path"]
        }
        game_state["phase"] = "confirm_move"
        return True

    def confirm_move(self, game_state):
        players = game_state["players"]
        current = game_state["active_player"]
        player = players[current]
        pending = game_state["pending_move"]
        selected_move = pending["selected_move"]
        destination_id = pending["destination_id"]

        old_space = game_state["space_lookup"][pending["old_space_id"]]
        old_space["captain"] = False
        new_space = game_state["space_lookup"][destination_id]
        new_space["captain"] = True
        game_state["captain_space"] = destination_id
        game_state["legal_moves"] = game_state["captain_graph"][destination_id] \
            if destination_id in game_state["captain_graph"] \
            else game_state["captain_graph"][str(destination_id)]

        rendezvous_scored = False
        for card in player["rendezvous"]:
            if card["completed"]:
                continue
            if self.rendezvous_check(card, new_space):
                card["completed"] = True
                rendezvous_scored = True
                self.log_action(game_state, f"{player['name']} had a romantic evening with his wench <3")

        sterling_free_move = False
        if player["character"] is not None:
            is_sterling = player["character"]["name"] == "Captain Sterling the Scoundrel"
            sterling_free_move = is_sterling and rendezvous_scored

        if not sterling_free_move:
            player["pirates"] -= pending["cost"]
            player["pirates_on_board"] += pending["cost"]
            for space_id in selected_move["path"]:
                game_state["space_lookup"][space_id]["occupant"] = player["id"]
            game_state["occupied_paths"].append({
                "player_id": player["id"],
                "start": old_space["id"],
                "destination": destination_id,
                "path": selected_move["path"],
                "cost": pending["cost"]
            })

        self.score_players(game_state)
        game_state["pending_move"] = None
        self.refresh_legal_moves(game_state)
        if not game_state["legal_moves"]:
            self.teleport_captain(game_state)
        self.resolve_space(game_state, new_space)

    def cancel_move(self, game_state):
        game_state["pending_move"] = None
        game_state["phase"] = "start_turn"

    # ── Space resolution (simple spaces only for now) ───────────────────

    def resolve_space(self, game_state, space):
        player = game_state["players"][game_state["active_player"]]

        if space["type"] == "barrels":
            self.log_action(game_state, f"{player['name']} secured barrels of rum.")
            return self.barrel_space(game_state, player)
        elif space["type"] == "coin":
            self.log_action(game_state, f"{player['name']} found a lucky coin.")
            return self.coin_space(game_state, player)
        elif space["type"] == "recruit":
            self.log_action(game_state, f"{player['name']} added an ally to their cause.")
            return self.recruit_space(game_state, player)
        else:
            # Not yet migrated (pubs, maps, guards, supply, rendezvous,
            # treasure, scorpion, start/reclaim). Log it and let the turn
            # continue rather than getting stuck.
            self.log_action(game_state, f"{player['name']} landed on a {space['type']} space (not yet handled server-side).")
            game_state["phase"] = "post_move"

    def barrel_space(self, game_state, player):
        if player["character"] is not None and player["character"]["name"] == "Captain Drake the Distiller":
            player["barrels"] += 3
        else:
            player["barrels"] += 2
        game_state["phase"] = "post_move"
        self.score_players(game_state)

    def coin_space(self, game_state, player):
        player["coins"] += 1
        game_state["phase"] = "post_move"

    def recruit_space(self, game_state, player):
        if player["pirate_reserve"] == 0:
            game_state["phase"] = "post_move"
            return
        player["pirates"] += 1
        player["pirate_reserve"] -= 1
        game_state["phase"] = "post_move"

    # ── Turn flow ────────────────────────────────────────────────────────

    def move_again(self, game_state):
        current = game_state["active_player"]
        player = game_state["players"][current]
        if player["coins"] == 0:
            return False
        player["coins"] -= 1
        self.log_action(game_state, f"{player['name']} spent a coin to move again.")
        game_state["phase"] = "start_turn"
        return True

    def rest(self, game_state):
        player = game_state["players"][game_state["active_player"]]
        if player["coins"] == 0:
            return False
        player["coins"] -= 1
        self.log_action(game_state, f"{player['name']} spent a coin to rest.")
        self.avast_turn(game_state)
        return True

    def go_on_board(self, game_state):
        player = game_state["players"][game_state["active_player"]]

        boarded_count = sum(1 for p in game_state["players"] if p["board_position"] > 0)
        player["board_position"] = boarded_count + 1

        all_on_board = all(p["board_position"] > 0 for p in game_state["players"])

        if all_on_board:
            self.log_action(game_state, f"{player['name']} went on board with {player['pirates']} pirates.")
            game_state["phase"] = "wrangle"
            # Wrangle isn't migrated yet — flag it so the client knows
            # nothing further will happen automatically.
            game_state.setdefault("wrangle", {})["active"] = True
            return

        self.avast_turn(game_state)

    def avast_turn(self, game_state):
        players = game_state["players"]
        current = game_state["active_player"]

        if players[current]["board_position"] > 0:
            self.log_action(game_state, f"{players[current]['name']} went on board with {players[current]['pirates']} pirates.")
        else:
            self.log_action(game_state, f"{players[current]['name']} avasted.")

        for player in players:
            self.sort_hand(player)

        for i in range(1, len(players) + 1):
            candidate = (current + i) % len(players)
            if self.player_can_act(players[candidate]):
                game_state["active_player"] = candidate
                game_state["phase"] = "start_turn"
                return

        if self.player_can_act(players[current]):
            game_state["phase"] = "start_turn"
            return

        # No eligible player found — wrangle isn't migrated yet.
        game_state["phase"] = "wrangle"
        game_state.setdefault("wrangle", {})["active"] = True