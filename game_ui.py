import pygame
import cv2
import numpy as np
import random
import json
import copy
import sys
from network import network_manager
import os

SERVER_URL = "https://rumandpirates.up.railway.app"

class Button:

    def __init__(self, x, y, width, height, text, action, color=(180, 180, 180), text_color=(0,0,0)):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.action = action
        self.color = color
        self.text_color = text_color

    def draw(self, screen, font):
        pygame.draw.rect(screen, self.color, self.rect)

        words = self.text.split(" ")
        line = ""
        lines = []
        for word in words:
            test_line = line + word + " "
            line_width, _ = font.size(test_line)
            if line_width > self.rect.width - 10 and line:
                lines.append(line.strip())
                line = word + " "
            else:
                line = test_line
        if line:
            lines.append(line.strip())

        total_height = len(lines) * font.get_linesize()
        y = self.rect.centery - total_height // 2

        for line in lines:
            rendered = font.render(line, True, self.text_color)
            x = self.rect.centerx - rendered.get_width() // 2
            screen.blit(rendered, (x, y))
            y += font.get_linesize()

    def draw_transparent(self, screen, font):

        button_surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        alpha = 0
        button_color = (80, 80, 80, alpha)
        pygame.draw.rect(button_surf, button_color, (0, 0, *self.rect.size))

        words = self.text.split(" ")
        line = ""
        lines = []
        for word in words:
            test_line = line + word + " "
            line_width, _ = font.size(test_line)
            if line_width > self.rect.width - 10 and line:
                lines.append(line.strip())
                line = word + " "
            else:
                line = test_line
        if line:
            lines.append(line.strip())

        total_height = len(lines) * font.get_linesize()
        y = (self.rect.height - total_height) // 2

        for line in lines:
            rendered = font.render(line, True, self.text_color)
            x = (self.rect.width - rendered.get_width()) // 2
            button_surf.blit(rendered, (x, y))
            y += font.get_linesize()

        screen.blit(button_surf, self.rect.topleft)

