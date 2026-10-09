"""The words the voice needs for a number, a unit or a date inside a native-language answer.

The answer text carries Latin units and digits inside native sentences ("30-35 m", "12 km/h",
"2 Oct 2026", "343°", "40%"), because the translator is told to leave numbers and units alone (see
`language._PROTECTED_TERM`). Read as written, the native voices spell a lone "m" as two letters
("ಇ ಎಂ"), drop the word between the two numbers of a range ("30-35" came back as "30 35"), and drop a
Latin month ("2 Oct 2026" lost "Oct"). `voice.speakable` rewrites those pieces with the words below,
for the SPEAKER only; the shown text never changes.

Every word here is Bhashini's own translation of an English test sentence ("The depth is from 30 to 35
metres.", "Wind is 12 kilometres per hour.", "The advisory was valid on 2 October 2026.") run on
2026-10-08, with the base form of an inflected word (Telugu "మీటర్ల" -> "మీటర్"). They were not written
from memory. Kannada and Hindi were read by the user; the other languages should be read by a native
speaker before they are relied on. To correct a word, edit it here: nothing else holds a copy.

Keys per language:
  to      the word between the two numbers of a range ("30 to 35")
  m, km, nm, deg, pct   the unit after a number
  kmh, ms   a template with {n} for "N km/h" and "N m/s": the "per hour" phrase goes before or after
            the number according to the language
  plus    the word for "+" in a phone number
  months  January to December
"""
from __future__ import annotations

from typing import TypedDict


class Lexicon(TypedDict):
    to: str
    m: str
    km: str
    nm: str
    deg: str
    pct: str
    kmh: str
    ms: str
    plus: str
    months: tuple[str, ...]


