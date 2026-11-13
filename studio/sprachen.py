"""
Sprachen, in denen Watson hören, denken und sprechen kann.

code   = ISO-Kürzel (auch für Whisper, die Spracherkennung)
de/en  = Name der Sprache auf Deutsch / Englisch (für Menüs und für Watsons Anweisungen)
nativ  = Name in der Sprache selbst (für die Auswahl im Installer)
Die Stimme (Piper) sucht der Installer passend aus dem offiziellen Stimmen-Katalog.
"""

SPRACHEN = {
    "de": ("Deutsch", "German", "Deutsch"),
    "en": ("Englisch", "English", "English"),
    "nl": ("Niederländisch", "Dutch", "Nederlands"),
    "fr": ("Französisch", "French", "Français"),
    "es": ("Spanisch", "Spanish", "Español"),
    "it": ("Italienisch", "Italian", "Italiano"),
    "pt": ("Portugiesisch", "Portuguese", "Português"),
    "pl": ("Polnisch", "Polish", "Polski"),
    "cs": ("Tschechisch", "Czech", "Čeština"),
    "sk": ("Slowakisch", "Slovak", "Slovenčina"),
    "sl": ("Slowenisch", "Slovenian", "Slovenščina"),
    "hu": ("Ungarisch", "Hungarian", "Magyar"),
    "ro": ("Rumänisch", "Romanian", "Română"),
    "da": ("Dänisch", "Danish", "Dansk"),
    "sv": ("Schwedisch", "Swedish", "Svenska"),
    "no": ("Norwegisch", "Norwegian", "Norsk"),
    "fi": ("Finnisch", "Finnish", "Suomi"),
    "is": ("Isländisch", "Icelandic", "Íslenska"),
    "lb": ("Luxemburgisch", "Luxembourgish", "Lëtzebuergesch"),
    "el": ("Griechisch", "Greek", "Ελληνικά"),
    "tr": ("Türkisch", "Turkish", "Türkçe"),
    "ru": ("Russisch", "Russian", "Русский"),
    "uk": ("Ukrainisch", "Ukrainian", "Українська"),
    "sr": ("Serbisch", "Serbian", "Српски"),
    "ka": ("Georgisch", "Georgian", "ქართული"),
    "kk": ("Kasachisch", "Kazakh", "Қазақ"),
    "ar": ("Arabisch", "Arabic", "العربية"),
    "fa": ("Persisch", "Persian", "فارسی"),
    "hi": ("Hindi", "Hindi", "हिन्दी"),
    "ne": ("Nepalesisch", "Nepali", "नेपाली"),
    "vi": ("Vietnamesisch", "Vietnamese", "Tiếng Việt"),
    "zh": ("Chinesisch", "Chinese", "中文"),
    "sw": ("Suaheli", "Swahili", "Kiswahili"),
    "ca": ("Katalanisch", "Catalan", "Català"),
    "cy": ("Walisisch", "Welsh", "Cymraeg"),
    "lv": ("Lettisch", "Latvian", "Latviešu"),
}


def name(code, auf="de"):
    """Name einer Sprache auf Deutsch (auf='de') oder Englisch (auf='en')."""
    s = SPRACHEN.get((code or "de").lower())
    if not s:
        return code or "Deutsch"
    return s[1] if auf == "en" else s[0]


def liste():
    """Für Auswahllisten: [{code, de, en, nativ}], nach deutschem Namen sortiert."""
    return sorted(({"code": k, "de": v[0], "en": v[1], "nativ": v[2]} for k, v in SPRACHEN.items()),
                  key=lambda x: x["de"])
