# Third-party components and licenses

Watson itself is licensed under the **GNU General Public License v3.0** (see `LICENSE`).
Watson does **not** bundle the components below in this repository – the installer downloads them from their
official sources. Their own licenses apply. This list was checked carefully, but it is not legal advice.

| Component | Used for | License |
|---|---|---|
| Python (via uv, Astral) | runtime | PSF License / uv: Apache-2.0 or MIT |
| pywebview | program window | BSD-3-Clause |
| piper-tts | speech output | **GPL-3.0** |
| Piper voices (rhasspy/piper-voices) | voices | **per voice** – the installer only downloads voices whose model card names a free license (CC0, CC-BY, MIT, Apache, …) and shows it |
| faster-whisper, CTranslate2, Whisper models | speech recognition | MIT |
| webrtcvad-wheels | voice detection | MIT |
| onnxruntime | AI runtime | MIT |
| numpy | maths | BSD-3-Clause |
| sounddevice | microphone / speaker | MIT |
| PyAV (av) | audio tempo | BSD-3-Clause (contains FFmpeg, LGPL/GPL) |
| uiautomation | reading the screen | Apache-2.0 |
| pythonnet, comtypes, pywin32 | Windows access | MIT / MIT / PSF |
| keyring, winrt packages | key vault, Windows Hello | MIT |
| webauthn (Duo Labs) | fingerprint sign-in on the phone | BSD-3-Clause |
| mcp, mcp-server-fetch, mcp-server-time | tool socket (Model Context Protocol) | MIT |
| Tabler Icons | icons | MIT (`studio/assets/TABLER-LICENSE.txt`) |

## Optional components (only if you install them yourself)

| Component | Notes |
|---|---|
| **n8n** (`n8n-linux/installieren.sh`) | Sustainable Use License (fair-code) – free for personal and internal use; read the license before commercial use. |
| **Hermes Agent** (Nous Research) | MIT |
| **omnivoice.cpp** (own voice, `studio/eigene-stimme/`) | code MIT; the **OmniVoice model weights do not allow commercial use**. Clone only your own voice or a voice you have written permission for. |
| **Tailscale** (phone access) | proprietary client, free for personal use |
| **OpenRouter** | online AI service – its terms of service apply; questions you ask Watson are sent there |
