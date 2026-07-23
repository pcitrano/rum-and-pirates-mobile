import copy

class game_setup:
    """
    Thin-client version of game_setup.

    Board generation, deck shuffling, graph building, and all other game
    logic have moved to the server (ServerGameSetup / ServerGameplay).
    This class now has two jobs:
      1. Hold references to locally-loaded assets (tiles for rendering,
         dice images) so game_ui can reach them via self.setup.
      2. Produce the initial menu-only game_state that game_ui needs
         before any server interaction begins.
    """

    def __init__(self, database, start_in_menu=False):
        # Asset references kept for board rendering in game_ui.
        # create_board_from_seed (called inside apply_network_state) uses
        # self.tiles to rotate and composite tile images into the board surface.
        self.tiles = database.tiles
        self.dice  = database.dice

        self.game_state = self.game_setup(start_in_menu=True)

    # ── Board rendering (client-side only) ────────────────────────────────
    # These methods are still needed because apply_network_state calls
    # self.setup.create_board_from_seed(state["board_seed"]) to reconstruct
    # the board image from the seed the server sends.

    def create_board_from_seed(self, seed):
        import cv2
        import numpy as np

        tile_lookup = {
            tile["properties"]["num_tile"]: tile
            for tile in self.tiles.values()
        }

        tile_size   = 300
        board_width  = tile_size * 3
        board_height = tile_size * 3
        grid_size    = 3
        board        = np.zeros((board_height, board_width, 3), dtype=np.uint8)
        all_spaces   = []

        for i, entry in enumerate(seed):
            tile       = tile_lookup[entry["tile_num"]]
            image      = tile["image"]
            properties = tile["properties"]
            tile_num   = properties["num_tile"]
            rotation   = entry["rotation"]

            rotated_img, rotated_spaces = self.rotate_tile(image, properties, rotation)

            col      = i % grid_size
            row      = i // grid_size
            offset_x = col * tile_size
            offset_y = row * tile_size

            rotated_img = cv2.resize(rotated_img, (tile_size, tile_size),
                                     interpolation=cv2.INTER_AREA)
            board[offset_y:offset_y + tile_size,
                  offset_x:offset_x + tile_size] = rotated_img

            for space in rotated_spaces:
                space["tile_num"] = tile_num
                space["board_x"]  = int(space["x"] * tile_size) + offset_x
                space["board_y"]  = int(space["y"] * tile_size) + offset_y
                all_spaces.append(space)

        space_lookup = {s["id"]: s for s in all_spaces}

        # Connect adjacent edge spaces (same logic as before)
        edge_spaces       = [s for s in all_spaces if s["type"] == "edge"]
        spaces_to_remove  = set()
        new_spaces        = []
        next_space_id     = max(s["id"] for s in all_spaces) + 1
        MAX_DIST          = 80

        for i, space_a in enumerate(edge_spaces):
            for space_b in edge_spaces[i + 1:]:
                if space_a["id"] in spaces_to_remove or space_b["id"] in spaces_to_remove:
                    continue
                dx = space_a["board_x"] - space_b["board_x"]
                dy = space_a["board_y"] - space_b["board_y"]
                if (dx*dx + dy*dy) ** 0.5 < MAX_DIST:
                    mid_x        = int((space_a["board_x"] + space_b["board_x"]) / 2)
                    mid_y        = int((space_a["board_y"] + space_b["board_y"]) / 2)
                    _raw = (
                        [n for n in space_a["neighbors"] if n != space_b["id"]] +
                        [n for n in space_b["neighbors"] if n != space_a["id"]]
                    )
                    seen = set()
                    neighbor_ids = [n for n in _raw if not (n in seen or seen.add(n))]
                    new_space = {
                        "id": next_space_id, "type": "normal",
                        "tile_num": None, "board_x": mid_x, "board_y": mid_y,
                        "neighbors": neighbor_ids, "occupant": None,
                    }
                    new_spaces.append((new_space, space_a, space_b))
                    spaces_to_remove.add(space_a["id"])
                    spaces_to_remove.add(space_b["id"])
                    next_space_id += 1

        for new_space, edge_a, edge_b in new_spaces:
            for nid in new_space["neighbors"]:
                neighbor = space_lookup[nid]
                neighbor["neighbors"] = [
                    new_space["id"] if x in (edge_a["id"], edge_b["id"]) else x
                    for x in neighbor["neighbors"]
                ]
            all_spaces.append(new_space)

        all_spaces   = [s for s in all_spaces if s["id"] not in spaces_to_remove]
        space_lookup = {s["id"]: s for s in all_spaces}

        for space in all_spaces:
            if space["type"] == "edge" and len(space["neighbors"]) == 1:
                space["type"] = "dark_alley"
            clickable     = space["type"] not in ("normal", "edge")
            captain_space = space["type"] not in ("normal", "edge", "dark_alley")
            space["captain_space"]  = captain_space
            space["clickable"]      = clickable
            space["hitbox_radius"]  = (
                0.04 * tile_size if (clickable and space["type"] == "edge")
                else 0.07 * tile_size if clickable
                else 0
            )
            space["required_pirates"] = 1 if space["type"] in ("normal", "dark_alley") else 0
            space["occupant"] = None
            space["captain"]  = False

        return board, all_spaces

    def rotate_tile(self, image, properties, rotation):
        import cv2
        import copy as _copy
        rotated_img = image.copy()
        spaces      = _copy.deepcopy(properties["spaces"])
        if rotation == 90:
            rotated_img = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            rotated_img = cv2.rotate(image, cv2.ROTATE_180)
        elif rotation == 270:
            rotated_img = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        for space in spaces:
            x, y = space["x"], space["y"]
            if rotation == 90:
                space["x"], space["y"] = 1.0 - y, x
            elif rotation == 180:
                space["x"], space["y"] = 1.0 - x, 1.0 - y
            elif rotation == 270:
                space["x"], space["y"] = y, 1.0 - x
        return rotated_img, spaces

    # ── Menu-only game state ──────────────────────────────────────────────
    def game_setup(self, start_in_menu=False):
        """
        Returns the minimal game_state needed to show the main menu.
        All gameplay fields are empty/None — the server populates them
        when a game starts and pushes them via state_updated.
        """
        return {
            "menu": {
                "menu_level":    "main",
                "stats_scroll":  0,
                "player_count":  2,
                "player_names":  ["", "", "", "", ""],
                "room_code_input": "",
                "lobby_players": [],
                "open_rooms":    [],
                "lobby_error":   None,
                "server_ip_input": "",
                "multiplayer_mode": None,
                "active_games":  [],
                "games_loading": False,
                "rooms_loading": False,
            },

            "selected_field": None,
            "chat":           {"messages": [], "input": ""},

            # Board / graph — all empty; filled by apply_network_state
            "spaces":        [],
            "space_lookup":  {},
            "captain_space": 20,
            "captain_graph": {},
            "legal_moves":   {},
            "alley_lookup":  {},
            "coin_lookup":   {},
            "pending_move":  None,
            "dark_alley":    {},
            "occupied_paths":[],
            "reclaim_1":     None,
            "reclaim_2":     None,

            # Players / round — filled by server
            "players":              [],
            "character_hands":      [],
            "character_selections": [],
            "character_confirmed":  [],
            "starting_player":      0,
            "active_player":        0,
            "round":                1,
            "action_log":           [],
            "phase": "menu" if start_in_menu else "start_turn",

            # Space resolution state — filled by server
            "supply":            None,
            "har_supply":        None,
            "har_selection":     None,
            "rendezvous":        None,
            "guard":             None,
            "current_roll":      {},
            "pub":               {"color": None, "invite_index": 0, "participants": [],
                                  "rolling_index": 0, "current_ask": 0, "pub_active": False},
            "scorpion_contest":  {"target": 0, "total": 0, "player_index": 0, "contest_active": False},
            "next_roller":       None,
            "wrangle":           {"active": False, "round": 0, "eliminated": [],
                                  "leader": None, "leader_roll": None, "queue": {}},
            "fergus_guard_roll": None,

            # Decks / tableau — filled by server; kept as empty stubs so
            # game_ui can reference them safely before the first state_updated.
            "tableau": {
                "pubs": [], "maps": [], "treasure": None, "scorpion": None,
                "wrangle_bunk": None, "wrangle_hammock": None, "wrangle_bedroll": None,
            },
            "decks": {},
            "board": None,
        }