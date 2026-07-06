import json
import os
import random
import copy

TILE_SIZE = 300  # must match the client's TILE_SIZE for coordinates to agree
MAX_CONNECTION_DISTANCE = 80
START_SPACE_ID = 20


class ServerGameSetup:
    def __init__(self, tiles_dir="assets/tiles", cards_path="assets/cards.json"):
        self.tiles_dir = tiles_dir
        self.cards_path = cards_path
        self.tiles = self.load_all_tiles()
        self.cards = self.load_cards()

    # ── Loading ────────────────────────────────────────────────────────────

    def load_all_tiles(self):
        tiles = {}
        for tile_number in range(1, 10):
            path = os.path.join(self.tiles_dir, f"tile_{tile_number}.json")
            with open(path, "r") as f:
                properties = json.load(f)
            tiles[tile_number] = properties
        return tiles

    def load_cards(self):
        with open(self.cards_path, "r") as f:
            return json.load(f)

    # ── Board creation ─────────────────────────────────────────────────────

    def generate_random_board_seed(self):
        tile_nums = list(self.tiles.keys())
        random.shuffle(tile_nums)

        seed = []
        for tile_num in tile_nums:
            seed.append({
                "tile_num": tile_num,
                "rotation": random.choice([0, 90, 180, 270])
            })
        return seed

    def rotate_normalized_point(self, x, y, rotation):
        if rotation == 0:
            return x, y
        elif rotation == 90:
            return 1.0 - y, x
        elif rotation == 180:
            return 1.0 - x, 1.0 - y
        elif rotation == 270:
            return y, 1.0 - x

    def rotate_tile_spaces(self, properties, rotation):
        spaces = copy.deepcopy(properties["spaces"])
        for space in spaces:
            new_x, new_y = self.rotate_normalized_point(space["x"], space["y"], rotation)
            space["x"] = new_x
            space["y"] = new_y
        return spaces

    def create_board_from_seed(self, seed):
        grid_size = 3
        all_spaces = []

        for i, entry in enumerate(seed):
            properties = self.tiles[entry["tile_num"]]
            tile_num = properties["num_tile"]
            rotation = entry["rotation"]

            rotated_spaces = self.rotate_tile_spaces(properties, rotation)

            col = i % grid_size
            row = i // grid_size
            offset_x = col * TILE_SIZE
            offset_y = row * TILE_SIZE

            for space in rotated_spaces:
                space["tile_num"] = tile_num
                local_x = int(space["x"] * TILE_SIZE)
                local_y = int(space["y"] * TILE_SIZE)
                space["board_x"] = local_x + offset_x
                space["board_y"] = local_y + offset_y
                all_spaces.append(space)

        space_lookup = {space["id"]: space for space in all_spaces}

        edge_spaces = sorted(
            [s for s in all_spaces if s["type"] == "edge"],
            key=lambda s: s["id"]
        )
        spaces_to_remove = set()
        new_spaces = []
        next_space_id = max(space["id"] for space in all_spaces) + 1

        for i in range(len(edge_spaces)):
            for j in range(i + 1, len(edge_spaces)):
                space_a = edge_spaces[i]
                space_b = edge_spaces[j]
                if space_a["id"] in spaces_to_remove or space_b["id"] in spaces_to_remove:
                    continue

                dx = space_a["board_x"] - space_b["board_x"]
                dy = space_a["board_y"] - space_b["board_y"]
                distance = (dx ** 2 + dy ** 2) ** 0.5

                if distance < MAX_CONNECTION_DISTANCE:
                    mid_x = int((space_a["board_x"] + space_b["board_x"]) / 2)
                    mid_y = int((space_a["board_y"] + space_b["board_y"]) / 2)

                    neighbor_ids = []
                    for nid in space_a["neighbors"]:
                        if nid != space_b["id"]:
                            neighbor_ids.append(nid)
                    for nid in space_b["neighbors"]:
                        if nid != space_a["id"]:
                            neighbor_ids.append(nid)
                    neighbor_ids = list(set(neighbor_ids))

                    new_space = {
                        "id": next_space_id,
                        "type": "normal",
                        "tile_num": None,
                        "board_x": mid_x,
                        "board_y": mid_y,
                        "neighbors": neighbor_ids,
                        "occupant": None
                    }

                    new_spaces.append((new_space, space_a, space_b))
                    spaces_to_remove.add(space_a["id"])
                    spaces_to_remove.add(space_b["id"])
                    next_space_id += 1

        for new_space, edge_a, edge_b in new_spaces:
            for neighbor_id in new_space["neighbors"]:
                neighbor = space_lookup[neighbor_id]
                neighbor["neighbors"] = [
                    new_space["id"] if x in (edge_a["id"], edge_b["id"]) else x
                    for x in neighbor["neighbors"]
                ]
            all_spaces.append(new_space)

        all_spaces = [s for s in all_spaces if s["id"] not in spaces_to_remove]
        space_lookup = {s["id"]: s for s in all_spaces}

        # ── Classify spaces ──
        for space in all_spaces:
            if space["type"] == "edge" and len(space["neighbors"]) == 1:
                space["type"] = "dark_alley"

            edge_radius = 0.04 * TILE_SIZE
            center_radius = 0.07 * TILE_SIZE

            clickable = True
            captain_space = True
            if space["type"] in ("normal", "edge"):
                clickable = False
            if space["type"] in ("normal", "edge", "dark_alley"):
                captain_space = False
            space["captain_space"] = captain_space
            space["clickable"] = clickable

            if space["clickable"] and space["type"] == "edge":
                space["hitbox_radius"] = edge_radius
            elif space["clickable"]:
                space["hitbox_radius"] = center_radius
            else:
                space["hitbox_radius"] = 0

            space["required_pirates"] = 1 if space["type"] in ("normal", "dark_alley") else 0
            space["occupant"] = None
            space["captain"] = False

        return all_spaces

    # ── Movement graph ─────────────────────────────────────────────────────

    def search_path(self, start_id, current_id, path, cost, captain_graph, space_lookup):
        current = space_lookup[current_id]

        if current["captain_space"] and current_id != start_id:
            captain_graph[start_id].append({
                "destination": current_id,
                "destination_type": "captain_space",
                "path": path,
                "cost": cost
            })
            return

        if current["type"] == "dark_alley":
            captain_graph[start_id].append({
                "destination": current_id,
                "destination_type": "dark_alley",
                "path": path + [current_id],
                "cost": cost + current["required_pirates"]
            })
            return

        new_path = path + [current_id]
        new_cost = cost + current["required_pirates"]

        for neighbor_id in current["neighbors"]:
            if neighbor_id == start_id or neighbor_id in new_path:
                continue
            self.search_path(start_id, neighbor_id, new_path, new_cost, captain_graph, space_lookup)

    def explore_from_captain(self, start_id, captain_graph, space_lookup):
        start_space = space_lookup[start_id]
        for neighbor_id in start_space["neighbors"]:
            self.search_path(start_id, neighbor_id, [], 0, captain_graph, space_lookup)
        return captain_graph

    # ── Full board + graph generation ──────────────────────────────────────

    def generate_board(self, game_state):
        seed = self.generate_random_board_seed()
        game_state["board_seed"] = seed

        all_spaces = self.create_board_from_seed(seed)
        space_lookup = {s["id"]: s for s in all_spaces}
        captain_spaces = [s["id"] for s in all_spaces if s["captain_space"]]

        space_lookup[START_SPACE_ID]["captain"] = True

        captain_graph = {}
        for captain_id in captain_spaces:
            captain_graph[captain_id] = []
            self.explore_from_captain(captain_id, captain_graph, space_lookup)

        alley_lookup = {}
        for captain_id, moves in captain_graph.items():
            for move in moves:
                for space_id in move["path"]:
                    space = space_lookup[space_id]
                    if space["type"] == "dark_alley":
                        alley_lookup[space_id] = {
                            "captain": captain_id,
                            "path": move["path"],
                            "cost": move["cost"]
                        }

        coin_lookup = {}
        for space in all_spaces:
            if space["type"] == "coin":
                coin_lookup[space["tile_num"]] = space["id"]

        game_state["spaces"] = all_spaces
        game_state["space_lookup"] = space_lookup
        game_state["captain_graph"] = captain_graph
        game_state["captain_space"] = START_SPACE_ID
        game_state["legal_moves"] = captain_graph[START_SPACE_ID]
        game_state["alley_lookup"] = alley_lookup
        game_state["coin_lookup"] = coin_lookup

        return game_state

    # ── Players ─────────────────────────────────────────────────────────────

    def create_players(self, num_of_players, player_names=None):
        if player_names is not None and len(player_names) != num_of_players:
            raise ValueError("Length of player_names must match num_of_players")

        if num_of_players > 5 or num_of_players < 2:
            raise ValueError("Number of players must be between 2 and 5")

        player_colors = [
            (0, 0, 175),      # Blue
            (0, 175, 0),      # Green
            (175, 0, 175),    # Pink
            (225, 125, 25),   # Orange
            (25, 225, 225)    # Turquoise
        ]
        random.shuffle(player_colors)
        players = []

        for i in range(num_of_players):
            name = player_names[i] if player_names else f"Player {i + 1}"
            players.append({
                "id": i + 1,
                "name": name,
                "color": player_colors[i],
                "character": None,

                "score": {"total": 0, "pubs": 0, "maps": 0, "guards": 0, "rendezvous": 0,
                           "treasure": 0, "scorpions": 0, "supplies": 0, "wrangle": 0},

                "pirates": 10,
                "pirates_on_board": 0,
                "pirate_reserve": 5,
                "board_position": 0,
                "wrangle_pirates": 0,
                "safe_pirates": 0,

                "coins": 2,
                "barrels": 0,
                "free_rerolls": 0,

                "pubs": [],
                "rendezvous": [],
                "large_guard": [],
                "small_guard": [],
                "treasure": [],
                "scorpions": [],
                "supplies": [],
                "maps": [],
                "wrangles": []
            })

        return players

    def create_character_ids(self, num_of_players):
        characters = [
            {"name": "Captain Duncan the Drunken", "image": "char_duncan.png"},
            {"name": "Captain Cutthroat the Cartographer", "image": "char_cutthroat.png"},
            {"name": "Captain Drake the Distiller", "image": "char_drake.png"},
            {"name": "Captain Sterling the Scoundrel", "image": "char_sterling.png"},
            {"name": "Captain Pete the Popular", "image": "char_pete.png"},
            {"name": "Captain Sullivan the Scorpion Tamer", "image": "char_sullivan.png"},
            {"name": "Captain Har the Hoarder", "image": "char_har.png"},
            {"name": "Captain Nought the Night Owl", "image": "char_nought.png"},
            {"name": "Captain Argh the Alley Bandit", "image": "char_argh.png"},
            {"name": "Captain Fergus the Fighter", "image": "char_fergus.png"},
            {"name": "Captain Midas the Master of Coin", "image": "char_midas.png"},
        ]

        random.shuffle(characters)
        hands = []
        for i in range(num_of_players):
            hands.append(characters[i * 2:(i * 2) + 2])
        return hands

    # ── Decks & tableau ───────────────────────────────────────────────────

    def create_card_decks(self):
        cards = self.cards
        decks = {
            "pubs": copy.deepcopy(cards["pubs"]),
            "maps": copy.deepcopy(cards["maps"]),
            "treasure": copy.deepcopy(cards["treasure"]),
            "scorpions": copy.deepcopy(cards["scorpions"]),
            "large_guard": copy.deepcopy(cards["large_guard"]),
            "small_guard": copy.deepcopy(cards["small_guard"]),
            "supplies": copy.deepcopy(cards["supply"]),
            "rendezvous": copy.deepcopy(cards["rendezvous"]),
            "wrangle_bunk": copy.deepcopy(cards["wrangle_bunk"]),
            "wrangle_hammock": copy.deepcopy(cards["wrangle_hammock"]),
            "wrangle_bedroll": copy.deepcopy(cards["wrangle_bedroll"])
        }
        for deck in decks.values():
            random.shuffle(deck)
        return decks

    def draw_starting_cards(self, decks):
        tableau = {
            "pubs": [],
            "maps": [],
            "treasure": None,
            "scorpion": None,
            "wrangle_bunk": None,
            "wrangle_hammock": None,
            "wrangle_bedroll": None
        }
        for _ in range(4):
            tableau["pubs"].append(decks["pubs"].pop())
        for _ in range(4):
            tableau["maps"].append(decks["maps"].pop())
        tableau["treasure"] = decks["treasure"].pop()
        tableau["scorpion"] = decks["scorpions"].pop()
        tableau["wrangle_bunk"] = decks["wrangle_bunk"].pop()
        tableau["wrangle_hammock"] = decks["wrangle_hammock"].pop()
        tableau["wrangle_bedroll"] = decks["wrangle_bedroll"].pop()
        return tableau

    # ── Full game state ───────────────────────────────────────────────────

    def new_game_state(self, player_names, play_with_characters=False, random_start=False):
        """
        Builds a complete, ready-to-play game_state entirely on the server:
        board, players, character hands (if enabled), decks and tableau.

        player_names: list of connected players' names, in lobby order.
        """
        num_players = len(player_names)

        decks = self.create_card_decks()
        tableau = self.draw_starting_cards(decks)

        players = self.create_players(num_players, player_names)
        random.shuffle(players)
        for i, player in enumerate(players):
            player["id"] = i + 1

        game_state = {
            "spaces": [],
            "space_lookup": {},
            "captain_space": START_SPACE_ID,
            "captain_graph": {},
            "legal_moves": {},
            "alley_lookup": {},
            "coin_lookup": {},
            "pending_move": None,
            "occupied_paths": [],
            "reclaim_1": None,
            "reclaim_2": None,

            "players": players,
            "character_hands": [],
            "character_selections": [None] * num_players,
            "character_confirmed": [False] * num_players,
            "starting_player": 0,
            "active_player": 0,
            "round": 1,
            "action_log": ["New Game"],

            "supply": None,
            "har_supply": None,
            "har_selection": None,
            "rendezvous": None,
            "guard": None,

            "current_roll": {},
            "pub": {"color": None, "invite_index": 0, "participants": [], "rolling_index": 0, "current_ask": 0, "pub_active": False},
            "scorpion_contest": {"target": 0, "total": 0, "player_index": 0, "contest_active": False},
            "next_roller": None,
            "wrangle": {"active": False, "round": 0, "eliminated": [], "leader": None, "leader_roll": None, "queue": {}},
            "fergus_guard_roll": None,

            "tableau": tableau,
            "decks": decks,
        }

        if play_with_characters:
            game_state["character_hands"] = self.create_character_ids(num_players)
            game_state["phase"] = "character_select"
            # Board is generated after character selection, on confirm
        else:
            game_state = self.generate_board(game_state)
            if random_start:
                self._apply_random_start(game_state)
            game_state["phase"] = "start_turn"

        return game_state

    def _apply_random_start(self, game_state):
        captain_spaces = [s["id"] for s in game_state["spaces"] if s.get("captain_space")]
        if not captain_spaces:
            return
        new_start = random.choice(captain_spaces)
        game_state["space_lookup"][game_state["captain_space"]]["captain"] = False
        game_state["space_lookup"][new_start]["captain"] = True
        game_state["captain_space"] = new_start
        game_state["legal_moves"] = game_state["captain_graph"][new_start]

    def finish_character_select(self, game_state, random_start=False):
        hands = game_state.get("character_hands", [])
        selections = game_state.get("character_selections", [])

        for i, player in enumerate(game_state["players"]):
            selected_name = selections[i]
            hand = hands[i]
            character = next((c for c in hand if c["name"] == selected_name), hand[0])
            player["character"] = character

            # Captain Pete the Popular — starts with one extra pirate
            if character["name"] == "Captain Pete the Popular" and player["pirate_reserve"] > 0:
                player["pirates"] += 1
                player["pirate_reserve"] -= 1

        game_state.pop("character_hands", None)
        game_state.pop("character_selections", None)
        game_state.pop("character_confirmed", None)

        game_state = self.generate_board(game_state)
        if random_start:
            self._apply_random_start(game_state)

        game_state["phase"] = "start_turn"
        return game_state