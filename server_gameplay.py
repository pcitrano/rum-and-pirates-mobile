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
        player = players[current]

        selected_move = next(
            (m for m in game_state["legal_moves"] if m["destination"] == destination_id),
            None
        )
        if selected_move is None:
            return False

        if selected_move["destination_type"] == "dark_alley":

            game_state["dark_alley"] = {
                "entry_move": selected_move,
                "entry_space": destination_id,
                "start_space": game_state["captain_space"]
            }

            all_dark_alley = all(
                m["destination_type"] == "dark_alley" for m in game_state["legal_moves"]
            )
            if all_dark_alley:
                game_state["phase"] = "dark_alley_start"
            else:
                if player["coins"] < 1:
                    game_state["dark_alley"] = {}
                    return False
                game_state["phase"] = "dark_alley_ask"
            return True

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
        self.resolve_space(game_state, new_space)

    def cancel_move(self, game_state):
        game_state["pending_move"] = None
        game_state["phase"] = "start_turn"

    def pay_dark_alley(self, game_state, accepted):
        current = game_state["active_player"]
        player = game_state["players"][current]

        if not accepted:
            game_state["dark_alley"] = {}
            game_state["phase"] = "start_turn"
            return

        player["coins"] -= 1
        game_state["phase"] = "dark_alley_start"

    def cancel_dark_alley(self, game_state):
        game_state["dark_alley"] = {}
        game_state["phase"] = "start_turn"

    def resolve_dark_alley(self, game_state, exit_id):

        players = game_state["players"]
        current = game_state["active_player"]
        player = players[current]
        dark_alley = game_state.get("dark_alley") or {}

        entry_move = dark_alley.get("entry_move")
        entry_space = dark_alley.get("entry_space")
        start_space = dark_alley.get("start_space")
        if entry_move is None:
            return False

        if exit_id == entry_space:
            return False  # must exit through a different alley

        alley_lookup = game_state["alley_lookup"]
        exit_move = alley_lookup.get(exit_id) or alley_lookup.get(str(exit_id))
        if exit_move is None:
            return False  # not a valid dark alley

        # Occupancy check across BOTH legs — neither the entry path nor the
        # exit path may pass through a space another player currently
        # occupies.
        all_relevant_spaces = set(entry_move["path"]) | set(exit_move["path"])
        for occupied in game_state["occupied_paths"]:
            if all_relevant_spaces.intersection(occupied["path"]):
                return False

        entry_cost = entry_move["cost"]
        exit_cost = exit_move["cost"]

        total_cost = entry_cost + exit_cost
        if player["pirates"] < total_cost:
            return False

        player["pirates"] -= total_cost
        player["pirates_on_board"] += total_cost

        for space_id in entry_move["path"]:
            game_state["space_lookup"][space_id]["occupant"] = player["id"]
        for space_id in exit_move["path"]:
            game_state["space_lookup"][space_id]["occupant"] = player["id"]

        # Two separate entries — never combined — so a future reclaim can
        # pick any two dark-alley legs independently, linked or not.
        game_state["occupied_paths"].append({
            "player_id": player["id"],
            "start": start_space,
            "destination": entry_space,
            "path": entry_move["path"],
            "cost": entry_cost,
            "dark_alley": True
        })
        game_state["occupied_paths"].append({
            "player_id": player["id"],
            "start": exit_id,
            "destination": exit_move["captain"],
            "path": exit_move["path"],
            "cost": exit_cost,
            "dark_alley": True
        })

        final_space_id = exit_move["captain"]
        old_space = game_state["space_lookup"].get(start_space) or game_state["space_lookup"].get(str(start_space))
        if old_space:
            old_space["captain"] = False
            
        new_space = game_state["space_lookup"].get(final_space_id) or game_state["space_lookup"].get(str(final_space_id))
        if new_space is None:
            # Fallback string-to-int cast if the dictionary keys are strictly numeric types
            new_space = game_state["space_lookup"].get(int(final_space_id))
            
        if new_space:
            new_space["captain"] = True
            game_state["captain_space"] = new_space["id"] # Use the strict integer ID from the space
        else:
            return False # Fail gracefully if space structure is corrupted

        game_state["legal_moves"] = game_state["captain_graph"].get(game_state["captain_space"]) \
            or game_state["captain_graph"].get(str(game_state["captain_space"]))

        rendezvous_scored = False
        for card in player["rendezvous"]:
            if card["completed"]:
                continue
            if self.rendezvous_check(card, new_space):
                card["completed"] = True
                rendezvous_scored = True
                self.log_action(game_state, f"{player['name']} had a romantic evening with his wench <3")

        game_state["dark_alley"] = {}
        self.score_players(game_state)
        self.refresh_legal_moves(game_state)
        game_state["phase"] = "post_move"

        return self.resolve_space(game_state, new_space)

    # ── Space resolution  ──────────────────────────────────────
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
        elif space["type"] == "treasure":
            return self.treasure_space(game_state)
        elif space["type"] in ("green_map", "yellow_map", "red_map"):
            return self.map_space(game_state, player, space)
        elif space["type"] == "rendezvous":
            self.log_action(game_state, f"{player['name']} set a hot date with a wench.")
            return self.rendezvous_space(game_state)
        elif space["type"] == "supply":
            return self.supply_space(game_state, player)
        elif space["type"] in ("red_pub", "blue_pub", "green_pub"):
            color = space["type"].replace("_pub", "")
            return self.pub_space(game_state, player, color)
        elif space["type"] == "guard":
            return self.guard_space(game_state)
        else:
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
        self.log_action(game_state, f"{player['name']} added an ally to their cause.")
        game_state["phase"] = "post_move"

    def map_space(self, game_state, player, space):
        target_color = space["type"].replace("_map", "")

        matching_maps = [
            card for card in game_state["tableau"]["maps"]
            if card["color"] == target_color
        ]

        if len(matching_maps) == 0:
            self.log_action(game_state, f"{player['name']} got lost without a map!")
            game_state["phase"] = "post_move"
            return

        best_map = max(matching_maps, key=lambda card: card["points"])
        player["maps"].append(best_map)
        self.log_action(game_state, f"{player['name']} found a piece of a {target_color} map.")

        game_state["tableau"]["maps"].remove(best_map)
        game_state["tableau"]["maps"].append(game_state["decks"]["maps"].pop())

        game_state["phase"] = "post_move"
        self.score_players(game_state)

    # ----- Rendezvous -----
    def rendezvous_space(self, game_state):
        if not game_state["decks"]["rendezvous"]:
            game_state["phase"] = "post_move"
            return

        game_state["phase"] = "rendezvous_card"
        game_state["rendezvous"] = game_state["decks"]["rendezvous"].pop()
        self.score_players(game_state)

    def confirm_rendezvous(self, game_state):
        player = game_state["players"][game_state["active_player"]]
        player["rendezvous"].append(game_state["rendezvous"])
        game_state["rendezvous"] = None
        game_state["phase"] = "post_move"
        self.score_players(game_state)

    # ----- Treasure -----
    def treasure_space(self, game_state):
        player = game_state["players"][game_state["active_player"]]
        card = game_state["tableau"]["treasure"]
 
        player["treasure"].append(card)
        game_state["tableau"]["treasure"] = game_state["decks"]["treasure"].pop()
        self.log_action(game_state, f"{player['name']} found buried treasure.")
        self.score_players(game_state)
 
        return self.start_scorpion(game_state)
 
    def start_scorpion(self, game_state):
        scorpion = game_state["tableau"]["scorpion"]
        game_state["scorpion_contest"] = {
            "target": int(scorpion["dice_roll"]),
            "total": 0,
            "player_index": game_state["active_player"],
            "contest_active": True
        }
        return self.roll_start(game_state, game_state["active_player"])

    def resolve_scorpion(self, game_state):
        player_id = game_state["current_roll"]["player"]
        player = game_state["players"][player_id]
        roll_value = game_state["current_roll"]["roll"]
        player["free_rerolls"] = 0
 
        card = game_state["tableau"]["scorpion"]
        game_state["scorpion_contest"]["total"] += roll_value
 
        if game_state["scorpion_contest"]["total"] >= game_state["scorpion_contest"]["target"]:
            player["scorpions"].append(card)
            self.log_action(game_state, f"Ouch! {player['name']} got stung!")
            game_state["scorpion_contest"]["contest_active"] = False
            game_state["tableau"]["scorpion"] = game_state["decks"]["scorpions"].pop()
            game_state["phase"] = "post_move"
            self.score_players(game_state)
        else:
            next_player = (player_id + 1) % len(game_state["players"])
            game_state["scorpion_contest"]["player_index"] = next_player
            self.roll_start(game_state, next_player)

    # ----- Supply -----
    def supply_space(self, game_state, player):
        if not game_state["decks"]["supplies"]:
            game_state["phase"] = "post_move"
            return

        game_state["supply"] = game_state["decks"]["supplies"].pop()

        is_har = player["character"] is not None and player["character"]["name"] == "Captain Har the Hoarder"
        if is_har and game_state["decks"]["supplies"]:
            game_state["har_supply"] = game_state["decks"]["supplies"].pop()
            game_state["phase"] = "har_supply"
        else:
            game_state["phase"] = "supply_card"

    def resolve_supply_choice(self, game_state, keep_card):
        player = game_state["players"][game_state["active_player"]]

        if keep_card:
            player["supplies"].append(game_state["supply"])
            self.log_action(game_state, f"{player['name']} stashed the supplies for later.")
        else:
            game_state["decks"]["supplies"].insert(0, game_state["supply"])
            player["coins"] += 2
            self.log_action(game_state, f"{player['name']} sold the supplies for a profit.")

        game_state["supply"] = None
        game_state["phase"] = "post_move"
        self.score_players(game_state)

    def resolve_har_supply(self, game_state, chosen_index):

        player = game_state["players"][game_state["active_player"]]
        card_a = game_state["supply"]
        card_b = game_state["har_supply"]

        if chosen_index == 0:
            player["supplies"].append(card_a)
            game_state["decks"]["supplies"].insert(0, card_b)
            self.log_action(game_state, f"{player['name']} picked the better of two supplies.")
        elif chosen_index == 1:
            player["supplies"].append(card_b)
            game_state["decks"]["supplies"].insert(0, card_a)
            self.log_action(game_state, f"{player['name']} picked the better of two supplies.")
        else:
            game_state["decks"]["supplies"].insert(0, card_a)
            game_state["decks"]["supplies"].insert(0, card_b)
            player["coins"] += 2
            self.log_action(game_state, f"{player['name']} sold both supplies for a profit.")

        game_state["supply"] = None
        game_state["har_supply"] = None
        game_state["phase"] = "post_move"
        self.score_players(game_state)

    # ----- Pubs -----
    def pub_space(self, game_state, player, color):
        active_player = game_state["active_player"]
        is_duncan = player["character"] is not None and player["character"]["name"] == "Captain Duncan the Drunken"

        matching_cards = [
            card for card in game_state["tableau"]["pubs"]
            if card["color"] == color
        ]

        # Duncan draws a bonus tile — free if the tableau has none of this
        # color, otherwise added to the tableau for everyone to compete for.
        if is_duncan:
            matching_deck = [c for c in game_state["decks"]["pubs"] if c["color"] == color]
            if matching_deck:
                bonus = matching_deck[0]
                game_state["decks"]["pubs"].remove(bonus)
                if not matching_cards:
                    player["pubs"].append(bonus)
                    self.log_action(game_state, f"{player['name']} charmed the barkeep and claimed {bonus['points']} free pints of ale!")
                    self.score_players(game_state)
                    game_state["phase"] = "post_move"
                    return
                else:
                    game_state["tableau"]["pubs"].append(bonus)
                    self.log_action(game_state, f"{player['name']} bought the bar another round!")
                    matching_cards.append(bonus)

        if not matching_cards:
            self.log_action(game_state, f"{player['name']} went to the pub, but it was closed.")
            game_state["phase"] = "post_move"
            return

        game_state["pub"] = {
            "color": color,
            "invite_index": 1,
            "participants": [active_player],
            "rolling_index": 0,
            "current_ask": (active_player + 1) % len(game_state["players"]),
            "pub_active": False
        }
        game_state["phase"] = "pub_invite"

    def get_next_player(self, game_state, offset):
        players = game_state["players"]
        host = game_state["active_player"]
        return (host + offset) % len(players)
    
    def answer_pub_invite(self, game_state, joined):
        pub = game_state["pub"]
        players = game_state["players"]
        player_index = self.get_next_player(game_state, pub["invite_index"])
        player = players[player_index]

        if joined and player["coins"] > 0:
            pub["participants"].append(player_index)
            player["coins"] -= 1
            players[game_state["active_player"]]["coins"] += 1
            self.log_action(game_state, f"{player['name']} paid the cover fee and entered the pub.")
        else:
            self.log_action(game_state, f"{player['name']} stayed home today.")

        pub["invite_index"] += 1
        pub["current_ask"] = (pub["current_ask"] + 1) % len(players)

        if pub["invite_index"] >= len(players):
            pub["rolling_index"] = 0
            game_state["phase"] = "pub_roll"
            self.start_pub(game_state)
            return

    def start_pub(self, game_state):
        pub = game_state["pub"]
        captain_space = game_state["captain_space"]
        space_type = game_state["space_lookup"][captain_space]["type"]
        color = space_type.replace("_pub", "")
        active_player = game_state["active_player"]
        player = game_state["players"][active_player]

        if len(pub["participants"]) == 1:
            eligible_cards = [
                card for card in game_state["tableau"]["pubs"]
                if card["color"] == color
            ]
            total = sum(c["points"] for c in eligible_cards)
            self.log_action(game_state, f"{player['name']} drank {total} pints alone.")

            for c in eligible_cards:
                player["pubs"].append(c)
                game_state["tableau"]["pubs"].remove(c)

            while len(game_state["tableau"]["pubs"]) < 4 and game_state["decks"]["pubs"]:
                game_state["tableau"]["pubs"].append(game_state["decks"]["pubs"].pop())

            game_state["phase"] = "post_move"
            self.score_players(game_state)
            return

        game_state["pub"]["pub_active"] = True
        self.roll_start(game_state, active_player)

    def resolve_pub(self, game_state):
        captain_space = game_state["captain_space"]
        space_type = game_state["space_lookup"][captain_space]["type"]

        player_id = game_state["current_roll"]["player"]
        player = game_state["players"][player_id]
        roll_value = game_state["current_roll"]["roll"]
        player["free_rerolls"] = 0
        pub = game_state["pub"]

        color = space_type.replace("_pub", "")
        eligible_cards = [
            card for card in game_state["tableau"]["pubs"]
            if card["color"] == color and card["points"] < roll_value
        ]

        if not eligible_cards:
            pub["rolling_index"] = (pub["rolling_index"] + 1) % len(pub["participants"])
            next_player = pub["participants"][pub["rolling_index"]]
            return self.roll_start(game_state, next_player)

        won_card = max(eligible_cards, key=lambda card: card["points"])
        player["pubs"].append(won_card)
        game_state["tableau"]["pubs"].remove(won_card)
        self.log_action(game_state, f"{player['name']} downed {won_card['points']} pints of ale.")
        self.score_players(game_state)

        more_cards = [
            card for card in game_state["tableau"]["pubs"]
            if card["color"] == color
        ]

        if more_cards:
            pub["rolling_index"] = (pub["rolling_index"] + 1) % len(pub["participants"])
            next_player = pub["participants"][pub["rolling_index"]]
            return self.roll_start(game_state, next_player)
        else:
            while len(game_state["tableau"]["pubs"]) < 4 and game_state["decks"]["pubs"]:
                game_state["tableau"]["pubs"].append(game_state["decks"]["pubs"].pop())
            game_state["phase"] = "post_move"
            game_state["pub"]["pub_active"] = False
            self.score_players(game_state)

    # ----- Guards -----
    def guard_space(self, game_state):
        game_state["phase"] = "guard_start"
        self.score_players(game_state)

    def choose_guard(self, game_state, guard_size):
        if guard_size == "large":
            if not game_state["decks"]["large_guard"]:
                game_state["phase"] = "post_move"
                return
            game_state["guard"] = game_state["decks"]["large_guard"].pop()
        else:
            if not game_state["decks"]["small_guard"]:
                game_state["phase"] = "post_move"
                return
            game_state["guard"] = game_state["decks"]["small_guard"].pop()

        game_state["phase"] = "guard_battle"

    def resolve_guard(self, game_state):
        player = game_state["players"][game_state["active_player"]]
        card = game_state["guard"]
        category = "large_guard" if card["points"] > 3 else "small_guard"

        if player["pirates"] > card["points"] and card.get("coin_bonus", 0) > 0:
            self.log_action(game_state, f"{player['name']} defeated the guard for {card['points']} points and secured a coin.")
            player[category].append(card)
            player["coins"] += 1
        elif player["pirates"] > card["points"]:
            self.log_action(game_state, f"{player['name']} defeated the guard for {card['points']} points.")
            player[category].append(card)
        else:
            self.log_action(game_state, f"The guard made {player['name']} their bitch!")
            game_state["decks"][category].insert(0, card)

        game_state["guard"] = None
        self.score_players(game_state)

        # Fergus the Fighter — any other player at the table gets a chance
        # to intimidate the same guard for a copy of the card.
        fergus_index = next(
            (i for i, p in enumerate(game_state["players"])
             if p["character"] is not None
             and p["character"]["name"] == "Captain Fergus the Fighter"
             and i != game_state["active_player"]),
            None
        )

        if fergus_index is not None:
            game_state["fergus_guard_roll"] = {
                "fergus_index": fergus_index,
                "guard_points": card["points"],
                "category": category,
                "card": card.copy()
            }
            self.roll_start(game_state, fergus_index)
        else:
            game_state["phase"] = "post_move"

    def resolve_fergus_roll(self, game_state):
        roll_data = game_state.get("fergus_guard_roll", {})
        fergus_index = roll_data["fergus_index"]
        fergus = game_state["players"][fergus_index]
        roll = game_state["current_roll"]["roll"]
        card = roll_data["card"]
        category = roll_data["category"]

        if roll >= roll_data["guard_points"]:
            self.log_action(game_state, f"{fergus['name']} intimidated the guard and also claimed {card['points']} points!")
            fergus[category].append(card)
            self.score_players(game_state)
        else:
            self.log_action(game_state, f"{fergus['name']} failed to intimidate the guard.")

        game_state["fergus_guard_roll"] = None
        game_state["phase"] = "post_move"

    # ── Dice Rolling ────────────────────────────────────────────────────────
    def roll_start(self, game_state, player_index):
        game_state["next_roller"] = player_index
        game_state["phase"] = "roll_start"
 
    def roll_die(self):
        return random.randint(1, 6)
 
    def roll(self, game_state, player_index):
        roll_value = self.roll_die()
        player = game_state["players"][player_index]
        game_state["current_roll"] = {
            "player": player_index,
            "roll": roll_value,
            "image": f"die_{roll_value}.png"
        }
 
        if player["free_rerolls"] > 0:
            game_state["phase"] = "roll_with_rerolls"
        elif player["barrels"] > 0:
            game_state["phase"] = "roll_with_barrels"
        else:
            game_state["phase"] = "roll_no_barrels"
 
    def resolve_reroll(self, game_state):
        player_id = game_state["current_roll"]["player"]
        player = game_state["players"][player_id]
 
        if game_state["phase"] == "roll_with_barrels":
            player["barrels"] -= 1
            player["free_rerolls"] += 1
            self.log_action(game_state, f"{player['name']} used a barrel to roll again.")
            self.roll_start(game_state, player_id)
        elif game_state["phase"] == "roll_with_rerolls":
            player["free_rerolls"] -= 1
            self.roll_start(game_state, player_id)
 
    def resolve_roll(self, game_state):
        """
        Accepts the current roll and dispatches based on what triggered it.
        Only the treasure/scorpion contest is migrated so far — wrangle and
        Fergus's guard roll are left alone (not yet server-side), and any
        other roll type just falls through safely.
        """
        captain_space = game_state["captain_space"]
        space_type = game_state["space_lookup"][captain_space]["type"]
        player_id = game_state["current_roll"]["player"]
        game_state["players"][player_id]["free_rerolls"] = 0
 
        if game_state.get("wrangle", {}).get("active"):
            return  # not yet migrated
        if game_state.get("fergus_guard_roll") is not None:
            return self.resolve_fergus_roll(game_state)
        if space_type == "treasure":
            return self.resolve_scorpion(game_state)
        if space_type in ("blue_pub", "green_pub", "red_pub"):
            return self.resolve_pub(game_state)

    # ── Turn flow ────────────────────────────────────────────────────────
    def move_again(self, game_state):
        current = game_state["active_player"]
        player = game_state["players"][current]
        if player["coins"] == 0:
            return False
        player["coins"] -= 1
        self.log_action(game_state, f"{player['name']} spent a coin to move again.")
        if not game_state["legal_moves"]:
            self.teleport_captain(game_state)
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

        if not game_state["legal_moves"]:
            self.teleport_captain(game_state)
        
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