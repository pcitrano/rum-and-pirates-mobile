"""
server_game_setup.py

Server-side port of game_setup.py's board logic.

Key difference from the desktop version: this never touches actual tile
images. The desktop/web clients already fetch tile images directly from
/assets/tiles/tile_N.jpg and re-draw the board themselves. The server only
needs the *geometry* (space positions, neighbors, the movement graph) so it
can validate moves and run game logic authoritatively.

Tile JSON is loaded straight from the assets folder already being served
by server.py, so there's a single source of truth for board data.
"""

import json
import os
import random
import copy

TILE_SIZE = 300  # must match the client's TILE_SIZE for coordinates to agree
MAX_CONNECTION_DISTANCE = 80
START_SPACE_ID = 20


class ServerGameSetup:
    def __init__(self, assets_dir="assets/tiles"):
        self.assets_dir = assets_dir
        self.tiles = self.load_all_tiles()

    # ── Loading ────────────────────────────────────────────────────────────

    def load_all_tiles(self):
        tiles = {}
        for tile_number in range(1, 10):
            path = os.path.join(self.assets_dir, f"tile_{tile_number}.json")
            with open(path, "r") as f:
                properties = json.load(f)
            tiles[tile_number] = properties
        return tiles

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

        # ── Connect adjacent tile edges ──
        edge_spaces = [s for s in all_spaces if s["type"] == "edge"]
        spaces_to_remove = set()
        new_spaces = []
        next_space_id = max(space["id"] for space in all_spaces) + 1

        for space_a in edge_spaces:
            for space_b in edge_spaces:
                if space_a["id"] >= space_b["id"]:
                    continue
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
