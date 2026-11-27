"""``rivex.constants.otp`` — OTP alphabets, lengths, passphrase words, and format regexes."""

from __future__ import annotations

import re
from typing import Final, Sequence, Tuple

from rivex.constants.abstraction import IConstant


def otp_alphabet_regex(alphabet: str, length: int) -> str:
    """Return a full-match regex for ``length`` characters from ``alphabet``."""
    return rf"^[{re.escape(alphabet)}]{{{length}}}$"


def otp_passphrase_regex(
    words: Sequence[str],
    word_count: int,
    separator: str,
) -> str:
    """Return a full-match regex for ``word_count`` words joined by ``separator``."""
    word = f"(?:{'|'.join(re.escape(item) for item in words)})"
    if word_count == 1:
        return rf"^{word}$"
    sep = re.escape(separator)
    return rf"^{word}(?:{sep}{word}){{{word_count - 1}}}$"


class OTP(IConstant):
    """One-time password generation constants.

    Carries both the alphabets/lengths (used by the
    :class:`rivex.utilities.otp.IOTPUtility` subclasses) and a much larger
    passphrase word list than the utility's built-in default, plus the
    pre-compiled regex strings used to validate OTP values at the
    application layer.
    """

    DIGIT: Final[str] = "digit"
    ALPHANUMERIC: Final[str] = "alphanumeric"
    ALPHABETIC: Final[str] = "alphabetic"
    HEX: Final[str] = "hex"
    PASSPHRASE: Final[str] = "passphrase"

    DIGIT_ALPHABET: Final[str] = "0123456789"
    ALPHABETIC_ALPHABET: Final[str] = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    ALPHANUMERIC_ALPHABET: Final[str] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    HEX_ALPHABET: Final[str] = "0123456789ABCDEF"

    DIGIT_LENGTH: Final[int] = 6
    ALPHANUMERIC_LENGTH: Final[int] = 8
    ALPHABETIC_LENGTH: Final[int] = 8
    HEX_LENGTH: Final[int] = 8
    PASSPHRASE_WORD_COUNT: Final[int] = 4
    PASSPHRASE_SEPARATOR: Final[str] = "-"

    DIGIT_REGEX: Final[str] = otp_alphabet_regex(DIGIT_ALPHABET, DIGIT_LENGTH)
    ALPHANUMERIC_REGEX: Final[str] = otp_alphabet_regex(
        ALPHANUMERIC_ALPHABET, ALPHANUMERIC_LENGTH
    )
    ALPHABETIC_REGEX: Final[str] = otp_alphabet_regex(ALPHABETIC_ALPHABET, ALPHABETIC_LENGTH)
    HEX_REGEX: Final[str] = otp_alphabet_regex(HEX_ALPHABET, HEX_LENGTH)

    WORDS: Final[Tuple[str, ...]] = (
        "able", "acid", "acre", "act", "add", "age", "ago", "aid",
        "aim", "air", "ale", "all", "alp", "amp", "and", "ant",
        "any", "ape", "apt", "arc", "ark", "arm", "art", "ash",
        "ask", "asp", "ate", "auk", "awe", "axe", "bad", "bag",
        "ban", "bar", "bat", "bay", "bed", "bee", "beg", "bet",
        "bid", "big", "bin", "bit", "boa", "bob", "bog", "bow",
        "box", "boy", "bra", "bud", "bug", "bum", "bun", "bus",
        "but", "buy", "cab", "cad", "cam", "can", "cap", "car",
        "cat", "caw", "cob", "cod", "cog", "con", "cop", "cot",
        "cow", "coy", "cry", "cub", "cud", "cue", "cup", "cur",
        "cut", "dab", "dad", "dam", "day", "den", "dew", "did",
        "die", "dig", "dim", "dip", "doe", "dog", "dot", "dry",
        "dub", "dud", "due", "dug", "dun", "duo", "dye", "ear",
        "eat", "ebb", "eel", "egg", "ego", "elf", "elk", "elm",
        "emu", "end", "eon", "era", "eve", "ewe", "eye", "fad",
        "fan", "far", "fat", "fax", "fed", "few", "fib", "fig",
        "fin", "fir", "fit", "fix", "fly", "foe", "fog", "for",
        "fox", "fry", "fun", "fur", "gab", "gag", "gap", "gas",
        "gel", "gem", "get", "gig", "gin", "gnu", "gob", "god",
        "got", "gum", "gun", "gut", "guy", "gym", "had", "hag",
        "ham", "has", "hat", "hay", "hem", "hen", "her", "hew",
        "hex", "hid", "him", "hip", "his", "hit", "hob", "hod",
        "hog", "hop", "hot", "how", "hub", "hue", "hug", "hum",
        "hut", "ice", "icy", "ill", "imp", "ink", "inn", "ion",
        "irk", "ivy", "jab", "jag", "jam", "jar", "jaw", "jay",
        "jet", "jig", "job", "jog", "jot", "joy", "jug", "keg",
        "ken", "key", "kid", "kin", "kit", "lab", "lad", "lag",
        "lap", "law", "lax", "lay", "lea", "led", "leg", "let",
        "lid", "lie", "lip", "lit", "lob", "log", "lot", "low",
        "lug", "lye", "mad", "man", "map", "mat", "maw", "may",
        "men", "met", "mew", "mid", "mix", "mob", "mod", "mop",
        "mow", "mud", "mug", "mum", "nab", "nag", "nap", "net",
        "new", "nil", "nip", "nit", "nix", "nob", "nod", "nor",
        "not", "now", "nub", "nun", "nut", "oak", "oar", "oat",
        "odd", "ode", "off", "oft", "ohm", "oil", "old", "one",
        "opt", "orb", "ore", "our", "out", "ova", "owe", "owl",
        "own", "pad", "pal", "pan", "pap", "par", "pat", "paw",
        "pay", "pea", "peg", "pen", "pep", "per", "pet", "pew",
        "pic", "pie", "pig", "pin", "pit", "ply", "pod", "pop",
        "pot", "pow", "pro", "pry", "pub", "pug", "pun", "pup",
        "pus", "put", "rag", "ram", "ran", "rap", "rat", "raw",
        "ray", "red", "ref", "rep", "rib", "rid", "rig", "rim",
        "rip", "rob", "rod", "roe", "rot", "row", "rub", "rug",
        "rum", "run", "rut", "rye", "sac", "sad", "sag", "sap",
        "sat", "saw", "sax", "say", "sea", "see", "set", "sew",
        "she", "shy", "sip", "sir", "sis", "sit", "six", "ski",
        "sky", "sly", "sob", "sod", "son", "sop", "sot", "sow",
        "soy", "spa", "spy", "sub", "sud", "sue", "sum", "sun",
        "sup", "tab", "tad", "tag", "tan", "tap", "tar", "tat",
        "tax", "tea", "ten", "the", "thy", "tic", "tie", "tin",
        "tip", "toe", "tog", "ton", "too", "top", "tot", "tow",
        "toy", "try", "tub", "tug", "tun", "two", "ugh", "ump",
        "urn", "use", "van", "vat", "vet", "vex", "via", "vie",
        "vow", "wad", "wag", "war", "was", "wax", "way", "web",
        "wed", "wee", "wet", "who", "why", "wig", "win", "wit",
        "woe", "wok", "won", "woo", "wow", "wry", "yak", "yam",
        "yap", "yaw", "yea", "yen", "yes", "yet", "yew", "yip",
        "you", "zap", "zen", "zig", "zip", "zit",
    )

    PASSPHRASE_REGEX: Final[str] = otp_passphrase_regex(
        WORDS, PASSPHRASE_WORD_COUNT, PASSPHRASE_SEPARATOR
    )

    @classmethod
    def alphabet_regex(cls, alphabet: str, length: int) -> str:
        """Return a full-match regex for ``length`` characters from ``alphabet``."""
        return otp_alphabet_regex(alphabet, length)

    @classmethod
    def passphrase_regex(
        cls,
        word_count: int | None = None,
        separator: str | None = None,
    ) -> str:
        """Return a full-match regex for a passphrase OTP."""
        return otp_passphrase_regex(
            cls.WORDS,
            cls.PASSPHRASE_WORD_COUNT if word_count is None else word_count,
            cls.PASSPHRASE_SEPARATOR if separator is None else separator,
        )

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "OTP"


__all__ = ["OTP", "otp_alphabet_regex", "otp_passphrase_regex"]
