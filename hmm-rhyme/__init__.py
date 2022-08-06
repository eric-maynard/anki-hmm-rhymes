from aqt.reviewer import Reviewer
from anki.hooks import addHook, wrap
from aqt import gui_hooks

import aqt
from aqt.reviewer import Reviewer
from aqt.qt import *
from aqt import mw
from anki.hooks import addHook, wrap
import shutil , os , glob , random , sys
from bs4 import BeautifulSoup
CONFIG = mw.addonManager.getConfig(__name__)
import unicodedata


class CardData:
    def __init__(self, hanzi, pinyin, initial, ending):
        self.hanzi = hanzi
        self.pinyin = pinyin
        self.initial = initial
        self.ending = ending


# Convert a card to [CardData]
def parse_card(card):
    hanzi = extract_hanzi(card)
    results = []
    for h in hanzi:
        pinyin = None
        if h in hanzi_pinyin_cache:
            pinyin = hanzi_pinyin_cache[h]
        elif len(hanzi) == 1:
            pinyin = extract_pinyin(card)
        if pinyin is not None:
            initial, ending = extract_initial_ending(pinyin)
            if ending != "?":
                results.append(CardData(h, pinyin, initial, ending))
    return results


# pinyin -> (initial, ending)
def extract_initial_ending(formatted_pinyin):
    # TODO fix some HMM endings, e.g. jiu = ou
    # todo rewrite this method
    letters = ""
    numbers = ""
    for c in formatted_pinyin:
        if c.isalpha():
            letters += c
        else:
            numbers += c
    endings = ["a", "ai", "ao", "an", "ang", "e", "ei", "n", "ong", "ng", "o", "ou", "i"]
    exception_full_pinyin = ["yi", "wu", "yu", "ju", "qu", "xu", "lu", "nu"]
    for ending in endings:
        if letters.endswith(ending):
            if letters in exception_full_pinyin:
                return letters, numbers
            else:
                return formatted_pinyin.replace(ending + numbers, ""), ending + numbers
    return "?"


# Dict[ending, Dict[initial, Set[hanzi]]
card_cache = None
hanzi_pinyin_cache = dict()


def extract_hanzi(card):
    note = card.note()
    for (name, value) in note.items():
        if "hanzi".lower() in name.lower() or "simplified".lower() in name.lower():
            return value
    return card.question()


# Update the card cache
def update_cache():
    global card_cache
    global hanzi_pinyin_cache
    if card_cache is not None:
        return

    all_cards = [mw.col.get_card(cid) for cid in mw.col.find_cards("-is:due -is:new")]

    # Comment this to enable cross_deck hints:
    # current_deck = mw.reviewer.card.current_deck_id()
    # all_cards = [c for c in all_cards if c.current_deck_id() == current_deck]

    # First collect hanzi -> pinyin cache
    parsed_cards_2d = [parse_card(c) for c in all_cards]
    for c in [item for sublist in parsed_cards_2d for item in sublist]:
        if len(c.hanzi) == 1:
            if c.hanzi not in hanzi_pinyin_cache:
                hanzi_pinyin_cache[c.hanzi] = c.pinyin

    # Then build the homophone cache:
    card_cache = dict()
    parsed_cards_2d = [parse_card(c) for c in all_cards]
    for c in [item for sublist in parsed_cards_2d for item in sublist]:
        if c.ending not in card_cache:
            card_cache[c.ending] = dict()
        if c.initial not in card_cache[c.ending]:
            card_cache[c.ending][c.initial] = set()
        card_cache[c.ending][c.initial].add(c.hanzi)


MAX_RHYMES = 5
MAX_RHYME_INITIALS = 4


# This should return a list of homophones, each one being a single hanzi
def get_homophones(formatted_pinyin, exclude=""):
    update_cache()
    initial, ending = extract_initial_ending(formatted_pinyin)
    if ending not in card_cache:
        card_cache[ending] = dict()
    if initial not in card_cache[ending]:
        card_cache[ending][initial] = set()
    return [c for c in card_cache[ending][initial] if c != exclude]


# List[List[initial, hanzi]]
def get_rhymes(formatted_pinyin):
    update_cache()
    initial, ending = extract_initial_ending(formatted_pinyin)
    sampled_rhyme_lists = list(card_cache[ending].items())[:MAX_RHYME_INITIALS]
    return [(i, list(hanzi)[:MAX_RHYMES]) for i, hanzi in sampled_rhyme_lists if i != initial]


# Convert from tone marks to number format, e.g. guan -> gua4n
def to_tone_number(s):
    table = {0x304: ord('1'), 0x301: ord('2'), 0x30c: ord('3'),
             0x300: ord('4')}
    return unicodedata.normalize('NFD', s).translate(table)


def format_pinyin(raw_pinyin):
    semi_formatted = to_tone_number(raw_pinyin)
    letters = ""
    numbers = ""
    for c in semi_formatted:
        if c.isalpha():
            letters += c
        else:
            numbers += c
    if numbers == "":
        numbers = "5"
    return letters + numbers


# For a card object, extract the first pinyin answer
def extract_pinyin(card):
    l = extract_pinyin_list(card)
    answer = ""
    reading = False
    skipping = 0
    for c in l:
        if c == "<":
            skipping += 1
        elif c == ">":
            skipping -= 1
        elif skipping == 0:
            if c.isalnum() and not reading:
                reading = True
            elif not c.isalnum() and reading:
                return answer
            if reading:
                answer += c
    return answer


# For a card object, extract the full pinyin answer
def extract_pinyin_list(card):
    note = card.note()
    for (name, value) in note.items():
        if "pinyin".lower() in name.lower():
            return value
    return ""


label: QLabel = None

def apply_label(label_text):
    global label
    if label is None:
        aw = mw.app.activeWindow() or mw
        label = QLabel(aw, )
    parent = mw.web
    label.setText(label_text)
    label.setFont(QFont("Arial", 18))
    label.resize(400, 250)
    center = (parent.frameGeometry().center() - label.frameGeometry().center())
    bottom_height = (parent.frameGeometry().height() - label.frameGeometry().height())
    label.move(center.x(), bottom_height)
    label.show()


def get_label(card):
    card_data = parse_card(card)
    label_string = ""
    for c in card_data:
        homophones = get_homophones(c.pinyin, c.hanzi)
        rhymes = get_rhymes(c.pinyin)
        label_string += f"{c.hanzi} ({c.pinyin} -> {c.initial}/{c.ending}):\n"
        label_string += f"Homophones: {', '.join(homophones)}\n"
        for i, h in rhymes:
            label_string += f"Rhymes ({i}):\t" + ', '.join(h) + "\n"
    return label_string


def show_answer(card):
    label_text = get_label(card)
    apply_label(label_text)


def remove_label(reviewer, card, ease):
    global label
    if label is not None:
        label.hide()
        label.deleteLater()
        label = None
    if ease != 1:
        update_cache()
        pinyin = extract_pinyin(card)
        formatted_pinyin = format_pinyin(pinyin)
        initial, ending = extract_initial_ending(formatted_pinyin)
        if ending not in card_cache:
            card_cache[ending] = dict()
        if initial not in card_cache[ending]:
            card_cache[ending][initial] = set()
        card_cache[ending][initial].add(extract_hanzi(card))



gui_hooks.reviewer_did_show_answer.append(show_answer)
gui_hooks.reviewer_did_answer_card.append(remove_label)
