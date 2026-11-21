"""Claude (die Werkstatt) trägt sein Urteil zu einem Reparatur-Vorschlag von Watsons Wartungs-Team ein.

Seit 22.11.2026: Vorschläge gehen erst an den Besitzer, wenn ein Oberprüfer sie mit dem ECHTEN Code geprüft hat –
ChatGPT (falls der Besitzer seinen Plan verbunden hat) oder sonst Claude in der Werkstatt.

    studio\\.venv\\Scripts\\python.exe werkzeuge\\werkstatt_urteil.py              -> offene Vorschläge zeigen
    studio\\.venv\\Scripts\\python.exe werkzeuge\\werkstatt_urteil.py 3 nein "Grund"
    studio\\.venv\\Scripts\\python.exe werkzeuge\\werkstatt_urteil.py 3 ja "Grund"

NEIN lehnt den Vorschlag ab (am Programm ändert sich nichts). JA heißt nur: Der Besitzer bekommt ihn zur
Entscheidung vorgelegt – angewendet wird weiterhin nur mit seinem OK.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "studio"))
import wartung  # noqa: E402


def main(argv):
    if len(argv) < 2:
        offen = [v for v in wartung._laden()["vorschlaege"] if v["status"] == "vorgeschlagen"]
        if not offen:
            print("Keine offenen Reparatur-Vorschläge.")
        for v in offen:
            ob = v.get("oberpruefung") or {}
            stand = "wartet auf Werkstatt" if ob.get("wartet") and ob.get("urteil") is None else \
                ("JA von " + ob["wer"]) if ob.get("urteil") else "noch nicht beim Oberprüfer"
            print(f"Nr. {v['id']} | {v['datei']} | Code-Rat {wartung.zustimmung(v)[0]}/3 Ja | {stand}\n"
                  f"   {v['fehler'][:200]}")
        return 0
    if len(argv) < 4 or argv[2].lower() not in ("ja", "nein"):
        print(__doc__)
        return 1
    r = wartung.urteil_setzen(int(argv[1]), argv[2].lower() == "ja", argv[3], "Claude (Werkstatt)")
    print(r)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