LEXICON: dict[str, Lexicon] = {
    "kn": {
        "to": "ರಿಂದ", "m": "ಮೀಟರ್", "km": "ಕಿಲೋಮೀಟರ್", "nm": "ನಾಟಿಕಲ್ ಮೈಲಿ", "deg": "ಡಿಗ್ರಿ", "pct": "ಪ್ರತಿಶತ",
        "kmh": "ಪ್ರತಿ ಗಂಟೆಗೆ {n} ಕಿಲೋಮೀಟರ್", "ms": "ಪ್ರತಿ ಸೆಕೆಂಡಿಗೆ {n} ಮೀಟರ್", "plus": "ಪ್ಲಸ್",  # VOICE-10: rates in the order the user chose by ear, 2026-10-10
        "months": ("ಜನವರಿ", "ಫೆಬ್ರವರಿ", "ಮಾರ್ಚ್", "ಏಪ್ರಿಲ್", "ಮೇ", "ಜೂನ್", "ಜುಲೈ", "ಆಗಸ್ಟ್", "ಸೆಪ್ಟೆಂಬರ್", "ಅಕ್ಟೋಬರ್", "ನವೆಂಬರ್", "ಡಿಸೆಂಬರ್"),
    },
    "hi": {
        "to": "से", "m": "मीटर", "km": "किलोमीटर", "nm": "समुद्री मील", "deg": "डिग्री", "pct": "प्रतिशत",
        "kmh": "{n} किलोमीटर प्रति घंटा", "ms": "{n} मीटर प्रति सेकंड", "plus": "प्लस",
        "months": ("जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"),
    },
    "mr": {
        "to": "ते", "m": "मीटर", "km": "किलोमीटर", "nm": "सागरी मैल", "deg": "अंश", "pct": "टक्के",
        "kmh": "ताशी {n} किलोमीटर", "ms": "{n} मीटर प्रति सेकंद", "plus": "प्लस",
        "months": ("जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"),
    },
    "ta": {
        "to": "முதல்", "m": "மீட்டர்", "km": "கிலோமீட்டர்", "nm": "கடல் மைல்", "deg": "டிகிரி", "pct": "சதவீதம்",
        "kmh": "மணிக்கு {n} கிலோமீட்டர்", "ms": "வினாடிக்கு {n} மீட்டர்", "plus": "பிளஸ்",
        "months": ("ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்"),
    },
    "te": {
        "to": "నుండి", "m": "మీటర్", "km": "కిలోమీటర్", "nm": "నాటికల్ మైలు", "deg": "డిగ్రీ", "pct": "శాతం",
        "kmh": "గంటకు {n} కిలోమీటర్", "ms": "సెకనుకు {n} మీటర్", "plus": "ప్లస్",
        "months": ("జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబరు", "నవంబర్", "డిసెంబర్"),
    },
    "ml": {
        "to": "മുതൽ", "m": "മീറ്റർ", "km": "കിലോമീറ്റർ", "nm": "നോട്ടിക്കൽ മൈൽ", "deg": "ഡിഗ്രി", "pct": "ശതമാനം",
        "kmh": "മണിക്കൂറിൽ {n} കിലോമീറ്റർ", "ms": "സെക്കൻഡിൽ {n} മീറ്റർ", "plus": "പ്ലസ്",
        "months": ("ജനുവരി", "ഫെബ്രുവരി", "മാർച്ച്", "ഏപ്രിൽ", "മെയ്", "ജൂൺ", "ജൂലൈ", "ഓഗസ്റ്റ്", "സെപ്റ്റംബർ", "ഒക്ടോബർ", "നവംബർ", "ഡിസംബർ"),
    },
    "bn": {
        "to": "থেকে", "m": "মিটার", "km": "কিলোমিটার", "nm": "নটিক্যাল মাইল", "deg": "ডিগ্রি", "pct": "শতাংশ",
        "kmh": "ঘন্টায় {n} কিলোমিটার", "ms": "প্রতি সেকেন্ডে {n} মিটার", "plus": "প্লাস",
        "months": ("জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"),
    },
    "gu": {
        "to": "થી", "m": "મીટર", "km": "કિલોમીટર", "nm": "નોટિકલ માઇલ", "deg": "ડિગ્રી", "pct": "ટકા",
        "kmh": "{n} કિલોમીટર પ્રતિ કલાક", "ms": "{n} મીટર પ્રતિ સેકન્ડ", "plus": "પ્લસ",
        "months": ("જાન્યુઆરી", "ફેબ્રુઆરી", "માર્ચ", "એપ્રિલ", "મે", "જૂન", "જુલાઈ", "ઓગસ્ટ", "સપ્ટેમ્બર", "ઓક્ટોબર", "નવેમ્બર", "ડિસેમ્બર"),
    },
    "or": {
        "to": "ରୁ", "m": "ମିଟର", "km": "କିଲୋମିଟର", "nm": "ନଟିକାଲ ମାଇଲ", "deg": "ଡିଗ୍ରୀ", "pct": "ପ୍ରତିଶତ",
        "kmh": "ଘଣ୍ଟାପ୍ରତି {n} କିଲୋମିଟର", "ms": "ସେକେଣ୍ଡ ପ୍ରତି {n} ମିଟର", "plus": "ପ୍ଲସ୍",
        "months": ("ଜାନୁଆରୀ", "ଫେବୃଆରୀ", "ମାର୍ଚ୍ଚ", "ଏପ୍ରିଲ", "ମେ", "ଜୁନ୍", "ଜୁଲାଇ", "ଅଗଷ୍ଟ", "ସେପ୍ଟେମ୍ବର", "ଅକ୍ଟୋବର", "ନଭେମ୍ବର", "ଡିସେମ୍ବର"),
    },
}

# The Latin spellings of a month that an answer can carry (the translator writes "2 Oct 2026" itself).
MONTH_ALIASES: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


# ---------------------------------------------------------------------------------------------------------
# English voice: single words it gets wrong (FIX-VOICE-3, 2026-10-09)
#
# Each entry was found by reading the voice back (Bhashini male English voice, then Whisper) and, for the
# first four, by the user's ear. A spelling is kept only when it read back right in all four of four test
# sentences of real answers (`%TEMP%\respell_sweep.py`; the plain word's score is beside it). The same
# method as "zones": try spellings, read back, keep what works. `scripts/voice_check.py` finds the NEXT
# word from the kept corpus; add it here with its evidence.
ENGLISH_RESPELLING: dict[str, str] = {
    # "fishing ones", "nearest sun", "danger wands": the z is dropped. plain 5 of 8 sentences, "zohn(z)" 7 of 8.
    "zone": "zohn",
    "zones": "zohnz",
    # "wave hate". plain 3 of 4; "hite" 4 of 4 (hyte, hight, highte also 4 of 4).
    "height": "hite",
    # "really", "rough like", "fun". plain 0 of 4; "ruffley" 4 of 4.
    "roughly": "ruffley",
    # "relayed", "rallied". plain 2 of 4; "re-lied" 4 of 4 (relide, ree-lied also 4 of 4).
    "relied": "re-lied",
    # "tide gorge" (2 of 30 corpus answers). plain 0 of 4; "gage" 4 of 4 (gayge also 4 of 4).
    "gauge": "gage",
    # The user's choice by ear (files M1-M4, 2026-10-09): "metres" is not what anyone says; "meeters" is.
    # A unit written "m" and "m/s" is turned into "metres" earlier in `speakable`, and a model may type either
    # spelling, so all four forms end up here. "kilometres" is a different word and is left alone.
    "metres": "meeters",
    "meters": "meeters",
    "metre": "meeter",
    "meter": "meeter",
    # Same for the compound (user's choice by ear, K2, 2026-10-09). "geometry" and "parametres" are other words.
    "kilometres": "kilomeeters",
    "kilometers": "kilomeeters",
    "kilometre": "kilomeeter",
    "kilometer": "kilomeeter",
}

