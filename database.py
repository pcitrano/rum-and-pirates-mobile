import json
import cv2
import os

class database:
    def __init__(self, board_path, card_path, image_path, ui_path):
        self.board_path = board_path
        self.card_path = card_path
        self.image_path = image_path
        self.ui_path = ui_path

        self.cards = self.load_cards()
        self.tiles = self.load_all_tiles()
        self.card_images = self.load_card_images()
        self.dice_images = self.load_die_images()
        self.dice = self.load_die_details()
        self.ui_images = self.load_ui_images()

    def load_tiles(self,tile_number):
        
        json_path = os.path.join(self.board_path, f"Tile{tile_number}.json")
        with open(json_path, "r") as file:
            properties = json.load(file)

        image_path = os.path.join(self.image_path, f"Tile {tile_number}.jpg")
        image = cv2.imread(image_path) 

        return {"image": image, "properties": properties}
    
    def load_all_tiles(self):
        tiles = {}
        for tile_number in [1,2,3,4,5,6,7,8,9]:
                tiles[tile_number] = self.load_tiles(tile_number)

        return tiles

    def load_cards(self):
        json_path = os.path.join(self.card_path, "cards.json")
        with open(json_path, "r") as file:
            cards = json.load(file)
    
        return cards

    def load_card_images(self):
        image_folder = self.image_path
        card_images = {}

        for filename in os.listdir(image_folder):
            # Skip board tiles
            if filename.startswith("Tile") or filename.startswith("Die"):
                continue

            # Only load image files
            if not filename.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                continue

            full_path = os.path.join(image_folder,filename)
            image = cv2.imread(full_path)

            if image is None:
                print(f"Failed to load: {filename}")
                continue

            card_images[filename] = image

        return card_images
    
    def load_die_images(self): 
        image_folder = self.image_path
        dice = {}

        for filename in os.listdir(image_folder):

            if filename.startswith("Die"):
                full_path = os.path.join(image_folder,filename)
                image = cv2.imread(full_path)

                if image is None:
                    print(f"Failed to load: {filename}")
                    continue

                dice[filename] = image
            
            else:
                continue

        return dice
    
    def load_die_details(self):
        dice = {}
        for die_number in [1,2,3,4,5,6]:
            dice[die_number] = {"value": die_number, "image": f"Die {die_number}.png"}
        return dice
    
    def load_ui_images(self):
        image_folder = self.ui_path
        ui_images = {}
        ui_images["menu_animation"] = []
        
        for filename in os.listdir(image_folder):
            full_path = os.path.join(image_folder, filename)
        
            # Check if it's a file before attempting to read it
            if os.path.isfile(full_path):
                image = cv2.imread(full_path, cv2.IMREAD_UNCHANGED)
                ui_images[filename] = image

        animation_folder = os.path.join(self.ui_path, "MenuBackground")

        if os.path.isdir(animation_folder):
            for filename in sorted(os.listdir(animation_folder)):
                if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                    full_path = os.path.join(animation_folder, filename)
                    image = cv2.imread(full_path)
                    if image is not None:
                        ui_images["menu_animation"].append(image)

        return ui_images