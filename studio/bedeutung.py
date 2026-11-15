"""
Bedeutungs-Suche für Watsons Gedächtnis.

Die Stichwort-Suche (FTS5) findet nur gleiche Wörter: „Auto“ findet nicht „Fahrzeug“.
Hier verwandelt ein kleines Sprachmodell (multilingual-e5-small, BERT-Art, ~120 MB, läuft auf dem Laptop,
ohne Internet nach dem ersten Laden) jeden Text in einen „Bedeutungs-Fingerabdruck“ (384 Zahlen).
Texte mit ähnlicher Bedeutung haben ähnliche Fingerabdrücke – auch mit ganz anderen Wörtern.

Gemessen am 15.11.2026 (12 Testfragen, 46 Fakten): Stichwort 5/12, Bedeutung 9/12, beides gemischt 10/12.
~12 ms pro Frage, ~20 ms pro neuem Fakt. Fehlt das Modell, arbeitet Watson einfach wie vorher (nur Stichworte).
"""
import threading

import numpy as np

REPO = "Xenova/multilingual-e5-small"
DATEIEN = ("onnx/model_quantized.onnx", "tokenizer.json")
DIM = 384

_lock = threading.Lock()
_sess = _tok = _eingaben = None
_fehler = None


def _pfad(name):
    from huggingface_hub import hf_hub_download
    try:
        return hf_hub_download(REPO, name, local_files_only=True)   # schon da -> kein Internet nötig
    except Exception:
        return hf_hub_download(REPO, name)                          # beim ersten Mal einmalig laden


def laden():
    """Lädt das Modell (beim ersten Mal ~120 MB aus dem Internet). True = bereit."""
    global _sess, _tok, _eingaben, _fehler
    with _lock:
        if _sess is not None:
            return True
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
            modell, tokdatei = (_pfad(d) for d in DATEIEN)
            tok = Tokenizer.from_file(tokdatei)
            tok.enable_truncation(256)
            tok.enable_padding()
            so = ort.SessionOptions()
            so.intra_op_num_threads = 2          # Laptop nicht ausbremsen
            sess = ort.InferenceSession(modell, so, providers=["CPUExecutionProvider"])
            _eingaben = {i.name for i in sess.get_inputs()}
            _tok, _sess, _fehler = tok, sess, None
            return True
        except Exception as e:
            _fehler = str(e)
            return False


def bereit():
    return _sess is not None


def fehler():
    return _fehler


def einbetten(texte, art="passage"):
    """Texte -> Fingerabdrücke (normiert, float32). art: "passage" für Gespeichertes, "query" für Fragen."""
    if not texte:
        return np.zeros((0, DIM), np.float32)
    if _sess is None and not laden():
        raise RuntimeError(_fehler or "Bedeutungs-Modell nicht verfügbar")
    enc = _tok.encode_batch([f"{art}: {t}" for t in texte])
    ids = np.array([e.ids for e in enc], np.int64)
    maske = np.array([e.attention_mask for e in enc], np.int64)
    feed = {"input_ids": ids, "attention_mask": maske}
    if "token_type_ids" in _eingaben:
        feed["token_type_ids"] = np.zeros_like(ids)
    h = _sess.run(None, feed)[0]
    v = (h * maske[..., None]).sum(1) / np.maximum(maske.sum(1, keepdims=True), 1)
    v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
    return v.astype(np.float32)
