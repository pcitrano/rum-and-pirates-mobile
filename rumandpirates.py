import sys
import os
from database import database
from pc_game_setup import game_setup
from game_ui import game_ui
from save_data import save_data

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.abspath(__file__))

base = get_base_path()
asset_base =  os.path.join(base, "thin_client_assets")

database = database(
    os.path.join(asset_base, "Tile and Card Data"),
    os.path.join(asset_base, "Tile and Card Data"),
    os.path.join(asset_base, "Gameplay Images"),
    os.path.join(asset_base, "UI Images")
)

game = game_setup(database, start_in_menu=True)
save_data = save_data()

ui = game_ui(
    game.game_state,
    rules=None,
    setup=game,
    save_data=save_data,
    card_images=database.card_images,
    dice_images=database.dice_images,
    ui_images=database.ui_images,
    font_path=os.path.join(asset_base, "Fonts", "Pieces of Eight.ttf"),
    base_path=base
)
ui.run()