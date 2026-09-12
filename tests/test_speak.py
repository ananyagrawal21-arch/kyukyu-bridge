import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from speak import speech_form
from speak import room_to_kana


# def test_hyphen_between_digits_becomes_no():
#     assert speech_form("24-5") == "24の5"


# def test_long_vowel_in_building_name_is_untouched():
#     assert speech_form("〇〇マンション") == "〇〇マンション"

def test_room_to_kana():
    assert room_to_kana("101号室") == "イチマルイチ"