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
from aqt.utils import showInfo , askUser , showText , tooltip
import re
import unicodedata


# This should return a list of rhymes, each one being a single hanzi
def extract_ending(formatted_pinyin):
    letters = ""
    numbers = ""
    for c in formatted_pinyin:
        if c.isalpha():
            letters += c
        else:
            numbers += c
    endings = ["a", "ai", "ao", "an", "ang", "e", "ei", "n", "ong", "ng", "o", "ou", "i", "u"]
    exception_full_pinyin = ["yi", "wu", "yu", "ju", "qu", "xu", "lu", "nu"]
    for ending in endings:
        if letters.endswith(ending):
            if letters in exception_full_pinyin:
                return numbers
            else:
                return ending + numbers
    return "?"


# Dict[ending, Dict[initial, Set[hanzi]]
card_cache = None


def extract_initial(formatted_pinyin):
    ending = extract_ending(formatted_pinyin)
    return formatted_pinyin.replace(ending, "")


def extract_hanzi(card):
    note = card.note()
    for (name, value) in note.items():
        if "hanzi".lower() in name.lower() or "simplified".lower() in name.lower():
            return value
    return card.question()


# Update the card cache
def update_cache():
    global card_cache
    if card_cache is not None:
        return
    card_cache = dict()
    all_cards = [mw.col.get_card(cid) for cid in mw.col.find_cards("-is:due -is:new")]

    # Uncomment this to enable cross_deck hints:
    current_deck = mw.reviewer.card.current_deck_id()
    all_cards = [c for c in all_cards if c.current_deck_id() == current_deck]

    card_pinyin_tuples = [(c, extract_pinyin(c)) for c in all_cards]
    for c, p in card_pinyin_tuples:
        if len(p) > 0:
            formatted = format_pinyin(p)
            ending = extract_ending(formatted)
            initial = extract_initial(formatted)
            hanzi = extract_hanzi(c)
            if ending not in card_cache:
                card_cache[ending] = dict()
            if initial not in card_cache[ending]:
                card_cache[ending][initial] = set()
            card_cache[ending][initial].add(hanzi)


MAX_RHYMES = 5
MAX_RHYME_INITIALS = 4


# This should return a list of homophones, each one being a single hanzi
def get_homophones(formatted_pinyin):
    update_cache()
    initial = extract_initial(formatted_pinyin)
    ending = extract_ending(formatted_pinyin)
    if ending not in card_cache:
        card_cache[ending] = dict()
    if initial not in card_cache[ending]:
        card_cache[ending][initial] = set()
    return list(card_cache[ending][initial])


# List[List[initial, hanzi]]
def get_rhymes(formatted_pinyin):
    update_cache()
    initial = extract_initial(formatted_pinyin)
    ending = extract_ending(formatted_pinyin)
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
    pinyin = extract_pinyin(card)
    formatted_pinyin = format_pinyin(pinyin)
    ending = extract_ending(formatted_pinyin)
    homophones = get_homophones(formatted_pinyin)
    rhymes = get_rhymes(formatted_pinyin)
    label_string = ""
    # label_string += "Formatted Pinyin:\t" + formatted_pinyin + "\n"
    label_string += "HMM Final:\t" + ending + "\n"
    label_string += "Homophones:\t" + ', '.join(homophones) + "\n"
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
        initial = extract_initial(formatted_pinyin)
        ending = extract_ending(formatted_pinyin)
        if ending not in card_cache:
            card_cache[ending] = dict()
        if initial not in card_cache[ending]:
            card_cache[ending][initial] = set()
        card_cache[ending][initial].add(card)



gui_hooks.reviewer_did_show_answer.append(show_answer)
gui_hooks.reviewer_did_answer_card.append(remove_label)