# Acronyms: spelled so the voice says them. MPA was heard "MPE" and "mp-ary" in every spelling of the
# letters tried (plain, "M P A", "em pee ay", "M-P-A": 2 of 4 each); the words it stands for read right.
ENGLISH_ACRONYMS: dict[str, str] = {
    "MRCC": "M R C C",
    "VHF": "V H F",
    "IMBL": "eye em bee el",  # heard "AMBL" and "emerald" as letters
    "DAT-SG": "D A T S G",
    "MPA": "marine protected area",
    # "BFZ", "bf that": plain 3 of 4 read right; "pee ef zee" 4 of 4 (P F Z 2, pee eff zed 3). Read-back only: the
    # user has not confirmed this one by ear.
    "PFZ": "pee ef zee",
}

# The sixteen compass points, in full. "NNW" is "north north-west" (FIX-VOICE-4). The translator turns
# "NNW" into "north-west" in most languages (a 22 degree error) or into letters ("एन. एन. डब्ल्यू."), so the
# token is kept out of translation (language._PROTECTED_TERM) and spoken from here.
COMPASS_ENGLISH: dict[str, str] = {
    "N": "north", "NNE": "north north-east", "NE": "north-east", "ENE": "east north-east",
    "E": "east", "ESE": "east south-east", "SE": "south-east", "SSE": "south south-east",
    "S": "south", "SSW": "south south-west", "SW": "south-west", "WSW": "west south-west",
    "W": "west", "WNW": "west north-west", "NW": "north-west", "NNW": "north north-west",
}

# north, east, south, west in each language: Bhashini's own translation of "The wind is from the north." and
# the three others, 2026-10-09. A native speaker should confirm (Kannada and Hindi can be checked by the user).
COMPASS_NATIVE: dict[str, dict[str, str]] = {
    "kn": {"N": "ಉತ್ತರ", "E": "ಪೂರ್ವ", "S": "ದಕ್ಷಿಣ", "W": "ಪಶ್ಚಿಮ"},
    "hi": {"N": "उत्तर", "E": "पूर्व", "S": "दक्षिण", "W": "पश्चिम"},
    "mr": {"N": "उत्तर", "E": "पूर्व", "S": "दक्षिण", "W": "पश्चिम"},
    "ta": {"N": "வடக்கு", "E": "கிழக்கு", "S": "தெற்கு", "W": "மேற்கு"},
    "te": {"N": "ఉత్తరం", "E": "తూర్పు", "S": "దక్షిణం", "W": "పశ్చిమం"},
    "ml": {"N": "വടക്ക്", "E": "കിഴക്ക്", "S": "തെക്ക്", "W": "പടിഞ്ഞാറ്"},
    "bn": {"N": "উত্তর", "E": "পূর্ব", "S": "দক্ষিণ", "W": "পশ্চিম"},
    "gu": {"N": "ઉત્તર", "E": "પૂર્વ", "S": "દક્ષિણ", "W": "પશ્ચિમ"},
    "or": {"N": "ଉତ୍ତର", "E": "ପୂର୍ବ", "S": "ଦକ୍ଷିଣ", "W": "ପଶ୍ଚିମ"},
}

# The multi-letter points, longest first, as one regular expression (the single letters N, E, S and W are
# only a direction after a number: "12.9894 N").
COMPASS_MULTI = ("NNE", "ENE", "ESE", "SSE", "SSW", "WSW", "WNW", "NNW", "NE", "SE", "SW", "NW")
