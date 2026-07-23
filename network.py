import socketio

class network_manager:
    def __init__(self):
        self.sio = socketio.Client()
        self.room_id = None
        self.connected = False
        self.incoming_state = None   # set when server pushes a state update
        self.incoming_action = None  # set when server pushes an action
        self.lobby_players = []
        self.join_error = False  # set True if room not found
        self.player_index = None
        self.disconnected = False
        self.reconnected = False
        self.join_error_message = None
        self.incoming_chat = []
        self.new_chat_message = False

        @self.sio.on("room_created")
        def on_room_created(data):
            self.room_id = data["room_id"]
            #print(f"[network] room_created: {data}")

        @self.sio.on("room_joined")
        def on_room_joined(data):
            self.room_id = data["room_id"]
            self.player_index = data["player_index"]
            self.reconnected = data.get("reconnected", False)

        @self.sio.on("error")
        def on_error(data):
            self.join_error = True

        @self.sio.on("state_updated")
        def on_state_updated(data):
            self.incoming_state = data["game_state"]
            #print(f"[network] state_updated received, phase: {data['game_state'].get('phase')}")

        @self.sio.on("action_received")
        def on_action_received(data):
            self.incoming_action = data

        @self.sio.on("player_joined")
        def on_player_joined(data):
            self.lobby_players = data["players"]
            #print(f"[network] player_joined: {data}")

        @self.sio.on("disconnect")
        def on_disconnect():
            self.disconnected = True
            print("[network] disconnected from server")

        @self.sio.on("connect")
        def on_connect():
            self.disconnected = False
            print("[network] connected to server")

        @self.sio.on("player_reconnected")
        def on_player_reconnected(data):
            print(f"[network] {data['name']} reconnected")

        @self.sio.on("rejoined")
        def on_rejoined(data):
            self.room_id = data["room_id"]
            self.player_index = data.get("player_index")
            self.reconnected = True
        
        @self.sio.on("rejoin_error")
        def on_rejoin_error(data):
            self.join_error = True
            self.join_error_message = data["message"]
        
        @self.sio.on("chat")
        def on_chat(data):
            self.incoming_chat.append(data)
            self.new_chat_message = True

    def connect(self, server_url="http://localhost:5000"):
        self.sio.connect(server_url)
        self.connected = True

    def create_room(self, player_name):
        self.sio.emit("create_room", {"name": player_name})

    def join_room(self, room_id, player_name):
        self.sio.emit("join_room", {"room_id": room_id, "name": player_name})

    def send_state(self, game_state):
        self.sio.emit("update_state", {"room_id": self.room_id, "game_state": game_state})

    def send_action(self, action):
        self.sio.emit("player_action", {"room_id": self.room_id, **action})

    def start_game(self, game_state):
        self.sio.emit("start_game", {"room_id": self.room_id, "game_state": game_state})

    def reconnect(self, server_url, room_id, player_name):
        try:
            self.sio.connect(server_url)
            self.sio.emit("join_room", {"room_id": room_id, "name": player_name})
        except Exception as e:
            print(f"[network] reconnect failed: {e}")

    def send_chat(self, message):
        self.sio.emit("chat", {"room_id": self.room_id, "text": message})