class game_ui:
    # Layout constants to resize everything
    LEFT_PANEL_RATIO = 252 / 1600
    RIGHT_PANEL_RATIO = 304 / 1600
    CARD_WIDTH_RATIO = 60 / 1600
    CARD_HEIGHT_RATIO = 60 / 1600
    CARD_BUFFER_RATIO = 10 / 1600
    ORIGINAL_BOARD_SIZE = 900
    INVENTORY_HEIGHT = 250 / 900
    INV_CARD_SIZE = 37 / 900
    CHAR_CARD_HEIGHT = 400 / 900
    CHAR_CARD_WIDTH = 290 / 1600

    @property
    def width(self):
        return self.screen.get_width()

    @property
    def height(self):
        return self.screen.get_height()
    
    @property
    def inventory_height(self):
        if not self.inventory_open:
            return 0 
        return int(250/900 * self.height)
    
    @property
    def left_panel_width(self):
        return int(256/1600 * self.width)
    
    @property
    def left_panel_x(self):
        return int(80/1600 * self.width)

    @property
    def board_x(self):
        return int(405/1600 * self.width)
    
    @property
    def board_y(self):
        return int(100/750 * self.height)

    @property
    def board_width(self):
        return int(790/1600 * self.width)
        
    @property
    def board_height(self):
        return int(610/750 * self.height)

    @property
    def right_panel_x(self):
        return int(1267/1600 * self.width)

    @property
    def right_panel_width(self):
        return int(310/1600 * self.width)

    @property
    def card_size(self):
        return int(self.width * self.CARD_WIDTH_RATIO)
    
    @property
    def small_card_size(self):
        return int(self.height * self.INV_CARD_SIZE)
    
    ######################################################################
    # INITIALISATION & MAIN LOOP
    ######################################################################

    def __init__(self, game_state, rules, setup, save_data, card_images, dice_images, ui_images, font_path, base_path):
        self.save_data = save_data
        
        pygame.init() 
        self.screen = self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN) if self.save_data.settings["fullscreen"] else pygame.display.set_mode((1600,900), pygame.RESIZABLE)
        pygame.display.set_caption("Rum & Pirates")
        
        self.splash_start_time = pygame.time.get_ticks()
        self.show_splash = True
        self.save_data = save_data
        self.game_state = game_state 
        self.rules = rules
        self.setup = setup
        self.base_path = base_path
        self.running = True 
        self.buttons = []
        self.transparent_buttons = []
        self.font = pygame.font.Font(font_path, 30)
        self.small_font = pygame.font.Font(font_path, 20)
        self.menu_font = pygame.font.Font(font_path, 50)
        
        # Collapsible UI
        self.inventory_open = False
        self.chat_open = False
        self.active_character_card = None
        
        self.raw_card_images = card_images
        self.rescale_cards(card_images)
        self.raw_die_images = dice_images
        self.rescale_dice(dice_images)
        self.raw_ui_images = ui_images
        self.rescale_ui(ui_images)

        self.menu_frame = 0
        self.menu_frame_timer = 0
        self.menu_animation_fps = 60

        # Drawing board
        if self.game_state.get("board") is not None:
            self.raw_board = self.game_state["board"]
            self.rescale_board()
        else:
            self.raw_board = None
            self.board_surface = None 

        # precreate button surfaces
        self.menu_button_surface = pygame.Surface((225,40), pygame.SRCALPHA)

        # Networking
        self.network = None      # set when hosting or joining
        self.room_id = None
        self.is_host = False
        self.my_player_index = None  # which player slot am I?
        self.lobby_players = []
        self.stats = self.save_data.load_stats_from_server()

        # Chat
        self.chat_messages = []
        self.chat_input_text = ""
        self.chat_read_messages = None
        self.chat_notification = False

        if self.rules is not None:
            self.rules.broadcast = self.broadcast_state

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            self.handle_events()
            dt = clock.tick(30)
            
            if self.game_state.get("phase") == "menu":
                self.menu_frame_timer += dt
                frames = self.ui_images.get("menu_animation", [])
                if frames and self.menu_frame_timer >= 1000 / self.menu_animation_fps:
                    self.menu_frame_timer = 0 
                    self.menu_frame = (self.menu_frame + 1) % len(frames)
            
            if self.show_splash and pygame.time.get_ticks() - self.splash_start_time > 5000:
                self.show_splash = False
            self.poll_network()
            self.draw()

            if self.game_state.get("phase") == "character_reveal":
                elapsed = pygame.time.get_ticks() - self.game_state.get("reveal_start_time", 0)
                if elapsed > 5000:
                    self.finish_character_reveal()

            pygame.display.flip()

        pygame.quit()
        sys.exit()
    
    ######################################################################
    # ASSET RESCALING
    ######################################################################
    
    def rescale_board(self):
        if self.game_state.get("board") is None:
            return
        
        board_rgb = cv2.cvtColor(self.raw_board, cv2.COLOR_BGR2RGB)
        board_rgb = np.transpose(board_rgb, (1, 0, 2))
        raw_surface = pygame.surfarray.make_surface(board_rgb)
        self.board_surface = pygame.transform.smoothscale(raw_surface, (self.board_width, self.board_height))

    def rescale_cards(self, raw_card_images):
        self.card_images = {}
        for filename, img in raw_card_images.items():
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_rgb = np.transpose(img_rgb, (1, 0, 2))
            surface = pygame.surfarray.make_surface(img_rgb)
            self.card_images[filename] = pygame.transform.smoothscale(
                surface, (self.card_size, self.card_size)
            )
    
    def rescale_dice(self, raw_dice_images):
        self.dice_images = {}
        for filename, img in raw_dice_images.items():
            img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
            img_rgba = np.transpose(img_rgba, (1, 0, 2))
            surface = pygame.surfarray.make_surface(img_rgba[:, :, :3])
            surface = surface.convert_alpha()
            alpha = img_rgba[:, :, 3]
            pygame.surfarray.pixels_alpha(surface)[:] = alpha
            self.dice_images[filename] = pygame.transform.smoothscale(
                surface, (self.card_size, self.card_size)
            )

    def rescale_ui(self, raw_ui_images):
        self.ui_images = {}
        for filename, img in raw_ui_images.items():
            if (filename == "Menu Background.jpg" or filename == "Game Over.jpg"
                or filename == "Game Screen.jpg" or filename == "Settings.jpg"
                or filename == "Statistics.png" or filename == "GH Studios.jpg"
                or filename == "Character Select.png"):
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                img_rgb = np.transpose(img_rgb, (1, 0, 2))
                surface = pygame.surfarray.make_surface(img_rgb)
                self.ui_images[filename] = pygame.transform.smoothscale(
                    surface, (self.width, self.height)
                )

            if filename == "Inventory Bar.jpg":
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                img_rgb = np.transpose(img_rgb, (1, 0, 2))
                surface = pygame.surfarray.make_surface(img_rgb)
                self.ui_images[filename] = pygame.transform.smoothscale(
                    surface, (self.width, self.inventory_height)
                )

            if filename == "Alternate Wrangle.jpg":
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                img_rgb = np.transpose(img_rgb, (1, 0, 2))
                surface = pygame.surfarray.make_surface(img_rgb)
                self.ui_images[filename] = pygame.transform.smoothscale(
                    surface, (self.board_width, self.board_height)
                )

            if filename == "Doubloon.png":
                img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                h, w = img_rgba.shape[:2]
    
                surface = pygame.image.frombuffer(img_rgba.tobytes(), (w, h), "RGBA")
                surface = surface.convert_alpha()  # ensures per-pixel alpha is properly set
    
                self.ui_images[filename] = pygame.transform.smoothscale(
                    surface, (int(self.card_size * 0.75), int(self.card_size * 0.75))
                )

            if filename == "chat.png" or filename == "home.png":
                img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                h, w = img_rgba.shape[:2]
    
                surface = pygame.image.frombuffer(img_rgba.tobytes(), (w, h), "RGBA")
                surface = surface.convert_alpha()  # ensures per-pixel alpha is properly set
    
                surface = pygame.transform.smoothscale(
                    surface, (int(60/1600*self.width), int(60/1600*self.width))
                )       
                surface.set_alpha(128) 
                self.ui_images[filename] = surface     
            
            if filename == "Rum Barrel.png":
                img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                h, w = img_rgba.shape[:2]
    
                surface = pygame.image.frombuffer(img_rgba.tobytes(), (w, h), "RGBA")
                surface = surface.convert_alpha()  # ensures per-pixel alpha is properly set
    
                self.ui_images[filename] = pygame.transform.smoothscale(
                    surface, (int(self.card_size * 0.75), int(self.card_size * 0.75))
                )

            if filename == "Treasure.png":
                img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                h, w = img_rgba.shape[:2]
    
                surface = pygame.image.frombuffer(img_rgba.tobytes(), (w, h), "RGBA")
                surface = surface.convert_alpha()  # ensures per-pixel alpha is properly set
    
                self.ui_images[filename] = pygame.transform.smoothscale(
                    surface, (int(75/1600*self.width), int(53/900*self.height))
                )

            if filename == "Wrangle.png":
                img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                h, w = img_rgba.shape[:2]
    
                surface = pygame.image.frombuffer(img_rgba.tobytes(), (w, h), "RGBA")
                surface = surface.convert_alpha()  # ensures per-pixel alpha is properly set
    
                self.ui_images[filename] = pygame.transform.smoothscale(
                    surface, (int(295/1600*self.width), int(500/900*self.height))
                )

            if filename == "Refresh.png":
                img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                h, w = img_rgba.shape[:2]
    
                surface = pygame.image.frombuffer(img_rgba.tobytes(), (w, h), "RGBA")
                surface = surface.convert_alpha()  # ensures per-pixel alpha is properly set
    
                self.ui_images[filename] = pygame.transform.smoothscale(
                    surface, (40/1600*self.width, 40/1600*self.width)
                )

            if filename.startswith("char"):
                img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                h, w = img_rgba.shape[:2]
    
                surface = pygame.image.frombuffer(img_rgba.tobytes(), (w, h), "RGBA")
                surface = surface.convert_alpha()  # ensures per-pixel alpha is properly set
    
                self.ui_images[filename] = pygame.transform.smoothscale(
                    surface, (self.CHAR_CARD_WIDTH * self.width, self.CHAR_CARD_HEIGHT * self.height)
                )

            
            if self.game_state["phase"] == "menu":
                if filename == "menu_animation":
                    self.ui_images["menu_animation"] = []

                    for img in img:   # img is the list of OpenCV frames
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        img_rgb = np.transpose(img_rgb, (1, 0, 2))
                        surface = pygame.surfarray.make_surface(img_rgb)

                        surface = pygame.transform.smoothscale(
                            surface,
                            (self.width, self.height)
                        )
                        surface = surface.convert()
                        self.ui_images["menu_animation"].append(surface)

                    continue
    
    ######################################################################
    # INPUT HANDLING
    ######################################################################

    # ── Event loop and keyboard ──────────────────────────────────────────────────────
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.show_splash:
                    self.show_splash = False
                    return
                x, y = pygame.mouse.get_pos()
                self.handle_click(x, y)

            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(
                    (event.w, event.h),
                    pygame.RESIZABLE
                )
                self.update_screen_size()  

            elif event.type == pygame.KEYDOWN:
                self.handle_key(event) 

            elif event.type == pygame.MOUSEWHEEL:
                if self.game_state["phase"] == "menu" and ("stats" in self.game_state["menu"]["menu_level"] or self.game_state["menu"]["menu_level"] == "elo"):
                    self.game_state["menu"]["stats_scroll"] -= event.y
                    self.game_state["menu"]["stats_scroll"] = max(0, self.game_state["menu"]["stats_scroll"])

    def update_screen_size(self):
        self.rescale_ui(self.raw_ui_images)
        self.rescale_board()
        self.rescale_cards(self.raw_card_images)
        self.build_buttons()
    
    def handle_key(self, event):

        if event.key == pygame.K_ESCAPE and self.chat_open:
            self.chat_open = False
            self.game_state["selected_field"] = None
            self.chat_notification = False
            return

        field = self.game_state["selected_field"]
        if field is None:
            return

        if field == "chat" and event.key == pygame.K_RETURN:
            message = self.chat_input_text.strip()
            if message:
                self.network.send_chat(message)
                self.chat_input_text = ""
        
        if event.key == pygame.K_BACKSPACE:
            if field == "room_code":
                self.game_state["menu"]["room_code_input"] = self.game_state["menu"]["room_code_input"][:-1]
            elif field == "chat":
                self.chat_input_text = self.chat_input_text[:-1]
            else:
                self.game_state["menu"]["player_names"][field] = self.game_state["menu"]["player_names"][field][:-1]
        
        elif len(event.unicode) == 1 and event.unicode.isprintable():
            if field == "room_code":
                self.game_state["menu"]["room_code_input"] += event.unicode.upper()
            elif field == "chat":
                self.chat_input_text += event.unicode
            else:
                self.game_state["menu"]["player_names"][field] += event.unicode

    # ── Click routing ──────────────────────────────────────────────────────
    def handle_click(self, x, y):
        
        if self.chat_open:
            if self.chat_input_rect.collidepoint(x, y):
                self.game_state["selected_field"] = "chat"
                return
            if self.chat_rect.collidepoint(x, y):
                self.game_state["selected_field"] = None
                return
            return
        
        for button in self.buttons:
            if button.rect.collidepoint(x, y):
                button.action()
                return
            
        for button in self.transparent_buttons:
            if button.rect.collidepoint(x, y):
                button.action()
                return
            
        if self.game_state["phase"] == "menu":
            self.handle_menu_click(x, y)
            return
        
        if self.game_state["phase"] == "character_select":
            for rect, character in getattr(self, "character_rects", []):
                if rect.collidepoint(x, y):
                    my_index = self.my_player_index if self.my_player_index is not None else 0
                    self.game_state["character_selections"][my_index] = character["name"]
                    self.build_buttons()
                    self.broadcast_state()
                    return
                
        if self.game_state["phase"] == "har_supply":
            for rect, card in getattr(self, "har_rects", []):
                if rect.collidepoint(x, y):
                    self.game_state["har_selection"] = card
                    self.build_buttons()
                    self.broadcast_state()
                    return

        # Otherwise check spaces
        if not self.chat_open:
            self.handle_space_click(x, y)
        
        if self.chat_open:
            self.game_state["selected_field"] = None
     
    def handle_menu_click(self, x, y):
        menu = self.game_state["menu"]
        
        # Check clickable room rows first (join_lobby only)
        if menu["menu_level"] == "join_lobby":
            for row_rect, rid in getattr(self, "room_rects", []):
                if row_rect.collidepoint(x, y):
                    menu["room_code_input"] = rid
                    self.game_state["selected_field"] = None
                    return

        if menu["menu_level"] == "active_games":
            for row_rect, rid in getattr(self, "active_game_rects", []):
                if row_rect.collidepoint(x, y):
                    self.rejoin_game(rid)
                    return

        if not self.menu_boxes:
            return
    
        for i, rect in enumerate(self.menu_boxes):
            if rect.collidepoint(x, y):
                if menu["menu_level"] == "join_lobby":
                    fields = [0, "room_code"]   # rect_name=0, rect_code="room_code"
                    self.game_state["selected_field"] = fields[i]
                else:
                    self.game_state["selected_field"] = i
                return
    
        # click outside deselects
        self.game_state["selected_field"] = None

    def handle_space_click(self, x, y):
        if not self.is_my_turn():
            return
        
        scale_x = self.board_width / self.ORIGINAL_BOARD_SIZE
        scale_y = self.board_height / self.ORIGINAL_BOARD_SIZE
        board_y = self.board_y
        
        for space in self.game_state["spaces"]:
            screen_x = self.board_x + int(space["board_x"] * scale_x)
            screen_y = int(space["board_y"] * scale_y) + board_y
            radius = max(4, int(space["hitbox_radius"] * min(scale_x, scale_y)))

            dx = x - screen_x
            dy = y - screen_y

            if (dx*dx + dy*dy) ** 0.5 <= radius:
                self.on_space_clicked(space)
                return
    
    def on_space_clicked(self, space):
        phase = self.game_state["phase"] 

        if phase == "start_turn":
            self.try_move(space)

        elif phase == "dark_alley_start":
            if space["id"] not in self.game_state["alley_lookup"]:
                return False
            self.send_action({"type": "resolve_dark_alley", "exit_id": space["id"]})

        elif phase == "reclaim_1":
            self.send_action({"type": "select_reclaim", "space_id": space["id"]})
        elif phase == "reclaim_2":
            self.send_action({"type": "select_reclaim", "space_id": space["id"]})

        else:
            print("Click ignored in phase:", phase)

    # ── Board space click and move attempt ──────────────────────────────────────────────────────
    def try_move(self, space):
        moves = self.game_state["legal_moves"]

        selected_move = None
        for move in moves: 
            if move["destination"] == space["id"]:
                selected_move = move 
                break
        if selected_move is None:
            return

        self.send_action({"type": "move", "destination_id": space["id"]})
    
    ######################################################################
    # DRAWING — MENU SCREENS
    ######################################################################
    
    # ── Splash Screen ──────────────────────────────────────────────────────
    def draw_splash(self):
        splash_image = self.ui_images["GH Studios.jpg"]  
        self.screen.blit(splash_image, (0, 0))

    # ── Main menu, lobby, room lists ──────────────────────────────────────────────────────
    def draw_menu(self):
        menu_image = self.ui_images["Menu Background.jpg"]
        frames = self.ui_images.get("menu_animation", [])

        if frames:
            self.screen.blit(frames[self.menu_frame], (0, 0))
        else:
            self.screen.blit(menu_image, (0, 0))

        version_text = "Ver 2.20"
        version_label = self.font.render(version_text, True, (255, 255, 255))
        self.screen.blit(version_label, (1450/1600*self.width, 850/900*self.height))

        menu = self.game_state["menu"]
        self.menu_boxes = []

        if menu["menu_level"] == "host_lobby":

            count_text = f"Players: {menu['player_count']}"
            count_label_width, _ = self.menu_font.size(count_text)
            count_label_x = ((((490/1600*self.width) - count_label_width) / 2) + 100/1600*self.width) / 1600 * self.width
            count_label = self.menu_font.render(count_text, True, (0, 0, 0))
            self.screen.blit(count_label, (count_label_x, 275/900*self.height))

            # Your name field (host is always player 0)
            box_width = int(350 / 1600 * self.width)
            base_x = int(((((490/1600*self.width) - box_width) / 2) + 100/1600*self.width) / 1600 * self.width)
            x = base_x
            y = int(420/900 * self.height)
            name_label = self.font.render("Your Name:",True,(0,0,0))
            self.screen.blit(name_label,(x,y))
            
            rect = pygame.Rect(x + 150/1600*self.width, y, box_width, int(40/900*self.height))
            self.menu_boxes = [rect]
            color = (200, 180, 80) if self.game_state["selected_field"] == 0 else (80, 80, 80)
            self.menu_button_surface.fill((0, 0, 0, 0))
            pygame.draw.rect(self.menu_button_surface, color, (0, 0, 225, 40))
            self.screen.blit(self.menu_button_surface, (x + 150/1600*self.width, y))
            
            name = menu["player_names"][0] or "Your Name"
            label = self.font.render(name, True, (0, 0, 0))
            self.screen.blit(label, (rect.x, rect.y + 10))

            random_label = self.font.render("Random Start:", True, (0, 0, 0))
            self.screen.blit(random_label, (x, y + 80))

            character_label = self.font.render("Use Captains:", True, (0, 0, 0))
            self.screen.blit(character_label, (x, y + 165))

        if menu["menu_level"] == "join_lobby":
            # Room code input field
            box_width = int(400 / 1600 * self.width)
            base_x = int(((((490/1600*self.width) - box_width) / 2) + 100/1600*self.width) / 1600 * self.width)

            refresh_icon = self.ui_images["Refresh.png"]
            self.screen.blit(refresh_icon,(base_x + 320/1600*self.width,285/900*self.height))
            refresh_label = self.small_font.render("Refresh", True, (0, 0, 0))
            self.screen.blit(refresh_label, (base_x + 310/1600*self.width,255/900*self.height))

            # Player Name
            name_label = self.font.render("Player Name:", True, (0, 0, 0))
            self.screen.blit(name_label, (base_x, int(255/900*self.height)))
            y_name = int(285/900 * self.height)
            rect_name = pygame.Rect(base_x, y_name, box_width, int(40/900*self.height))
            color_name = (200, 180, 80) if self.game_state["selected_field"] == 0 else (80, 80, 80)
            self.menu_button_surface.fill((0, 0, 0, 0))
            pygame.draw.rect(self.menu_button_surface, color_name, (0, 0, 225, 40))
            self.screen.blit(self.menu_button_surface, (base_x, y_name))
            name = menu["player_names"][0] or "Your Name"
            self.screen.blit(self.font.render(name, True, (0, 0, 0)), (rect_name.x, rect_name.y + 10))

            # Open Rooms
            rooms_title = self.font.render("Open Rooms:", True, (0, 0, 0))
            self.screen.blit(rooms_title, (base_x, int(345/900*self.height)))

            open_rooms = menu.get("open_rooms", [])
            rooms_loading = menu.get("rooms_loading", False)
            row_h = int(44/900 * self.height)
            list_y = int(378/900 * self.height)
            max_visible = 4
            self.room_rects = []  # clickable room rows

            if rooms_loading:
                loading_label = self.font.render("Loading rooms...", True, (100, 100, 100))
                self.screen.blit(loading_label, (base_x, list_y))
            elif not open_rooms:
                empty_label = self.font.render("No open rooms found.", True, (100, 100, 100))
                self.screen.blit(empty_label, (base_x, list_y))
            else:
                for i, room in enumerate(open_rooms[:max_visible]):
                    rid = room.get("room_id", "???")
                    player_names = room.get("players", [])
                    player_count = len(player_names)
                    host_name = player_names[0] if player_names else "?"
                    row_rect = pygame.Rect(base_x, list_y + i * (row_h + 4), box_width, row_h)
                    selected = menu.get("room_code_input", "").upper() == rid.upper()
                    row_color = (200, 180, 80) if selected else (80, 80, 80)
                    pygame.draw.rect(self.screen, row_color, row_rect, border_radius=4)
                    row_text = f"{rid}   Host: {host_name}  ({player_count} waiting)"
                    row_label = self.font.render(row_text, True, (0, 0, 0))
                    self.screen.blit(row_label, (row_rect.x + 10, row_rect.y + (row_h - row_label.get_height()) // 2))
                    self.room_rects.append((row_rect, rid))

            # Manual code entry if necessary
            code_label_y = list_y + max_visible * (row_h + 4) + 10
            self.screen.blit(self.font.render("Or enter code manually:", True, (0, 0, 0)), (base_x, code_label_y))
            y_code = int(code_label_y + 30)
            rect_code = pygame.Rect(base_x, y_code, box_width, int(40/900*self.height))
            color_code = (200, 180, 80) if self.game_state["selected_field"] == "room_code" else (80, 80, 80)
            self.menu_button_surface.fill((0, 0, 0, 0))
            pygame.draw.rect(self.menu_button_surface, color_code, (0, 0, 225, 40))
            self.screen.blit(self.menu_button_surface, (base_x, y_code))
            code_text = menu["room_code_input"] or "Room Code"
            self.screen.blit(self.font.render(code_text, True, (0, 0, 0)), (rect_code.x, rect_code.y + 10))

            self.menu_boxes = [rect_name, rect_code]

            # Error message
            if menu["lobby_error"]:
                error_label = self.font.render(menu["lobby_error"], True, (180, 0, 0))
                self.screen.blit(error_label, (base_x, int(y_code + 50)))
        
        if menu["menu_level"] == "waiting_room":
            box_width = int(350 / 1600 * self.width)
            base_x = int(((((490/1600*self.width) - box_width) / 2) + 100/1600*self.width) / 1600 * self.width)

            if menu["multiplayer_mode"] == "host":
                # Show the room code for host to share
                code_text = f"Room Code: {self.room_id or '...'}"
                code_label = self.menu_font.render(code_text, True, (0, 0, 0))
                self.screen.blit(code_label, (base_x - 5/1600*self.width, int(275/900*self.height)))

                #share_label = self.font.render("Share this code with other players", True, (0, 0, 0))
                #self.screen.blit(share_label, (base_x, int(320/900*self.height)))
            else:
                waiting_label = self.menu_font.render("Waiting for host...", True, (0, 0, 0))
                self.screen.blit(waiting_label, (base_x, int(275/900*self.height)))

            # List connected players
            players_title = self.font.render("Connected Players:", True, (0, 0, 0))
            self.screen.blit(players_title, (base_x, int(370/900*self.height)))
            for i, name in enumerate(menu["lobby_players"]):
                player_label = self.font.render(f"  {i+1}. {name}", True, (0, 0, 0))
                self.screen.blit(player_label, (base_x, int((410 + i * 40)/900*self.height)))

        if menu["menu_level"] == "active_games":
            box_width = int(400 / 1600 * self.width)
            base_x = int(((((490/1600*self.width) - box_width) / 2) + 100/1600*self.width) / 1600 * self.width)

            title = self.menu_font.render("Active Games", True, (0, 0, 0))
            self.screen.blit(title, (base_x, int(245 / 900 * self.height)))

            refresh_icon = self.ui_images["Refresh.png"]
            self.screen.blit(refresh_icon,(base_x + 320/1600*self.width,275/900*self.height))
            refresh_label = self.small_font.render("Refresh", True, (0, 0, 0))
            self.screen.blit(refresh_label, (base_x + 310/1600*self.width,245/900*self.height))

            active_games = menu.get("active_games", [])
            games_loading = menu.get("games_loading", False)
            row_h = int(44 / 900 * self.height)
            list_y = int(350 / 900 * self.height)
            self.active_game_rects = []

            if games_loading:
                self.screen.blit(self.font.render("Loading...", True, (100, 100, 100)), (base_x, list_y))
            elif not active_games:
                self.screen.blit(self.font.render("No active games found.", True, (100, 100, 100)), (base_x, list_y))
            else:
                my_name = self.save_data.settings.get("player_name", "").lower()
                for i, game in enumerate(active_games[:6]):
                    rid = game.get("room_id", "???")
                    players = game.get("players", [])
                    # players is a list of {"name": ..., "connected": ...} dicts
                    player_names = [p["name"] if isinstance(p, dict) else p for p in players]
                    # Highlight games the player is already in
                    in_game = any(n.lower() == my_name for n in player_names)
                    row_rect = pygame.Rect(base_x, list_y + i * (row_h + 4), box_width, row_h)
                    row_color = (200, 180, 80) if in_game else (80, 80, 80)
                    pygame.draw.rect(self.screen, row_color, row_rect, border_radius=4)
                    player_str = ", ".join(player_names)
                    row_text = f"{rid}   {player_str}"
                    row_label = self.font.render(row_text, True, (0, 0, 0))
                    self.screen.blit(row_label, (row_rect.x + 10, row_rect.y + (row_h - row_label.get_height()) // 2))
                    self.active_game_rects.append((row_rect, rid))

        if menu["menu_level"] == "stats_1" or menu["menu_level"] == "stats_2" or menu["menu_level"] == "elo":
            self.draw_stats()

    # ── Settings menu ──────────────────────────────────────────────────────
    def draw_settings_menu(self):
        menu_image = self.ui_images["Settings.jpg"]
        self.screen.blit(menu_image,(0, 0))
    
        settings = self.save_data.settings
        
        settings_panel_x = 120/1600*self.width
        settings_panel_y = 280/900*self.height
        settings_panel_width = 730/1600*self.width
        menu_buffer = 80/900*self.height

        self.buttons = []
        self.transparent_buttons = []
        # ── Title ──────────────────────────────────────────────
        title_text = "Settings"
        title_label_width, _ = self.menu_font.size(title_text)
        title_label_x = (settings_panel_width - title_label_width) / 2 + settings_panel_x
        title_label = self.menu_font.render(title_text, True, (0, 0, 0))
        self.screen.blit(title_label, (title_label_x, settings_panel_y))

        # ── Resolution ─────────────────────────────────────────
        res_label = self.font.render("Resolution:", True, (0, 0, 0))
        self.screen.blit(res_label, (settings_panel_x, settings_panel_y + menu_buffer))

        resolutions = [[1280, 720], [1600, 900], [1920, 1080]]
        for i, res in enumerate(resolutions):
            label = f"{res[0]}x{res[1]}"
            color = (200, 180, 80) if settings["resolution"] == res else (80, 80, 80)
            self.buttons.append(Button((250 + i * 200 )/1600*self.width, settings_panel_y + menu_buffer, 200/1600*self.width, 50, label, lambda r=res: self.set_resolution(r), color=color))

        # ── Fullscreen ─────────────────────────────────────────
        fs_label = self.font.render("Fullscreen:", True, (0, 0, 0))
        self.screen.blit(fs_label, (settings_panel_x, settings_panel_y + 2 * menu_buffer))
    
        fs_value = "On" if settings["fullscreen"] else "Off"
        fs_color = (200, 180, 80) if settings["fullscreen"] else (80, 80, 80)
        self.buttons.append(Button(450/1600*self.width, settings_panel_y + 2* menu_buffer, 150/1600*self.width, 50, fs_value, self.toggle_fullscreen, color=fs_color))

        # ── Wrangle View ───────────────────────────────────────
        wrangle_label = self.font.render("Wrangle View:", True, (0, 0, 0))
        self.screen.blit(wrangle_label, (settings_panel_x, settings_panel_y + 3 * menu_buffer))

        for i, mode in enumerate(["Classic", "Cinematic"]):
            color = (200, 180, 80) if settings.get("wrangle_view") == mode else (80, 80, 80)
            # Draw button using color and mode.capitalize() as label
            self.buttons.append(Button((317 + i * 267)/1600*self.width, settings_panel_y + 3 * menu_buffer, 200/1600*self.width, 50, mode, lambda m=mode: self.set_wrangle_view(m), color=color))
       
        
        self.transparent_buttons.append(Button((settings_panel_width-300)/2 + settings_panel_x, 725/900*self.height, 300, 100, "Main Menu", self.return_menu))

        return

    # ── Statistics screens ──────────────────────────────────────────────────────
    def draw_stats(self):
        stats_screen = self.ui_images["Statistics.png"]
        self.screen.blit(stats_screen,(0,0))
        
        
        game_stats = self.stats["games"]
        player_stats = self.stats["players"]
        players = [name for name, data in player_stats.items() if data["games_played"] >= 3]
        max_visible = 5  
        scroll = self.game_state["menu"].get("stats_scroll", 0)
        scroll = min(scroll, max(0, len(players) - max_visible))
        self.game_state["menu"]["stats_scroll"] = scroll  
        
        averages = {} 

        for player_name in players:
            player_avgs = self.save_data.get_averages(player_name)
            player_avgs["total"] = round(sum(player_avgs.values(), 1))
            averages[player_name] = player_avgs

        sorted_players = sorted(
            players,
            key=lambda name: averages[name]["total"],
            reverse=True
        )

        if self.stats == {}:
            stat_text = "No game stats to display."
            stat_label_width, _ = self.menu_font.size(stat_text)
            stat_label_x = ((908-stat_label_width) / 2 + 340) /1600*self.width
            stat_label = self.menu_font.render(stat_text, True, (0, 0, 0))
            self.screen.blit(stat_label, (stat_label_x, 440/900*self.height))

        if self.game_state["menu"]["menu_level"] == "stats_1":
            col_labels = ["Wrangle", "Maps", "Pubs", "Supplies", "Rendezvous", "Guards", "Treasure", "Scorpions", "Total"]

            table_x = 325/1600*self.width
            table_y = 430/900*self.height 
            col_width = 80/1600*self.width 
            row_height = 60

            for j, label in enumerate(col_labels): 
                x = table_x + (j + 1) * col_width + col_width // 2
                self.draw_angled_label(self.screen, self.font, label, (0, 0, 0), x, table_y, angle=40)

            for row, player_name in enumerate(sorted_players[scroll:scroll + max_visible]):
                player_avgs = averages[player_name]

                name_label = self.menu_font.render(player_name, True, (0, 0, 0))
                self.screen.blit(name_label, (table_x - 10, table_y + (row) * row_height))

                for col, label in enumerate(col_labels):
                    value = round(player_avgs.get(label.lower(), 0))
                    text = self.menu_font.render(str(value), True, (0, 0, 0))

                    x = table_x + (col + 1) * col_width + col_width // 2
                    y = table_y + (row) * row_height

                    self.screen.blit(text, (x, y))

        if self.game_state["menu"]["menu_level"] == "stats_2":
            table_x = 460/1600*self.width
            table_y = 450/900*self.height
            row_height = 50

            if player_stats:
                last_game = game_stats[-1] if game_stats else None
                if last_game:
                    champion = last_game["winner"]
                    streak = player_stats[champion]["current_streak"]
                    champion_text = f"Reigning Champion: {champion} ({streak} game streak)"
                    champion_width, _ = self.menu_font.size(champion_text)
                    champion_label = self.menu_font.render(champion_text, True, (0, 0, 0))
                    self.screen.blit(champion_label, ((1600-champion_width)/2/1600*self.width, 360/900*self.height))

                # Longest win streak (all time)
                #longest_name = max(player_stats.keys(), key=lambda n: player_stats[n]["best_streak"])
                #longest = player_stats[longest_name]["best_streak"]
                #streak_text = f"Longest Win Streak: {longest_name} ({longest} games)"
                #streak_width, _ = self.font.size(streak_text)
                #streak_label = self.font.render(streak_text, True, (0, 0, 0))
                #self.screen.blit(streak_label, ((1600-streak_width)/2/1600*self.width, 420/900*self.height))

            # Table headers
            col_labels = ["Games", "Wins", "Win Rate", "Best Streak"]
            col_width = 160/1600*self.width
            for j, label in enumerate(col_labels):
                x = table_x + (j + 1) * col_width
                width, _ = self.font.size(label)
                header = self.font.render(label, True, (0, 0, 0))
                self.screen.blit(header, (x - width / 2, table_y))

            # Player rows
            sorted_by_wins = sorted(
                [n for n in players if player_stats[n]["games_played"] >= 3],
                key=lambda n: player_stats[n]["wins"],
                reverse=True
            )
            for row, player_name in enumerate(sorted_by_wins[scroll:scroll + max_visible]):
                s = player_stats[player_name]
                games = s["games_played"]
                wins = s["wins"]
                streak = s["best_streak"]
                win_pct = round((wins / games * 100)) if games > 0 else 0

                y = table_y + (row + 1) * row_height
                name_label = self.menu_font.render(player_name, True, (0, 0, 0))
                self.screen.blit(name_label, (table_x - 30, y - 12))

                for col, value in enumerate([games, wins, f"{win_pct}", streak]):
                    text = self.font.render(str(value), True, (0, 0, 0))
                    width, _ = self.font.size(str(value))
                    x = table_x + (col + 1) * col_width
                    self.screen.blit(text, (x - width / 2, y))

        if self.game_state["menu"]["menu_level"] == "elo":
            name_x = 450/1600 * self.width
            elo_x = 750/1600*self.width
            games_x = 1050/1600*self.width
            title_y = 390/900*self.height
            start_y = 450/900*self.height
            y_buffer = 50/900*self.height
            
            leaderboard = [p for p in self.save_data.get_elo_leaderboard() if p["games_played"] >= 3]

            ######   Headers #############
            name_label_width, _ = self.menu_font.size("Player")
            name_label_x = name_x - name_label_width / 4
            name_label = self.menu_font.render("Players", True, (0, 0, 0))
            self.screen.blit(name_label, (name_label_x, title_y))
            elo_label = self.menu_font.render("ELO", True, (0, 0, 0))
            self.screen.blit(elo_label, (elo_x, title_y))
            games_label_width, _ = self.menu_font.size("Games Played")
            games_label_x = games_x - games_label_width / 2
            games_label = self.menu_font.render("Games Played", True, (0, 0, 0))
            self.screen.blit(games_label, (games_label_x, title_y))

            for i, player in enumerate(leaderboard[scroll:scroll + max_visible]):
                y = start_y + i * y_buffer 
                
                name_text = self.menu_font.render(player["name"], True, (0, 0, 0))
                elo_text = self.menu_font.render(str(player["elo"]), True, (0, 0, 0))
                games_text = self.menu_font.render(str(player["games_played"]), True, (0, 0, 0))

                self.screen.blit(name_text, (name_x,y))
                self.screen.blit(elo_text, (elo_x,y))
                self.screen.blit(games_text, (games_x,y))

        total = len(players)
        if total > 2:  #max_visible
            shown_end = min(scroll + max_visible, total)
            scroll_text = f"{scroll + 1}-{shown_end} of {total}"
            scroll_width, _ = self.font.size(scroll_text)
            scroll_label = self.font.render(scroll_text, True, (100, 100, 100))
            self.screen.blit(scroll_label, ((1600 - scroll_width) / 2 / 1600 * self.width, 755/900*(self.height)))

    # ── Character Selection ──────────────────────────────────────────────────────
    def draw_character_select(self):
        character_screen = self.ui_images["Character Select.png"]
        self.screen.blit(character_screen, (0, 0))

        my_index = self.my_player_index if self.my_player_index is not None else 0
        hands = self.game_state.get("character_hands", [])
        selections = self.game_state.get("character_selections", [])
        confirmed = self.game_state.get("character_confirmed", [])

        if not hands or my_index >= len(hands):
            return

        my_hand = hands[my_index]
        my_selection = selections[my_index]
        already_confirmed = confirmed[my_index] if my_index < len(confirmed) else False

        # Title
        title = self.menu_font.render("Choose Your Captain", True, (255, 255, 255))
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, int(60/900*self.height)))

        # Waiting status for other players
        if already_confirmed:
            confirmed_count = sum(1 for c in confirmed if c)
            total = len(self.game_state["players"])
            status_text = f"{confirmed_count}/{total} captains chosen"
            status = self.font.render(status_text, True, (255, 255, 255))
            self.screen.blit(status, (self.width // 2 - status.get_width() // 2, int(140/900*self.height)))

            # If already confirmed, show waiting message over cards
            if my_selection is not None and confirmed_count < total:
                waiting = self.menu_font.render("Waiting for other players...", True, (255, 255, 255))
                self.screen.blit(waiting, (self.width // 2 - waiting.get_width() // 2, int(700/900*self.height)))

        # Draw the two character cards
        card_w = int(self.CHAR_CARD_WIDTH * self.width)
        card_h = int(self.CHAR_CARD_HEIGHT * self.height)
        gap = int(100/1600 * self.width)
        total_w = card_w * 2 + gap
        start_x = (self.width - total_w) // 2
        card_y = int(250/900 * self.height)

        self.character_rects = []

        for i, character in enumerate(my_hand):
            x = start_x + i * (card_w + gap)
            rect = pygame.Rect(x, card_y, card_w, card_h)
            
            # Only allow clicks if not confirmed 
            if not already_confirmed:
                self.character_rects.append((rect, character))

            # Highlight selected card
            selected = my_selection == character["name"]
            border_color = (200, 180, 80) if selected else (80, 80, 80)
            border_width = 5 if selected else 2

            # Dim cards if confirmed
            if already_confirmed:
                dim = pygame.Surface((card_w, card_h))
                dim.set_alpha(120)
                dim.fill((0, 0, 0))

            pygame.draw.rect(self.screen, border_color, rect, border_radius=8)
            pygame.draw.rect(self.screen, border_color, rect, border_width, border_radius=8)

            # Character image
            image_key = character["image"]
            if image_key in self.ui_images:
                img = pygame.transform.smoothscale(self.ui_images[image_key], (card_w - 10, card_h - 10))
                self.screen.blit(img, (x + 5, card_y + 5))

    def draw_character_reveal(self): 
        character_screen = self.ui_images["Character Select.png"]
        self.screen.blit(character_screen, (0, 0))

        players = self.game_state.get("players", [])
        n = len(players)
        if n == 0:
            return
        
        title = self.menu_font.render("Setting Sail!", True, (255, 255, 255))
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, int(40/900*self.height)))

        card_w = int(self.CHAR_CARD_WIDTH * self.width)
        card_h = int(self.CHAR_CARD_HEIGHT * self.height)
        total_w = n * card_w
        spacing = (self.width - total_w) // (n + 1)
        card_y = int(250/900 * self.height)

        for i, player in enumerate(players):
            x = spacing + i * (card_w + spacing)

            name_label = self.menu_font.render(player["name"], True, (255, 255, 255))
            self.screen.blit(name_label, (x + card_w // 2 - name_label.get_width() // 2, card_y - int(50/900*self.height)))

            character = player.get("character")
            if character:
                char_image_key = character.get("image")
                if char_image_key and char_image_key in self.ui_images:
                    img = pygame.transform.smoothscale(self.ui_images[char_image_key], (card_w, card_h))
                    self.screen.blit(img, (x, card_y))

    ######################################################################
    # DRAWING — MAIN DISPATCHER
    ######################################################################

    def draw(self):  ############ Main draw function that calls all other draws ###########
        
        if self.show_splash:
            self.draw_splash()
            return
        
        if self.game_state["phase"] == "menu" and self.game_state["menu"]["menu_level"] == "stats_1":
            self.draw_stats()

            self.build_buttons()
            for button in self.buttons:
                button.draw(self.screen, self.menu_font)
            for button in self.transparent_buttons:
                button.draw_transparent(self.screen, self.menu_font)
            
            return

        if self.game_state["phase"] == "menu" and self.game_state["menu"]["menu_level"] != "settings_menu":
            self.draw_menu()
            
            self.build_buttons()
            for button in self.buttons:
                button.draw(self.screen, self.menu_font)
            for button in self.transparent_buttons:
                button.draw_transparent(self.screen, self.menu_font)
            
            return
        
        if self.game_state["phase"] == "menu" and self.game_state["menu"]["menu_level"] == "settings_menu":
            self.draw_settings_menu()

            for button in self.buttons:
                button.draw(self.screen, self.menu_font)
            for button in self.transparent_buttons:
                button.draw_transparent(self.screen, self.menu_font)
            
            return
        
        if self.game_state.get("reconnecting"):
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            msg = self.menu_font.render("Connection lost - reconnecting...", True, (255, 255, 255))
            self.screen.blit(msg, (self.width // 2 - msg.get_width() // 2, self.height // 2))
            return
        
        if self.game_state["phase"] == "game_over":
            self.draw_end_scores()
            self.build_buttons()
            for button in self.buttons:
                button.draw(self.screen, self.menu_font)
            for button in self.transparent_buttons:
                button.draw_transparent(self.screen, self.menu_font)
            return
        
        if self.game_state["phase"] == "character_select":
            self.draw_character_select()
            self.build_buttons()
            for button in self.buttons:
                button.draw(self.screen, self.menu_font)
            for button in self.transparent_buttons:
                button.draw_transparent(self.screen, self.menu_font)
            return
        
        if self.game_state["phase"] == "character_reveal":
            self.draw_character_reveal()
            return

        game_screen = self.ui_images["Game Screen.jpg"]
        self.screen.blit(game_screen,(0,0))

        chat_image = self.ui_images["chat.png"]
        home_image = self.ui_images["home.png"]
        self.screen.blit(home_image,(140/1600*self.width,15/900*self.height))
        self.screen.blit(chat_image,(220/1600*self.width,15/900*self.height))

        if not self.chat_open and self.chat_notification:
            pygame.draw.circle(self.screen, (0,255,0), (265/1600*self.width, 30/900*self.height), 5)

        wrangle = self.game_state.get("wrangle", {})
        if wrangle.get("active"):
            self.draw_wrangle_setup()

        else:
            if self.board_surface is not None and self.game_state.get("space_lookup"):
                self.draw_board()
        
        ################## Panels ####################
        self.draw_tableau()    # right
        self.draw_info_panel() # left
        self.draw_character_card_overlay() # Captain card
        
        ################ Images ######################
        self.draw_images()
    
        ################## Buttons ####################
        self.build_buttons()
        for button in self.buttons:
            button.draw(self.screen, self.font)
        for button in self.transparent_buttons:
            button.draw_transparent(self.screen, self.font)
                
        if not self.game_state["players"]:
            return
        
        ############### Messages #####################
        self.draw_messages()
        
        ######## Inventory and Chat last so they opens over everything else ######
        if self.inventory_open:
            self.draw_inventory_panel() 
            self.draw_inventory_info()
        if self.chat_open:
            self.draw_chat()

    def draw_board(self):
        self.screen.blit(self.board_surface, (self.board_x, 98/750*self.height))

        ############ Scalable Space Locations ##########
        scale_x = self.board_width / self.ORIGINAL_BOARD_SIZE
        scale_y = self.board_height / self.ORIGINAL_BOARD_SIZE
        board_y = self.board_y
        
        ################## Pirates ####################
        for occupied_path in self.game_state["occupied_paths"]:
            player = next(p for p in self.game_state["players"] if p["id"] == occupied_path["player_id"])
            color = player["color"]

            for space_id in occupied_path["path"]:
                space = self.game_state["space_lookup"][space_id]
                screen_x = self.board_x + int(space["board_x"] * scale_x)
                screen_y = int(space["board_y"] * scale_y) + board_y
                radius = max(4, int(8 * min(scale_x, scale_y)))
                pygame.draw.circle(self.screen, color, (screen_x, screen_y), radius)

        pending = self.game_state.get("pending_move")
        dark_alley_1 = self.game_state.get("dark_alley_1")
        dark_alley_2 = self.game_state.get("dark_alley_2")

        if pending or dark_alley_1 or dark_alley_2:
            player = self.game_state["players"][self.game_state["active_player"]]
            color = player["color"]
            if pending:
                for space_id in pending["path"]:
                    space = self.game_state["space_lookup"][space_id]
                    screen_x = self.board_x + int(space["board_x"] * scale_x)
                    screen_y = int(space["board_y"] * scale_y) + board_y
                    radius = max(4, int(8 * min(scale_x, scale_y)))
                    pygame.draw.circle(self.screen, color, (screen_x, screen_y), radius, 2)
            if dark_alley_1:
                for space_id in dark_alley_1["path"]:
                    space = self.game_state["space_lookup"][space_id]
                    screen_x = self.board_x + int(space["board_x"] * scale_x)
                    screen_y = int(space["board_y"] * scale_y) + board_y
                    radius = max(4, int(8 * min(scale_x, scale_y)))
                    pygame.draw.circle(self.screen, color, (screen_x, screen_y), radius, 2)
            if dark_alley_2:
                for space_id in dark_alley_2["path"]:
                    space = self.game_state["space_lookup"][space_id]
                    screen_x = self.board_x + int(space["board_x"] * scale_x)
                    screen_y = int(space["board_y"] * scale_y) + board_y
                    radius = max(4, int(8 * min(scale_x, scale_y)))
                    pygame.draw.circle(self.screen, color, (screen_x, screen_y), radius, 2)
            # Draw preview captain position
            if pending or dark_alley_2:
                if pending:
                    dest_space = self.game_state["space_lookup"][pending["destination_id"]]
                else:
                    dest_space = self.game_state["space_lookup"][dark_alley_2["final_space"]]
                screen_x = self.board_x + int(dest_space["board_x"] * scale_x)
                screen_y = int(dest_space["board_y"] * scale_y) + board_y
                radius = max(8, int(15 * min(scale_x, scale_y)))
                pygame.draw.circle(self.screen, (255, 0, 0), (screen_x, screen_y), radius, 3)

        ################## Captain ####################
        captain_space = self.game_state["captain_space"]
        space_id = self.game_state["space_lookup"][captain_space]
        screen_x = self.board_x + int(space_id["board_x"] * scale_x)
        screen_y = int(space_id["board_y"] * scale_y) + board_y
        radius = max(8, int(15 * min(scale_x, scale_y)))
        pygame.draw.circle(self.screen,(255,0,0),(screen_x, screen_y), radius)

    ######################################################################
    # DRAWING — IN-GAME PANELS
    ######################################################################

    # ── Chat window ──────────────────────────────────────────────────────
    def draw_chat(self):
        if not self.chat_open:
            return
        
        width = int(800 / 1600 * self.width)
        base_height = int(200 / 900 * self.height)
        height = base_height + 30 * min(len(self.chat_messages),10)
        x = (self.width - width)/2
        y = (self.height - height)/2

        self.chat_rect = pygame.Rect(x, y, width, height)
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((25, 25, 25, 220))
        self.screen.blit(panel, (x, y))
        pygame.draw.rect(self.screen, (180, 180, 180), self.chat_rect, 2)

        # Title
        title = self.font.render("Chat", True, (255,255,255))
        self.screen.blit(title, (x + 10, y + 8))

        # Input box
        input_height = 34
        input_rect = pygame.Rect(x + 8, y + height - input_height - 8, width - 16, input_height)
        self.chat_input_rect = input_rect
        pygame.draw.rect(self.screen, (55,55,55), input_rect)
        border = (255,255,255) if self.game_state["selected_field"] == "chat" else (120,120,120)
        pygame.draw.rect(self.screen, border, input_rect, 2)
        text = self.font.render(self.chat_input_text, True, (255,255,255))
        self.screen.blit(text, (input_rect.x + 6, input_rect.y + 2))

        # Messages 
        message_y = input_rect.y - 32
        for message in reversed(self.chat_messages[-10:]):
            message_y = self.draw_wrapped_text_up(self.font, f'{message["player"]}: {message["text"]}', x + 8, message_y, width - 16, (255,255,255))
            message_y -= 4
    
    def toggle_chat(self):
        self.chat_open = not self.chat_open
        self.game_state["selected_field"] = "chat"
        self.chat_read_messages = len(self.chat_messages)
        self.chat_notification = False
        self.rescale_board()
        self.rescale_ui(self.raw_ui_images) 
        self.build_buttons()

    # ── Info panel (left) and player status ──────────────────────────────────────────────────────
    def draw_info_panel(self):
        if not self.game_state["players"]:
            return
        
        panel_x = int(self.left_panel_x + 15/1600*self.width)
        panel_width = self.left_panel_width

        # --- Round and Room info ---
        round_y = int(20/750 * self.height)
        round = self.game_state["round"]
        round_text = f"Round {round}"
        round_label_width, _ = self.menu_font.size(round_text)
        round_label_x = int((self.board_x + (self.board_width - round_label_width) // 2))
        round_label = self.menu_font.render(round_text, True, (255, 255, 255))
        self.screen.blit(round_label, (round_label_x, round_y))

        room_code = self.room_id or self.game_state["menu"]["room_code_input"].strip().upper()
        room_text = f"Room: {room_code}"
        room_x = round_label_x + round_label_width + 100/1600*self.width
        room_label = self.font.render(room_text, True, (255, 255, 255))
        self.screen.blit(room_label, (room_x, self.board_y - 75/900*self.height))

        # --- Action Log ---
        action_y = int(90/750 *self.height)
        log_text = "Action Log"
        log_label_width, _ = self.font.size(log_text)
        log_label_x = int((self.left_panel_width - log_label_width) / 2) + self.left_panel_x
        log_label = self.font.render(log_text, True, (0, 0, 0))
        self.screen.blit(log_label, (log_label_x, action_y))

        # Show the last 10 actions, most recent first
        log_y = action_y + int(30/750*self.board_height)
        recent_actions = self.game_state["action_log"][-10:]
        for entry in reversed(recent_actions):
            log_y = self.draw_wrapped_text(self.small_font, entry, panel_x + 5, log_y, panel_width - 10, (0, 0, 0))
            log_y += 4  # spacing between entries

        self.draw_player_status()

    def draw_player_status(self):
        if not self.game_state["players"]:
            return
        
        players = self.game_state["players"]
        active_index = self.game_state["active_player"]
        starting_index = self.game_state["starting_player"]

        start_x = 85 / 1600 * self.width
        names_y = 620 / 900 * self.height
        row_height = 45 / 900 * self.height

        arrow_x = start_x 
        name_x = start_x + 35/1600 * self.width
        pirate_x = name_x + 120/1600 * self.width
        barrel_x = 300/1600 * self.width
        barrel_image = self.ui_images["Rum Barrel.png"]
        self.screen.blit(barrel_image,(barrel_x - 20/1600*self.width, 552 / 900 * self.height))

        for i, player in enumerate(players):
            total_pirates = 0
            y = names_y + i * row_height
            color = (0,0,0)

            # Draw arrow for active player
            if i == starting_index:
                arrow_label = self.font.render("$", True, (139, 0, 0))
                self.screen.blit(arrow_label, (arrow_x, y))

            # Draw player name

            if i == active_index:
                color = (255,255,255)
            
            name_text= player["name"]
            if player["board_position"] > 0:
                name_text = name_text + " #"
            
            name_label = self.font.render(name_text, True, color)
            self.screen.blit(name_label, (name_x, y))

            # Draw remaining pirates
            total_pirates = (15 - player["pirate_reserve"])
            pirate_label = self.small_font.render(str(f"{player["pirates"]}/{total_pirates}"),True,player["color"])
            self.screen.blit(pirate_label, (pirate_x, y+5))

            barrels = player["barrels"]
            barrel_label = self.small_font.render(str(barrels),True,(0,0,0))
            self.screen.blit(barrel_label, (barrel_x, y + 5))

        
        own_player = self.get_my_player()
        if own_player is None:
            return
        coins = own_player["coins"] 
        coin_label = self.font.render(str(coins),True,(0,0,0)) 
        coin_label_width, _ = self.font.size(str(coins))
        coin_image = self.ui_images["Doubloon.png"]
        coin_width = self.card_size*.75
        coin_image_x = int(((258 - coin_width) / 2 + 80)/1600*self.width)
        self.screen.blit(coin_image,(coin_image_x, 552 / 900 * self.height))
        self.screen.blit(coin_label, ((coin_width - coin_label_width) // 2 + coin_image_x, 557 / 900 * self.height))

    # ── Tableau (right panel) and messages ──────────────────────────────────────────────────────
    def draw_tableau(self):  ############### Draw tableau menu on the right of the board
        if not self.game_state["tableau"]:
            return
        
        tableau = self.game_state["tableau"]
        card_width = self.card_size
        card_height = self.card_size
        padding = int((self.right_panel_width - card_width * 4) // 5)
        x_start = self.right_panel_x + padding
        y = 45 / 750 * self.height 

        # --- Pubs ---
        # Center text in the middle of the panel
        pub_text = "Pubs"
        pub_label_width, _ = self.font.size(pub_text)
        pub_label_x = self.right_panel_x + (self.right_panel_width - pub_label_width) // 2
        pub_label = self.font.render(pub_text, True, (0, 0, 0))
        self.screen.blit(pub_label, (pub_label_x, y))

        # Adjust card size if 5 pub tiles in tableau
        pub_card_size = card_width
        pub_padding = padding
        pub_x_start = x_start
        if len(tableau["pubs"]) == 5:
            pub_card_size = int(0.8 * card_width)
            pub_padding = int((self.right_panel_width - pub_card_size * 5) // 6)
            pub_x_start = self.right_panel_x + pub_padding

        y += 35 / 750 * self.height
        # Draw cards in 1 row
        for i, card in enumerate(tableau["pubs"]):
            x = pub_x_start + i * (pub_card_size + pub_padding)

            image_key = card.get("image_file")
            if image_key and image_key in self.card_images:
                img = pygame.transform.smoothscale(self.card_images[image_key], (pub_card_size, pub_card_size))
                self.screen.blit(img, (x, y))
            else:
                pygame.draw.rect(self.screen, (80, 80, 80), (x, y, pub_card_size, pub_card_size))

        y += 77 / 750 * self.height
        # --- Maps ---
        # Center text in the middle of the panel
        map_text = "Maps"
        map_label_width, _ = self.font.size(map_text)
        map_label_x = self.right_panel_x + (self.right_panel_width - map_label_width) // 2
        map_label = self.font.render(map_text, True, (0, 0, 0))
        self.screen.blit(map_label, (map_label_x, y))

        y += 35 / 750 * self.height
        for i, card in enumerate(tableau["maps"]):
            x = x_start + i * (card_width + padding)

            image_key = card.get("image_file")
            if image_key and image_key in self.card_images:
                img = pygame.transform.smoothscale(self.card_images[image_key], (card_width, card_height))
                self.screen.blit(img, (x, y))

        y += 77 / 750 * self.height
        # Treasure
        treasure_text = "Treasure"
        treasure_label_width, _ = self.font.size(treasure_text)
        treasure_label_x = self.right_panel_x + (self.right_panel_width - treasure_label_width) // 2
        treasure_label = self.font.render(treasure_text, True, (0, 0, 0))
        self.screen.blit(treasure_label, (treasure_label_x, y))

        card = tableau["treasure"]
        image_key = card.get("image_file") 
        treasure_x = self.right_panel_x + ( self.right_panel_width -  (2 * card_width + 2 * padding)) / 2
        y += 35 / 750 * self.height
        img = pygame.transform.smoothscale(self.card_images[image_key], (card_width, card_height))
        self.screen.blit(img, (treasure_x, y))

        card = tableau["scorpion"]
        image_key = card.get("image_file") 
        scorpion_x = treasure_x + card_width + 2* padding
        img = pygame.transform.smoothscale(self.card_images[image_key], (card_width, card_height))
        self.screen.blit(img, (scorpion_x, y))

        y += 77 / 750 * self.height
        # Wrangle
        wrangle_text = "Wrangle"
        wrangle_label_width, _ = self.font.size(wrangle_text)
        wrangle_label_x = self.right_panel_x + (self.right_panel_width - wrangle_label_width) // 2
        wrangle_label = self.font.render(wrangle_text, True, (0, 0, 0))
        self.screen.blit(wrangle_label, (wrangle_label_x, y))

        card = tableau["wrangle_bunk"]
        image_key = card.get("image_file") 
        bunk_x = self.right_panel_x + ( self.right_panel_width -  (3 * card_width + 4 * padding)) / 2
        y += 35 / 750 * self.board_height
        img = pygame.transform.smoothscale(self.card_images[image_key], (card_width, card_height))
        self.screen.blit(img, (bunk_x, y))

        card = tableau["wrangle_hammock"]
        image_key = card.get("image_file") 
        hammock_x = bunk_x + card_width + 2* padding
        img = pygame.transform.smoothscale(self.card_images[image_key], (card_width, card_height))
        self.screen.blit(img, (hammock_x, y))

        card = tableau["wrangle_bedroll"]
        image_key = card.get("image_file") 
        bedroll_x = hammock_x + card_width + 2* padding
        img = pygame.transform.smoothscale(self.card_images[image_key], (card_width, card_height))
        self.screen.blit(img, (bedroll_x, y))

    def draw_messages(self):
        message_y = 640 / 750 * self.board_height
        
        pub = self.game_state["pub"]
        player_index = (self.game_state["active_player"] + pub["invite_index"]) % len(self.game_state["players"])
        player_data = self.game_state["players"][player_index]
        roller_index = self.game_state["next_roller"]
        player = self.game_state["players"][self.game_state["active_player"]]
        
        if self.game_state["phase"] == "pub_invite":
            pub_label = f"{player_data['name']}, would you like to join {player["name"]} at the pub?"
            self.draw_wrapped_text(self.font, pub_label, self.right_panel_x + 5, message_y, self.right_panel_width - 10, (0, 0, 0))

        if self.game_state["phase"] == "dark_alley_start":
            message = self.font.render("Select an exit location.", True, (0,0,0))
            self.screen.blit(message, (self.right_panel_x + (2 * self.CARD_BUFFER_RATIO * self.width), message_y))

        if self.game_state["phase"] == "start_turn" and self.is_my_turn():
            message = self.font.render("Move the captain.", True, (0,0,0))
            self.screen.blit(message, (self.right_panel_x + (2 * self.CARD_BUFFER_RATIO * self.width), message_y))

        if self.game_state["phase"] == "confirm_boarding" and self.is_my_turn():
            message = "Are you sure you want to go on board?"
            self.draw_wrapped_text(self.font, message, self.right_panel_x + 5, message_y, self.right_panel_width - 10, (0, 0, 0))

        if self.game_state["phase"] == "reclaim_1":
            message = self.font.render("Select a starting point.", True, (0,0,0))
            self.screen.blit(message, (self.right_panel_x + (2 * self.CARD_BUFFER_RATIO * self.width), message_y))

        if self.game_state["phase"] == "reclaim_2":
            message = self.font.render("Select an ending point.", True, (0,0,0))
            self.screen.blit(message, (self.right_panel_x + (2 * self.CARD_BUFFER_RATIO * self.width), message_y))

        if self.game_state["phase"] == "reclaim_fail":
            message = self.font.render("Invalid Selection", True, (0,0,0))
            self.screen.blit(message, (self.right_panel_x + (2 * self.CARD_BUFFER_RATIO * self.width), message_y))

        if self.network and not self.is_my_turn():
            active = self.game_state["players"][self.game_state["active_player"]]
            waiting_text = self.font.render(f"Waiting for {active['name']}...", True, (255, 255, 255))
            self.screen.blit(waiting_text, (self.board_x + 10, self.board_y - 75/900*self.height))

        scorpion_contest = self.game_state["scorpion_contest"]
        if scorpion_contest["contest_active"] == True:
            total = scorpion_contest["total"]
            target = scorpion_contest["target"]
            total_text = f"Total: {total}/{target}"
            total_label_width, _ = self.menu_font.size(total_text)
            total_label_x = self.board_x + (self.board_width - total_label_width) / 2
            total_label = self.menu_font.render(total_text, True, (255, 255, 255))
            self.screen.blit(total_label, (total_label_x, 600/900*self.board_height))

            roller_name = self.game_state["players"][roller_index]["name"]
            roller_text = f"Rolling: {roller_name}"
            roller_label_x = self.board_x + (self.board_width - total_label_width) / 2
            roller_label = self.menu_font.render(roller_text, True, (255, 255, 255))
            self.screen.blit(roller_label, (roller_label_x, 650/900*self.board_height))

        if self.game_state["pub"]["pub_active"] == True:
            roller_name = self.game_state["players"][roller_index]["name"]
            roller_text = f"Rolling: {roller_name}"
            roller_label_width, _ = self.menu_font.size(roller_text)
            roller_label_x = self.board_x + (self.board_width - roller_label_width) / 2
            roller_label = self.menu_font.render(roller_text, True, (255, 255, 255))
            self.screen.blit(roller_label, (roller_label_x, 600/900*self.board_height))

        if self.game_state["fergus_guard_roll"] is not None:
            player_id = self.game_state["fergus_guard_roll"]["fergus_index"]
            name = self.game_state["players"][player_id]["name"]
            name_text = f"{name} showed up to fight the guard!"
            self.draw_wrapped_text(self.font, name_text, self.right_panel_x + 5, message_y, self.right_panel_width - 10, (0, 0, 0))

    # ── Inventory and Captain Card ──────────────────────────────────────────────────────
    def draw_inventory_panel(self):

        inventory_image = self.ui_images["Inventory Bar.jpg"]
        self.screen.blit(inventory_image,(0, int(650/900 * self.height)))

    def draw_inventory_info(self):
        player = self.get_my_player()
        if player is None:
            return

        categories = [
            ("Wrangle", player["wrangles"]),
            ("Maps", player["maps"]),
            ("Pubs", player["pubs"]),
            ("Supplies", player["supplies"]),
            ("Rendezvous", player["rendezvous"]),
            ("Guards", player["large_guard"] + player["small_guard"]),
            ("Treasure", player["treasure"]),
            ("Scorpions", player["scorpions"])
        ]

        section_width = (self.width - 50) / len(categories)

        y = 680/900 * self.height

        for i, (title, cards) in enumerate(categories):
            x = i * section_width + 25 / 1600 * self.width      ####buffer

            # show cards in inv
            size = self.small_card_size 
            card_y = y + 30 
            max_per_row = 4
            for idx, card in enumerate(cards):
                image_key = card["image_file"]
                if image_key in self.card_images:
                    img = pygame.transform.smoothscale(
                        self.card_images[image_key],
                        (size, size)
                    )
                    row = idx // max_per_row
                    col = idx % max_per_row
                    card_x = x + 5 + col * (size + 2)
                    self.screen.blit(img, (card_x, card_y + row * (size + 2)))
                    if card.get("completed"):
                        star = self.font.render("*",True, (0,200,0))
                        self.screen.blit(star, (card_x + (size - star.get_width())/2,card_y + row * (size + 2)))

            score = player["score"].get(title.lower(), 0)
            score_label = self.small_font.render(
                f"Total: {score}",
                True,
                (0, 0, 0)
            )
            self.screen.blit(score_label,(x + 5, self.height - 60))
            label = self.small_font.render(title, True, (0,0,0))
            self.screen.blit(label, (x + 5, y + 5))

        total_score = player["score"]["total"]
        total_score_label = self.menu_font.render(str(total_score),True,(0,0,0))
        self.screen.blit(total_score_label, (1520/1600*self.width, 750/900*self.height))

    def draw_character_card_overlay(self):
        if self.active_character_card is None:
            return
        players = self.game_state.get("players", [])
        if self.active_character_card >= len(players):
            return
        player = players[self.active_character_card]
        character = player.get("character")
        if not character:
            return

        # Draw over the action log area (left panel)
        card_w = int(290/1600 * self.width)
        card_h = int(390/900 * self.height)
        card_x = int(66/1600*self.width)
        card_y = int(115/900 * self.height)

        # Character image
        image_key = character.get("image")
        if image_key and image_key in self.ui_images:
            img = pygame.transform.smoothscale(self.ui_images[image_key], (card_w, card_h))
            self.screen.blit(img, (card_x, card_y))

    # ── Board images — dice, cards, guards ──────────────────────────────────────────────────────
    def draw_images(self):   ####### Dice images, guards, supplies
        card_size = self.board_width / 6
        x = int(self.board_x + (self.board_width - card_size) / 2)
        y = (self.board_height - card_size) / 2

        treasure = self.ui_images["Treasure.png"]
        self.screen.blit(treasure,(85/1600*self.width, 550/900*self.height))
        
        if self.game_state["phase"] == "supply_card" and self.is_my_turn():
            card = self.game_state.get("supply")
            if not card:
                return

            image_key = card["image_file"]
            if image_key not in self.card_images:
                return

            img = pygame.transform.smoothscale(self.card_images[image_key], (card_size, card_size))
            self.screen.blit(img, (x, y))

        
        if self.game_state["phase"] == "har_supply" and self.is_my_turn():
            self.har_rects = []

            selection = self.game_state.get("har_selection", None)
            
            har_x1 = int(self.board_x + (self.board_width - card_size * 3) / 2)
            har_x2 = har_x1 + 2* card_size
            
            # Set up first card
            card = self.game_state.get("supply")
            if not card:
                return

            image_key = card["image_file"]
            if image_key not in self.card_images:
                return
            
            selected1 = selection is not None and selection["image_file"] == card["image_file"]
            border_color1 = (200, 180, 80) if selected1 else (80, 80, 80)
            border_width1 = 5 if selected1 else 2

            rect = pygame.Rect(har_x1, y, card_size, card_size)
            self.har_rects.append((rect, card))
            
            # Set up second card
            card2 = self.game_state.get("har_supply")
            if not card2:
                return

            image_key2 = card2["image_file"]
            if image_key2 not in self.card_images:
                return

            selected2 = selection is not None and selection["image_file"] == card2["image_file"]
            border_color2 = (200, 180, 80) if selected2 else (80, 80, 80)
            border_width2 = 5 if selected2 else 2

            rect2 = pygame.Rect(har_x2, y, card_size, card_size)
            self.har_rects.append((rect2, card2))
            
            pygame.draw.rect(self.screen, border_color1, rect, border_radius=8)
            pygame.draw.rect(self.screen, border_color1, rect, border_width1, border_radius=8)
            pygame.draw.rect(self.screen, border_color2, rect2, border_radius=8)
            pygame.draw.rect(self.screen, border_color2, rect2, border_width2, border_radius=8)

            img = pygame.transform.smoothscale(self.card_images[image_key], (card_size - 10, card_size - 10))
            self.screen.blit(img, (har_x1 + 5, y + 5))
            img2 = pygame.transform.smoothscale(self.card_images[image_key2], (card_size - 10, card_size - 10))
            self.screen.blit(img2, (har_x2 + 5, y + 5))


        if self.game_state["phase"] == "rendezvous_card" and self.is_my_turn():
            card = self.game_state.get("rendezvous")
            if not card:
                return

            image_key = card["image_file"]
            if image_key not in self.card_images:
                return

            img = pygame.transform.smoothscale(
                self.card_images[image_key],
                (card_size, card_size)
            )

            self.screen.blit(img, (x, y))

        if self.game_state["phase"] == "guard_battle":
            card = self.game_state.get("guard")
            if not card:
                return

            image_key = card["image_file"]
            if image_key not in self.card_images:
                return

            img = pygame.transform.smoothscale(
                self.card_images[image_key],
                (card_size, card_size)
            )

            self.screen.blit(img, (x, y))
        
        if (self.game_state["phase"] == "roll_no_barrels" or self.game_state["phase"] == "roll_with_barrels"
              or self.game_state["phase"] == "roll_with_rerolls"):
            die = self.game_state.get("current_roll")
            
            if not die:
                return
            
            image_key = die["image"]
            if image_key not in self.dice_images:
                return
            
            img = pygame.transform.smoothscale(
                self.dice_images[image_key],
                (card_size, card_size)
            )

            self.screen.blit(img, (x, y))

    # ── Wrangle screens ──────────────────────────────────────────────────────
    def draw_wrangle_setup(self):
        wrangle_view = self.save_data.settings.get("wrangle_view", "Classic")
        if wrangle_view == "Cinematic":
            self.draw_wrangle_cinematic()
        else:
            self.draw_wrangle()
    
    def draw_wrangle(self):
        wrangle_image = self.ui_images["Wrangle.png"]
        wrangle_width = wrangle_image.get_width()
        wrangle_x = self.board_x + (self.board_width - wrangle_width)/2
        self.screen.blit(wrangle_image,(wrangle_x, self.board_y + 50/900*self.height))
        
        players = self.game_state["players"]
        wrangle = self.game_state["wrangle"]
        current_leader = wrangle.get("leader")
 
        # Sort players by board_position (earliest = top)
        active_players = [p for p in players if p["board_position"] != 0]
        sorted_players = sorted(active_players, key=lambda p: p["board_position"])
 
        pirate_radius = max(8, int(self.board_width * 0.015))
        pirate_diameter = pirate_radius * 2
        pirate_gap = max(4, pirate_radius // 2)
        row_height = max(50 / 900 * self.height, pirate_diameter + 20 / 900 * self.height)
        name_col_width = 280 / 1600 * self.width
        padding_left = 45 / 1600 * self.width
 
        # Divider x between active and safe pirates
        divider_x = self.board_x + self.board_width - int(self.board_width * 0.28)
        status_y = 700/900 * self.height
        x_center = self.board_width /2 + self.board_x
 
        # Header labels
        active_label = self.menu_font.render("Active", True, (0, 0, 0))
        safe_label = self.menu_font.render("Safe", True, (0, 0, 0))
        self.screen.blit(active_label, (self.board_x + 175/1600*self.width, 200 / 900 * self.height))
        self.screen.blit(safe_label, (x_center + 100/1600*self.width, 200 / 900 * self.height))
 
        #draw each player in row
        for i, player in enumerate(sorted_players):
            color = player["color"]
            y_start = 325/900*self.height + i * row_height + row_height // 2
 
            # Player name on the left
            name_label = self.font.render(player["name"], True, (0, 0, 0))
            self.screen.blit(name_label, (self.board_x + padding_left, y_start - name_label.get_height() // 2))
 
            # Active pirates left to right from name column
            active_x = x_center - 37/1600*self.width
            for _ in range(player["wrangle_pirates"]):
                pygame.draw.circle(self.screen, color, (active_x - pirate_radius, y_start), pirate_radius)
                pygame.draw.circle(self.screen, (255, 255, 255), (active_x - pirate_radius, y_start), pirate_radius, 1)
                active_x -= (pirate_diameter + pirate_gap)
 
            # Safe pirates right of the divider
            safe_x = x_center + 34/1600*self.width
            for _ in range(player["safe_pirates"]):
                pygame.draw.circle(self.screen, color, (safe_x + pirate_radius, y_start), pirate_radius)
                pygame.draw.circle(self.screen, (255, 255, 255), (safe_x + pirate_radius, y_start), pirate_radius, 2)
                safe_x += pirate_diameter + pirate_gap
 
        # Status: who is rolling and current leader
        if self.game_state.get("phase") == "roll_start" and self.game_state.get("next_roller") is not None:
            roller_id = self.game_state["next_roller"]

            roller = players[roller_id] if 0 <= roller_id < len(players) else None

            if roller:
                status = self.font.render(f"Rolling: {roller['name']}", True, (0, 0, 0))
                self.screen.blit(status, (self.board_x + padding_left, status_y))

        # Leader status
        if current_leader is not None:
            leader = players[current_leader] if 0 <= current_leader < len(players) else None

            if leader:
                roll = wrangle.get("leader_roll", "?")
                leader_label = self.font.render(
                    f"Leader: {leader['name']} (rolled {roll})",
                    True,
                    (0, 0, 0)
                )
                self.screen.blit(leader_label, (self.board_x + padding_left + 2, status_y + 50/900*self.height))

    def draw_wrangle_cinematic(self):
        wrangle_image = self.ui_images["Alternate Wrangle.jpg"]
        self.screen.blit(wrangle_image,(self.board_x, self.board_y))
        
        players = self.game_state["players"]
        wrangle = self.game_state["wrangle"]
        current_leader = wrangle.get("leader")
 
        # Sort players by board_position (earliest = top)
        active_players = [p for p in players if p["board_position"] != 0]
        sorted_players = sorted(active_players, key=lambda p: p["board_position"])
 
        pirate_radius = max(8, int(self.board_width * 0.015))
        pirate_diameter = pirate_radius * 2
        pirate_gap = max(4, pirate_radius // 2)
        row_height = max(50 / 900 * self.height, pirate_diameter + 20 / 900 * self.height)
        name_col_width = 280 / 1600 * self.width
        padding_left = 45 / 1600 * self.width
 
        # Divider x between active and safe pirates
        divider_x = self.board_x + self.board_width - int(self.board_width * 0.28)
        status_y = 675/900 * self.height
        x_center = self.board_width /2 + self.board_x
 
        # Header labels
        active_label = self.menu_font.render("Active", True, (255, 255, 255))
        safe_label = self.menu_font.render("Safe", True, (255, 255, 255))
        self.screen.blit(active_label, (self.board_x + 175/1600*self.width, 200 / 900 * self.height))
        self.screen.blit(safe_label, (x_center + 100/1600*self.width, 200 / 900 * self.height))
 
        #draw each player in row
        for i, player in enumerate(sorted_players):
            color = player["color"]
            y_start = 325/900*self.height + i * row_height + row_height // 2
 
            # Player name on the left
            name_label = self.font.render(player["name"], True, (255, 255, 255))
            self.screen.blit(name_label, (self.board_x + padding_left, y_start - name_label.get_height() // 2))
 
            # Active pirates left to right from name column
            active_x = x_center - 37/1600*self.width
            for _ in range(player["wrangle_pirates"]):
                pygame.draw.circle(self.screen, color, (active_x - pirate_radius, y_start), pirate_radius)
                pygame.draw.circle(self.screen, (255, 255, 255), (active_x - pirate_radius, y_start), pirate_radius, 1)
                active_x -= (pirate_diameter + pirate_gap)
 
            # Safe pirates right of the divider
            safe_x = x_center + 34/1600*self.width
            for _ in range(player["safe_pirates"]):
                pygame.draw.circle(self.screen, color, (safe_x + pirate_radius, y_start), pirate_radius)
                pygame.draw.circle(self.screen, (255, 255, 255), (safe_x + pirate_radius, y_start), pirate_radius, 2)
                safe_x += pirate_diameter + pirate_gap
 
        # Status: who is rolling and current leader
        if self.game_state.get("phase") == "roll_start" and self.game_state.get("next_roller") is not None:
            roller_id = self.game_state["next_roller"]

            roller = players[roller_id] if 0 <= roller_id < len(players) else None

            if roller:
                status = self.font.render(f"Rolling: {roller['name']}", True, (255, 255, 255))
                self.screen.blit(status, (self.board_x + padding_left, status_y))

        # Leader status
        if current_leader is not None:
            leader = players[current_leader] if 0 <= current_leader < len(players) else None

            if leader:
                roll = wrangle.get("leader_roll", "?")
                leader_label = self.font.render(
                    f"Leader: {leader['name']} (rolled {roll})",
                    True,
                    (255, 255, 255)
                )
                self.screen.blit(leader_label, (self.board_x + padding_left + 2, status_y + 50/900*self.height))

    # ── End scores ──────────────────────────────────────────────────────
    def draw_end_scores(self):

        score_image = self.ui_images["Game Over.jpg"]
        self.screen.blit(score_image,(0, 0))

        players = sorted(
            self.game_state["players"],
            key=lambda p: (
                p["score"].get("total", 0),
                -p.get("pirate_reserve", 0),
                p.get("barrels", 0),
                p.get("coins", 0)
            ),
            reverse=True
        )

        col_labels = ["Wrangle", "Maps", "Pubs", "Supplies", "Rendezvous", "Guards", "Treasure", "Scorpions", "Total"]
        num_cols = len(col_labels) + 1  # +1 for player name column

        table_x = 470/1600*self.width
        table_y = 425/900*self.height 
        col_width = 56/1600*self.width 
        row_height = 40

        for j, label in enumerate(col_labels): 
            x = table_x + (j + 1) * col_width + col_width // 2
            self.draw_angled_label(self.screen, self.font, label, (0, 0, 0), x, table_y, angle=40)

        for i, player in enumerate(players):
            categories = [
                ("Wrangle", player["wrangles"]),
                ("Maps", player["maps"]),
                ("Pubs", player["pubs"]),
                ("Supplies", player["supplies"]),
                ("Rendezvous", player["rendezvous"]),
                ("Guards", player["large_guard"] + player["small_guard"]),
                ("Treasure", player["treasure"]),
                ("Scorpions", player["scorpions"])
            ]

            y = table_y + (i + 1) * row_height

            name = self.font.render(player["name"], True, (0,0,0))
            self.screen.blit(name, (table_x - 5 ,y-3))

            for j, (label, cards) in enumerate(categories):
                score = player["score"].get(label.lower(), 0)
                rendered = self.small_font.render(str(score), True, (0, 0, 0))
                x = table_x + (j + 1) * col_width + col_width // 2 #- rendered.get_width() // 2
                self.screen.blit(rendered, (x, y))

            # Total
            total = player["score"].get("total", 0)
            total_rendered = self.font.render(str(total), True, (0, 0, 0))
            x = table_x + num_cols * col_width - col_width // 2 #- total_rendered.get_width() // 2
            self.screen.blit(total_rendered, (x+5, y-5))

    def draw_angled_label(self, surface, font, text, color, x, y, angle=45):
        text_surface = font.render(text, True, color)
        rotated = pygame.transform.rotate(text_surface, angle)
        # After rotation, offset so the label sits above the column
        surface.blit(rotated, (x, y - rotated.get_height()))

    # ── Helpers — draw_wrapped_text, draw_angled_label ──────────────────────────────────────────────────────
    def draw_wrapped_text(self, font, text, x, y, max_width, color):
        words = text.split(" ")
        line = ""

        for word in words:
            test_line = line + word + " "
            line_width, _ = font.size(test_line)

            if line_width > max_width and line:
                rendered = font.render(line.strip(), True, color)
                self.screen.blit(rendered, (x, y))
                y += font.get_linesize()
                line = word + " "
            else:
                line = test_line

        # Draw any remaining text
        if line:
            rendered = font.render(line.strip(), True, color)
            self.screen.blit(rendered, (x, y))
            y += font.get_linesize()

        return y  # return updated y so the caller knows where to continue

    def draw_wrapped_text_up(self, font, text, x, y, max_width, color):

        words = text.split()

        lines = []
        current = ""

        for word in words:
            test = current + (" " if current else "") + word

            if font.size(test)[0] <= max_width:
                current = test
            else:
                lines.append(current)
                current = word

        if current:
            lines.append(current)

        line_height = font.get_linesize()

        for line in reversed(lines):
            label = font.render(line, True, color)
            self.screen.blit(label, (x, y))
            y -= line_height

        return y

    ######################################################################
    # BUTTONS & UI HELPERS
    ######################################################################

    # ── Build all buttons for current phase ──────────────────────────────────────────────────────
    def build_buttons(self): 
        self.buttons = []
        self.transparent_buttons = []
        
        phase = self.game_state["phase"]
        menu_level = self.game_state["menu"]["menu_level"]

        players = self.game_state["players"]
        current = self.game_state["active_player"]

        # Menu button sizes
        menu_option_width = int(300 / 1600 * self.width) 
        menu_option_height = int(70 / 900 * self.height)
        menu_option_x = int(((((490/1600*self.width) - menu_option_width) / 2) + 100/1600*self.width))
        menu_option_y = int(320 / 900 * self.height)
        menu_y_buffer = int(80 / 900 * self.height)

        player_plus_y = int(320 / 900 * self.height)
        start_game_y = int(640 / 900 * self.height)

        # Set Game Settings
        settings = self.save_data.settings
        rs_value = "On" if settings.get("random_start") else "Off"
        rs_color = (200, 180, 80) if settings.get("random_start") else (80, 80, 80)
        captains_value = "On" if settings.get("play_with_characters") else "Off"
        captains_color = (200, 180, 80) if settings.get("play_with_characters") else (80, 80, 80)

        if phase == "menu" and menu_level == "main":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(menu_option_x, menu_option_y - 50, menu_option_width, menu_option_height,"Host Game", self.host_game))
            self.transparent_buttons.append(Button(menu_option_x, menu_option_y - 50 + menu_y_buffer, menu_option_width, menu_option_height,"Join Game", self.join_game))
            self.transparent_buttons.append(Button(menu_option_x, menu_option_y - 50 + menu_y_buffer * 2, menu_option_width, menu_option_height,"Active Games", self.view_active_games))
            self.transparent_buttons.append(Button(menu_option_x, menu_option_y - 50 + menu_y_buffer * 3, menu_option_width, menu_option_height,"Settings", self.settings_menu))
            self.transparent_buttons.append(Button(menu_option_x, menu_option_y - 50 + menu_y_buffer * 4, menu_option_width, menu_option_height,"Statistics", self.stats_menu))
            self.transparent_buttons.append(Button(menu_option_x, menu_option_y - 50 + menu_y_buffer * 5, menu_option_width, menu_option_height,"Quit", self.quit_game))

        if phase == "menu" and menu_level == "new_game":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(int(355/1600*self.width), player_plus_y, menu_option_width / 4, menu_option_height / 1.4, "+1", self.increase_players))
            self.transparent_buttons.append(Button(int(270/1600*self.width), player_plus_y, menu_option_width / 4, menu_option_height / 1.4, "-1", self.decrease_players))
            self.transparent_buttons.append(Button(menu_option_x, start_game_y, menu_option_width, menu_option_height, "Start Game", self.start_game))
            self.transparent_buttons.append(Button(menu_option_x, start_game_y + 75/900*self.height, menu_option_width, menu_option_height, "Cancel", self.return_menu))
        
        if phase == "menu" and menu_level == "host_lobby":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(int(355/1600*self.width), player_plus_y + 25, menu_option_width / 4, menu_option_height / 1.4, ">", self.increase_players))
            self.transparent_buttons.append(Button(int(270/1600*self.width), player_plus_y + 25, menu_option_width / 4, menu_option_height / 1.4, "<", self.decrease_players))
            self.buttons.append(Button(375/1600*self.width, 490/900*self.height , 150/1600*self.width, 50, rs_value, self.toggle_random_start, color=rs_color))
            self.buttons.append(Button(375/1600*self.width, 575/900*self.height , 150/1600*self.width, 50, captains_value, self.toggle_characters, color=captains_color))
            self.transparent_buttons.append(Button(menu_option_x, start_game_y, menu_option_width, menu_option_height, "Host Game", self.confirm_host))
            self.transparent_buttons.append(Button(menu_option_x, start_game_y + 75/900*self.height, menu_option_width, menu_option_height, "Cancel", self.return_menu))
        
        if phase == "menu" and menu_level == "join_lobby":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(menu_option_x, start_game_y, menu_option_width, menu_option_height, "Join", self.confirm_join))
            self.transparent_buttons.append(Button(menu_option_x, start_game_y + 75/900*self.height, menu_option_width, menu_option_height, "Cancel", self.return_menu))
            self.transparent_buttons.append(Button(455/1600*self.width, 275/900*self.height, 50, 40, " ", self.refresh_rooms))

        if phase == "menu" and menu_level == "active_games":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(455/1600*self.width, 275/900*self.height, 50, 40, " ", self.fetch_active_games))
            self.transparent_buttons.append(Button(menu_option_x, start_game_y + 75/900*self.height, menu_option_width, menu_option_height, "Back", self.return_menu))

        if phase == "menu" and menu_level == "waiting_room":
            self.buttons = []
            self.transparent_buttons = []
            # Host sees a Start button once enough players have joined, joiners just wait
            if self.game_state["menu"]["multiplayer_mode"] == "host":
                lobby_players = self.game_state["menu"]["lobby_players"]
                if len(lobby_players) >= self.game_state["menu"]["player_count"]:
                    self.transparent_buttons.append(Button(menu_option_x, start_game_y, menu_option_width, menu_option_height, "Start Game", self.start_multiplayer_game))
            self.transparent_buttons.append(Button(menu_option_x, start_game_y + 75/900*self.height, menu_option_width, menu_option_height, "Cancel", self.return_menu))
        
        if phase == "game_over":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(70/1600*self.width, 511/900*self.height, 280/1600*self.width, 100/900*self.height, "Main Menu", self.return_menu, color=(180, 180, 180), text_color=(255,255,255)))
            self.transparent_buttons.append(Button(70/1600*self.width, 619/900*self.height, 280/1600*self.width, 100/900*self.height,"Quit", self.quit_game, color=(180, 180, 180), text_color=(255,255,255)))

        stat_button_width = 275
        stat_button_height = 60
        center_x = 800 / 1600 * self.width
        button1_x = center_x - 50 - 1.5 * stat_button_width
        button3_x = center_x + .5 * stat_button_width + 50
        
        if phase == "menu" and (menu_level == "stats_1" or menu_level == "stats_2" or menu_level == "elo"):
            self.buttons = []
            self.transparent_buttons = []
            ga_color = (200, 180, 80) if menu_level == "stats_1" else (145, 145, 145)
            self.buttons.append(Button(button1_x, 275/900*self.height, stat_button_width, stat_button_height,"Averages", self.toggle_stats_1, color = ga_color))
            other_color = (200, 180, 80) if menu_level == "stats_2" else (145, 145, 145)
            self.buttons.append(Button(center_x - stat_button_width/2, 275/900*self.height, stat_button_width, stat_button_height,"Wins", self.toggle_stats_2, color = other_color))
            elo_color = (200, 180, 80) if menu_level == "elo" else (145, 145, 145)
            self.buttons.append(Button(button3_x, 275/900*self.height, stat_button_width, stat_button_height,"Leaderboard", self.toggle_elo_leaderboard, color = elo_color))

            self.transparent_buttons.append(Button(center_x - stat_button_width/2, 800/900*self.height, stat_button_width, stat_button_height, "Main Menu", self.return_menu))


        ########## In Game Buttons ##########
        if phase == "character_select":
            self.buttons = []
            self.transparent_buttons = []
            my_index = self.my_player_index if self.my_player_index is not None else 0
            selections = self.game_state.get("character_selections", [])
            confirmed = self.game_state.get("character_confirmed", [])
            my_selection = selections[my_index] if my_index < len(selections) else None
            already_confirmed = confirmed[my_index] if my_index < len(confirmed) else False

            if my_selection is not None and not already_confirmed:
                self.buttons.append(Button(self.width // 2 - 150, int(720/900*self.height),300, 70, "Set Sail!", self.confirm_character_select, text_color=(0, 0, 0)))
        
        game_button_width = int(250)
        game_button_height = int(60)
        game_button_x = int((self.right_panel_width - game_button_width) / 2 + self.right_panel_x)
        game_button_y1 = int(600 / 750 * self.height)
        game_button_y2 = int(663 / 750 * self.height)
        
        if phase != "menu":
            if not self.is_my_turn() and not self.is_my_action():
                # Add inventory button and captain card buttons
                if phase != "new_game" and phase != "game_over":
                    self.transparent_buttons.append(Button(100/1600*self.width, 550/900*self.height,75,55," ", self.toggle_inventory))

                players = self.game_state.get("players", [])
                for i, player in enumerate(players):
                    if player.get("character"):
                        self.transparent_buttons.append(Button(int(120/1600*self.width),int((620 + i * 45)/900*self.height), int(150/1600*self.width), int(35/900*self.height), " ", lambda idx=i: self.toggle_character_card(idx)))
            
                # Card locations from draw
                card_w = int(290/1600 * self.width)
                card_x = int(66/1600*self.width)
                card_y = int(115/900 * self.height)
                if self.active_character_card is not None:
                    self.transparent_buttons.append(Button(card_x + card_w - 45/1600*self.width, card_y + 5/900*self.height, 40/1600*self.width, 40/900*self.height, "X", lambda: setattr(self, "active_character_card", None), text_color=(255, 0, 0)))
                
                # Chat and Home buttons 
                self.transparent_buttons.append(Button(140/1600*self.width, 15/900*self.height,60,60," ", self.return_menu))
                self.transparent_buttons.append(Button(220/1600*self.width, 15/900*self.height,60,60," ", self.toggle_chat))
                
                return

        if phase == "start_turn":
            self.buttons = []
            self.transparent_buttons = []
            player = self.game_state["players"][self.game_state["active_player"]]

            if player["coins"] > 0:
                self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Rest", self.rest))

            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Go On Board", self.confirm_boarding))

        if phase == "confirm_boarding":
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Confirm", self.go_on_board))
            self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Cancel", self.cancel_boarding))

        if phase == "confirm_move":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Confirm Move", self.confirm_move))
            self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Cancel", self.cancel_move))

        if phase == "dark_alley_confirm":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Confirm Move", self.confirm_dark_alley))
            self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Cancel", self.cancel_dark_alley))
        
        if phase == "post_move":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Avast", self.avast))
            if players[current]["coins"] > 0:
                self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Spend a coin to go again", self.move_again))

        if phase == "supply_card":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Accept", lambda: self.resolve_supply(True)))
            self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Return for 2 coins", lambda: self.resolve_supply(False)))

        if phase == "har_supply":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Accept", lambda: self.resolve_har_supply(True)))
            self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Return for 2 coins", lambda: self.resolve_har_supply(False)))
        
        if phase == "rendezvous_card":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Accept", self.resolve_rendezvous))

        if phase == "dark_alley_ask":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Spend a coin", lambda: self.pay_dark_alley(True)))
            self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Cancel move", lambda: self.pay_dark_alley(False)))

        if phase == "guard_start":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Small Guard", lambda: self.battle_guard("small")))
            self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Large Guard", lambda: self.battle_guard("large")))

        if phase == "guard_battle":
            self.transparent_buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Fight", self.resolve_guard))

        if phase == "roll_start":
            self.transparent_buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Roll", self.roll_start))
        
        if phase == "roll_no_barrels":
            self.transparent_buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Accept", self.resolve_roll))

        if phase == "roll_with_barrels":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Accept", self.resolve_roll))
            self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Use a barrel", self.resolve_reroll))

        if phase == "roll_with_rerolls":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Accept", self.resolve_roll))
            self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Reroll", self.resolve_reroll))

        if phase == "pub_invite":
            self.transparent_buttons = []
            # Check if player being asked has coins
            pub = self.game_state["pub"]
            asked_player = pub["current_ask"]
            player = self.game_state["players"][asked_player]
            
            if player["coins"] > 0:
                self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Drink", lambda: self.answer_pub_invite(True)))
                self.transparent_buttons.append(Button(game_button_x, game_button_y2, game_button_width, game_button_height, "Stay Home", lambda: self.answer_pub_invite(False)))
            else:
                self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Stay Home", lambda: self.answer_pub_invite(False)))

        if phase == "reclaim_fail":
            self.buttons = []
            self.transparent_buttons = []
            self.transparent_buttons.append(Button(game_button_x, game_button_y1, game_button_width, game_button_height, "Select Again", self.reclaim_fail))

        ### Draw toggle inventory button all the time
        if phase != "menu" and phase != "game_over":
            self.transparent_buttons.append(Button(100/1600*self.width, 550/900*self.height,75,55," ", self.toggle_inventory))

            players = self.game_state.get("players", [])
            for i, player in enumerate(players):
                if player.get("character"):
                    self.transparent_buttons.append(Button(int(120/1600*self.width),int((620 + i * 45)/900*self.height), int(150/1600*self.width), int(35/900*self.height), " ", lambda idx=i: self.toggle_character_card(idx)))
            
            # Card locations from draw
            card_w = int(290/1600 * self.width)
            card_x = int(66/1600*self.width)
            card_y = int(115/900 * self.height)
            if self.active_character_card is not None:
                self.transparent_buttons.append(Button(card_x + card_w - 45/1600*self.width, card_y + 5/900*self.height, 40/1600*self.width, 40/900*self.height, "X", lambda: setattr(self, "active_character_card", None), text_color=(255, 0, 0)))

            # Chat and Home buttons 
            self.transparent_buttons.append(Button(140/1600*self.width, 15/900*self.height,60,60," ", self.return_menu))
            self.transparent_buttons.append(Button(220/1600*self.width, 15/900*self.height,60,60," ", self.toggle_chat))

    # ── Inventory toggle and player lookup ──────────────────────────────────────────────────────
    def toggle_inventory(self):
        self.inventory_open = not self.inventory_open
        self.rescale_board()
        self.rescale_ui(self.raw_ui_images) 
        self.build_buttons()

    def get_my_player(self):
        """Returns this client's player data regardless of whose turn it is."""
        if self.network is None:
            # Local game - show active player's inventory
            return self.game_state["players"][self.game_state["active_player"]]
        # Multiplayer - always show your own cards
        if self.my_player_index is not None:
            return self.game_state["players"][self.my_player_index]
        return None

    def toggle_character_card(self, player_index):
        if self.active_character_card == player_index:
            self.active_character_card = None
        else:
            self.active_character_card = player_index

    # ── Turn helpers — is_my_turn, is_my_action ──────────────────────────────────────────────────────
    def is_my_turn(self):
        """Returns True if this client is allowed to act."""
        # Local game - always your turn
        if self.network is None:
            return True
        
        if self.game_state["phase"] in ("roll_start", "roll_no_barrels", "roll_with_barrels", "roll_with_rerolls", "pub_invite"):
            return False

        return self.game_state["active_player"] == self.my_player_index

    def is_my_action(self):
        """Returns True if this client needs to act right now, even if it's not their main turn."""
        if self.network is None:
            return True

        phase = self.game_state["phase"]
        players = self.game_state["players"]

        # Pub invite - the player being asked needs to respond
        if phase == "pub_invite":
            pub = self.game_state["pub"]
            return pub["current_ask"] == self.my_player_index

        # Rolling phases - check whose roll it is
        if phase in ("roll_start", "roll_no_barrels", "roll_with_barrels", "roll_with_rerolls"):
            next_roller = self.game_state.get("next_roller")
            if next_roller is not None:
                return next_roller == self.my_player_index

        return False

    ######################################################################
    # GAME SETUP
    ######################################################################

    def increase_players(self):
        if self.game_state["menu"]["player_count"] < 5:
            self.game_state["menu"]["player_count"] += 1
        return self.game_state
    
    def decrease_players(self):
        if self.game_state["menu"]["player_count"] > 2:
            self.game_state["menu"]["player_count"] -= 1
        return self.game_state

    def start_game(self):
        menu = self.game_state["menu"]

        player_count = menu["player_count"]

        names = [
            menu["player_names"][i].strip() if i < len(menu["player_names"]) else ""
            for i in range(player_count)
        ]

        players = self.rules.create_players(player_count, names)
        random.shuffle(players)
        self.game_state["occupied_paths"] = []


        self.game_state["players"] = players
        self.game_state["phase"] = "start_turn"
        pygame.mixer.music.fadeout(1000)

        return self.game_state 

    def new_game(self):
        self.game_state["menu"]["menu_level"] = "new_game"

    def settings_menu(self):
        self.game_state["menu"]["menu_level"] = "settings_menu"

    def stats_menu(self):
        self.game_state["menu"]["menu_level"] = "stats_1"
    
    def start_multiplayer_game(self):
        """
        Ask the server to build the full game state and broadcast it to all
        clients.  We no longer generate the board or shuffle players locally.
        The server's on_new_game handler (server.py) calls
        board_setup.new_game_state() and emits state_updated to everyone.
        my_player_index is resolved later inside apply_network_state() when
        the state_updated payload arrives with the shuffled player list.
        """
        self.network.sio.emit("new_game", {
            "room_id": self.room_id,
            "play_with_characters": self.save_data.settings.get("play_with_characters", False),
            "random_start": self.save_data.settings.get("random_start", False),
        })

    def confirm_character_select(self):
        """
        Tell the server which character this player has chosen.
        The server tracks confirmations; once all players confirm it
        assigns characters, generates the board, and sends state_updated.
        """
        my_index = self.my_player_index if self.my_player_index is not None else 0
        selections = self.game_state.get("character_selections", [])
        selected_name = selections[my_index] if my_index < len(selections) else None

        self.network.sio.emit("confirm_character", {
            "room_id": self.room_id,
            "player_index": my_index,
            "selected_name": selected_name,
            "random_start": self.save_data.settings.get("random_start", False),
        })
        self.build_buttons()

    def finish_character_reveal(self):
        """
        The character reveal animation has finished.  In the thin-client model
        the server already sent the board via state_updated when the last
        player confirmed their character, so apply_network_state() has already
        built and rescaled the board.  We just clean up local animation state
        and rebuild buttons.
        """
        self.game_state.pop("reveal_start_time", None)
        self.build_buttons()

    def return_menu(self):

        #if self.game_state["phase"] == "game_over":
        fresh_state = self.setup.game_setup(start_in_menu=True)
        self.game_state.clear()
        self.game_state.update(fresh_state)

        self.network = None
        self.room_id = None
        self.is_host = False
        self.my_player_index = None
        self.lobby_players = []
        self.raw_board = None
        self.board_surface = None
        self.rescale_ui(self.raw_ui_images) 

        self.stats = self.save_data.load_stats_from_server()

        self.game_state["phase"] = "menu"
        self.game_state["menu"]["menu_level"] = "main"

    def quit_game(self):
        if hasattr(self, "server_process") and self.server_process:
            self.server_process.terminate()
        
        self.running = False

    def on_game_over(self):
        import threading
        threading.Thread(
            target=self.save_data.record_game_result,
            args=(self.game_state["players"],),
            daemon=True
        ).start()
        if self.my_player_index is not None:
            my_name = self.game_state["players"][self.my_player_index]["name"]
            self.save_data.settings["player_name"] = my_name
            self.save_data.save_settings()
        self.build_buttons()
        self.broadcast_state()

    ######################################################################
    # SETTINGS
    ######################################################################

    def set_resolution(self, resolution):
        self.save_data.settings["resolution"] = resolution
        self.save_data.save_settings()
        flags = pygame.FULLSCREEN if self.save_data.settings["fullscreen"] else 0
        self.screen = pygame.display.set_mode(resolution, flags)
        self.rescale_board()
        self.rescale_ui(self.raw_ui_images)

    def toggle_fullscreen(self):
        self.save_data.settings["fullscreen"] = not self.save_data.settings["fullscreen"]
        self.save_data.save_settings()

        resolution = self.save_data.settings["resolution"]
        self.screen = self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN) if self.save_data.settings["fullscreen"] else pygame.display.set_mode(resolution, pygame.RESIZABLE)
        self.update_screen_size()

    def set_wrangle_view(self, mode):
        self.save_data.settings["wrangle_view"] = mode
        self.save_data.save_settings()

    def toggle_random_start(self):
        self.save_data.settings["random_start"] = not self.save_data.settings.get("random_start", False)
        self.save_data.save_settings()

    def toggle_characters(self):
        self.save_data.settings["play_with_characters"] = not self.save_data.settings.get("play_with_characters", False)
        self.save_data.save_settings()

    def toggle_stats_1(self):
        self.game_state["menu"]["menu_level"] = "stats_1" 
        self.game_state["menu"]["stats_scroll"] = 0

    def toggle_stats_2(self):
        self.game_state["menu"]["menu_level"] = "stats_2"
        self.game_state["menu"]["stats_scroll"] = 0

    def toggle_elo_leaderboard(self):
        self.game_state["menu"]["menu_level"] = "elo"  
        self.game_state["menu"]["stats_scroll"] = 0  

    ######################################################################
    # GAME ACTIONS
    ######################################################################

    # ── Core turn actions ──────────────────────────────────────────────────────
    def log_action(self, text):
        self.game_state["action_log"].append(text)

    def confirm_move(self):
        # No-op: the server auto-confirms moves after processing them.
        pass
    
    def confirm_dark_alley(self):
        self.send_action({"type": "pay_dark_alley", "accepted": True})

    def cancel_move(self):
        # In the server model moves are sent only after player confirms in UI,
        # so there is nothing to cancel at the server level.
        pass

    def cancel_dark_alley(self):
        self.send_action({"type": "cancel_dark_alley"})

    def rest(self):
        self.send_action({"type": "rest"})

    def cancel_boarding(self):
        # Boarding confirmation is local UI state only; just rebuild buttons.
        self.game_state["phase"] = "start_turn"
        self.build_buttons()

    def confirm_boarding(self):
        self.game_state["phase"] = "confirm_boarding"

    def go_on_board(self):
        self.send_action({"type": "go_on_board"})

    def avast(self):
        self.send_action({"type": "avast"})

    # ── Space resolution — supply, rendezvous, dark alley, guards, rolls ──────────────────────────────────────────────────────
    def resolve_supply(self, accepted):
        self.send_action({"type": "supply_choice", "keep_card": accepted})

    def resolve_har_supply(self, accepted):
        chosen = self.game_state.get("har_selection")
        chosen_index = None
        if chosen is not None:
            har_supply = self.game_state.get("har_supply", [])
            for i, card in enumerate(har_supply):
                if card == chosen:
                    chosen_index = i
                    break
        self.send_action({"type": "har_supply_choice", "chosen_index": chosen_index})
    
    def resolve_rendezvous(self):
        self.send_action({"type": "confirm_rendezvous"})

    def pay_dark_alley(self, accepted):
        self.send_action({"type": "pay_dark_alley", "accepted": accepted})

    def move_again(self):
        self.send_action({"type": "move_again"})

    def battle_guard(self, guard_size):
        self.send_action({"type": "choose_guard", "guard_size": guard_size})

    def resolve_guard(self):
        self.send_action({"type": "fight_guard"})

    def roll_start(self):
        self.send_action({"type": "roll", "player_index": self.my_player_index})

    def resolve_roll(self):
        self.send_action({"type": "confirm_roll"})
    
    def resolve_reroll(self):
        self.send_action({"type": "reroll"})

    # ── Pub invite ──────────────────────────────────────────────────────
    def get_next_player(self, offset):
        players = self.game_state["players"]
        host = self.game_state["active_player"]

        return (host + offset) % len(players)
    
    def answer_pub_invite(self, joined):
        self.send_action({"type": "answer_pub_invite", "joined": joined})

    # ── Reclaim pirates ──────────────────────────────────────────────────────
    def try_reclaim_1(self, space):
        self.send_action({"type": "select_reclaim", "space_id": space["id"]})
    
    def try_reclaim_2(self, space):
        self.send_action({"type": "select_reclaim", "space_id": space["id"]})
    
    def resolve_reclaim(self):
        # Reclaim resolution is now entirely server-side; nothing to do locally.
        pass

    def reclaim_fail(self):
        # Server handles reclaim failure; nothing to do locally.
        pass

    ######################################################################
    # NETWORKING
    ######################################################################

    # ── State broadcast and serialisation ──────────────────────────────────────────────────────
    def broadcast_state(self):
        """Send game state to other players after any action."""
        if self.network and self.network.connected:
            serializable = self.get_serializable_state()
            self.network.send_state(serializable)

    def send_action(self, action: dict):
        """
        Send a player_action to the server.  The server mutates game_state
        and broadcasts state_updated back to all clients — we do NOT update
        local state here.  Falls back to the old local-rules path when
        there is no network connection (local/solo play).
        """
        if self.network and self.network.connected and self.room_id:
            action["room_id"] = self.room_id
            self.network.sio.emit("player_action", action)
        else:
            # ── Local / offline fallback (original behaviour) ──────────
            self._apply_action_locally(action)
            self.build_buttons()

    def _apply_action_locally(self, action):
        """Execute an action against the local rules object (offline fallback)."""
        t = action.get("type")
        gs = self.game_state
        if t == "move":
            result = self.rules.move_captain(gs, action["destination_id"])
            if result is not False and gs["phase"] == "confirm_move":
                self.rules.confirm_move(gs)
        elif t == "rest":
            self.rules.rest(gs)
        elif t == "go_on_board":
            self.rules.go_on_board(gs)
        elif t == "move_again":
            self.rules.move_again(gs)
        elif t == "avast":
            self.rules.avast_turn(gs)
        elif t == "roll":
            self.rules.roll(gs, action["player_index"])
        elif t == "confirm_roll":
            self.rules.resolve_roll(gs)
        elif t == "reroll":
            self.rules.resolve_reroll(gs)
        elif t == "confirm_rendezvous":
            self.rules.confirm_rendezvous(gs)
        elif t == "supply_choice":
            self.rules.resolve_supply_choice(gs, action.get("keep_card", False))
        elif t == "har_supply_choice":
            self.rules.resolve_har_supply(gs, action.get("chosen_index"))
        elif t == "answer_pub_invite":
            self.rules.answer_pub_invite(gs, action.get("joined", False))
        elif t == "pay_dark_alley":
            self.rules.pay_dark_alley(gs, action.get("accepted", False))
        elif t == "cancel_dark_alley":
            self.rules.cancel_dark_alley(gs)
        elif t == "resolve_dark_alley":
            self.rules.resolve_dark_alley(gs, action.get("exit_id"))
        elif t == "choose_guard":
            self.rules.choose_guard(gs, action.get("guard_size"))
        elif t == "fight_guard":
            self.rules.resolve_guard(gs)
        elif t == "select_reclaim":
            space_id = action.get("space_id")
            if gs["phase"] == "reclaim_1":
                self.rules.try_reclaim_1(gs, space_id)
            elif gs["phase"] == "reclaim_2":
                self.rules.try_reclaim_2(gs, space_id)

    def get_serializable_state(self):

        state = copy.copy(self.game_state)  # shallow copy
        # Remove pygame/numpy objects that can't be sent over the network
        state = {k: v for k, v in self.game_state.items() if k not in (
            "board",        # numpy array
            "space_lookup", # contains board_x/board_y but is rebuildable
            "spaces",       # same
            "dice",         # pygame surfaces
        )}
        return state

    # ── Menu navigation — host, join, rooms, active games ──────────────────────────────────────────────────────
    def host_game(self):

        self.game_state["menu"]["menu_level"] = "host_lobby"
        self.game_state["menu"]["multiplayer_mode"] = "host"
        self.game_state["menu"]["player_names"][0] = self.save_data.settings.get("player_name", "")

    def join_game(self):

        self.game_state["menu"]["menu_level"] = "join_lobby"
        self.game_state["menu"]["multiplayer_mode"] = "join"
        self.game_state["menu"]["player_names"][0] = self.save_data.settings.get("player_name", "")
        self.game_state["menu"]["lobby_error"] = None
        self.game_state["menu"]["open_rooms"] = [] ##### list of available rooms
        self.game_state["menu"]["rooms_loading"] = True
        self.fetch_open_rooms()

    def fetch_open_rooms(self):
        import threading, requests

        def _fetch():
            try:
                resp = requests.get(f"{SERVER_URL}/rooms", timeout=5)
                if resp.status_code == 200:
                    rooms = resp.json()  # expected: [{"room_id": "XXXX", "players": 1, "max_players": 4}, ...]
                else:
                    rooms = []
            except Exception:
                rooms = []
            self.game_state["menu"]["open_rooms"] = rooms
            self.game_state["menu"]["rooms_loading"] = False

        threading.Thread(target=_fetch, daemon=True).start()

    def refresh_rooms(self):

        self.game_state["menu"]["open_rooms"] = []
        self.game_state["menu"]["rooms_loading"] = True
        self.fetch_open_rooms()

    def view_active_games(self):
        self.game_state["menu"]["menu_level"] = "active_games"
        self.game_state["menu"]["active_games"] = []
        self.game_state["menu"]["games_loading"] = True
        self.fetch_active_games()
        self.build_buttons()

    def fetch_active_games(self):
        import threading, requests
        def _fetch():
            try:
                resp = requests.get(f"{SERVER_URL}/games", timeout=5)
                if resp.status_code == 200:
                    games = resp.json()
                else:
                    games = []
            except Exception:
                games = []
            self.game_state["menu"]["active_games"] = games
            self.game_state["menu"]["games_loading"] = False
        threading.Thread(target=_fetch, daemon=True).start()

    def rejoin_game(self, room_id):
        name = self.save_data.settings.get("player_name", "")
        if not self.network:
            self.network = network_manager()
            self.network.connect(SERVER_URL)
        self.network.sio.emit("rejoin_room", {"room_id": room_id, "name": name})

    # ── Connect and confirm ──────────────────────────────────────────────────────
    def confirm_host(self):
        self.network = network_manager()
        self.network.connect(SERVER_URL)
        
        host_name = self.game_state["menu"]["player_names"][0].strip() or "Player 1"
        self.network.create_room(host_name)
        self.my_player_index = 0
        self.game_state["menu"]["menu_level"] = "waiting_room"

    def confirm_join(self):
        room_code = self.game_state["menu"]["room_code_input"].strip().upper()
        server_ip = self.game_state["menu"]["server_ip_input"].strip()
    
        if not room_code:
            self.game_state["menu"]["lobby_error"] = "Please enter a room code"
            return

        self.network = network_manager()
        self.network.connect(SERVER_URL)
        player_name = self.game_state["menu"]["player_names"][0].strip() or "Player 2"
        self.network.join_room(room_code, player_name)
        self.my_player_index = None
        self.game_state["menu"]["menu_level"] = "waiting_room"

    # ── Poll network, apply state, handle web client actions ──────────────────────────────────────────────────────
    def poll_network(self):
        if not self.network:
            return
        
        # Handle disconnection
        if self.network.disconnected and not self.game_state.get("reconnecting"):
            self.game_state["reconnecting"] = True
            self.game_state["reconnect_attempts"] = 0
            print("[game] disconnected, attempting to reconnect...")

        # Auto retry reconnection
        if self.game_state.get("reconnecting"):
            self.game_state["reconnect_attempts"] = self.game_state.get("reconnect_attempts", 0) + 1
            if self.game_state["reconnect_attempts"] % 90 == 0:  # try every 3 seconds at 30fps
                try:
                    my_name = self.game_state["players"][self.my_player_index]["name"]
                    self.network.reconnect(SERVER_URL, self.room_id, my_name)
                except Exception:
                    pass

        # Clear reconnecting state on success
        if self.game_state.get("reconnecting") and not self.network.disconnected:
            self.game_state["reconnecting"] = False
            self.game_state["reconnect_attempts"] = 0
            print("[game] reconnected successfully")

        # Pick up room ID once server confirms creation or join
        if self.network.room_id and not self.room_id:
            self.room_id = self.network.room_id

        if self.network.player_index is not None and self.my_player_index is None:
            #self.my_player_index = self.network.player_index
            pass

        # Update lobby player list
        if self.network.lobby_players:
            self.game_state["menu"]["lobby_players"] = self.network.lobby_players

        # Handle failed join
        if self.network.join_error:
            self.game_state["menu"]["lobby_error"] = "Room not found"
            self.game_state["menu"]["menu_level"] = "join_lobby"
            self.network.join_error = False

        # Apply incoming game state from other players
        if self.network.incoming_state:
            prev_phase = self.game_state["phase"]
            self.apply_network_state(self.network.incoming_state)
            self.network.incoming_state = None
            if prev_phase != "game_over" and self.game_state["phase"] == "game_over":
                self.on_game_over()
        
        if self.network.incoming_action:
            action = self.network.incoming_action
            self.network.incoming_action = None
            web_players = self.game_state.get("web_players", [])
            active = self.game_state.get("active_player")
            if active in web_players:
                self.handle_network_action(action)

        while self.network.incoming_chat:
            message = self.network.incoming_chat.pop(0)
            self.chat_messages.append(message)
            self.chat_notification = True 
        self.network.new_chat_message = False

        if self.network.reconnected:
            self.network.reconnected = False
            self.room_id = self.network.room_id
            self.my_player_index = None
            if self.network.incoming_state:
                self.apply_network_state(self.network.incoming_state)
                self.network.incoming_state = None
            self.build_buttons()

        if self.network.join_error:
            self.network.join_error = False
            self.game_state["menu"]["lobby_error"] = getattr(self.network, "join_error_message", "Could not rejoin game")

    def apply_network_state(self, state):
        
        local_menu = self.game_state.get("menu")

        # legal_moves and occupied_paths are normalised below with int casting
        CLIENT_ONLY_KEYS = {"spaces", "space_lookup", "board", "legal_moves", "occupied_paths"}
        for key, value in state.items():
            if key not in CLIENT_ONLY_KEYS:
                self.game_state[key] = value

        if local_menu is not None:
            self.game_state["menu"] = local_menu

        ### Reset indices to use integers
        if "captain_space" in state:
            self.game_state["captain_space"] = int(state["captain_space"])
        if "active_player" in state:
            self.game_state["active_player"] = int(state["active_player"])
        if "captain_graph" in state:
            self.game_state["captain_graph"] = {
                int(k): v for k, v in state["captain_graph"].items()
            }

        if "legal_moves" in state:
            normalised = []
            for move in state["legal_moves"]:
                m = dict(move)
                if "destination" in m:
                    m["destination"] = int(m["destination"])
                if "path" in m:
                    m["path"] = [int(p) for p in m["path"]]
                normalised.append(m)
            self.game_state["legal_moves"] = normalised

        if "occupied_paths" in state:
            normalised_paths = []
            for path in state["occupied_paths"]:
                p = dict(path)
                if "path" in p:
                    p["path"] = [int(x) for x in p["path"]]
                if "start" in p:
                    p["start"] = int(p["start"])
                if "destination" in p:
                    p["destination"] = int(p["destination"])
                normalised_paths.append(p)
            self.game_state["occupied_paths"] = normalised_paths

        if "alley_lookup" in state:
            self.game_state["alley_lookup"] = {
                int(k): {
                    "captain": int(v["captain"]),
                    "path": v["path"],
                    "cost": v["cost"]
                }
                for k, v in state["alley_lookup"].items()
            }

        if "coin_lookup" in state:
            self.game_state["coin_lookup"] = {
                int(k): int(v) for k, v in state["coin_lookup"].items()
            }

        if "board_seed" in state:
            current_seed = self.game_state.get("board_seed")
            if state["board_seed"] != current_seed or self.game_state.get("board") is None:
                board, all_spaces = self.setup.create_board_from_seed(state["board_seed"])
                self.game_state["board"] = board
                self.game_state["spaces"] = all_spaces
                self.game_state["space_lookup"] = {s["id"]: s for s in all_spaces}
                self.raw_board = board
                self.rescale_board()

            # Assign my_player_index by matching name after shuffle
            if self.my_player_index is None:
                my_name = self.game_state["menu"]["player_names"][0]
                for i, player in enumerate(state["players"]):
                    if player["name"] == my_name:
                        self.my_player_index = i
                        break

        if "players" in state and self.network is not None:
            my_name = (
                self.save_data.settings.get("player_name", "").strip()
                or self.game_state["menu"]["player_names"][0]
            )
            if my_name:
                for i, player in enumerate(state["players"]):
                    if player["name"].strip().lower() == my_name.lower():
                        self.my_player_index = i
                        break

        self.build_buttons()