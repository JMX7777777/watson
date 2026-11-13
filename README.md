# Watson – your personal assistant for Windows

*[Deutsche Version: README.de.md](README.de.md)*

Watson is a personal AI assistant that lives on your Windows computer – in the spirit of J.A.R.V.I.S. or K.I.T.T.
He listens, speaks, remembers things for you, can read your screen and – only with your permission – click and type for you.
You can also talk to him from your phone through a private, encrypted tunnel.

> **Status:** early version, built and tested on one Windows 11 ARM laptop. It works there every day, but it has not
> been tested on many other computers yet. Feedback is welcome.

## What Watson can do

- **Talk**: type or speak. Conversation mode works like a voice call – Watson listens all the time, answers with his voice and listens again.
- **Many languages**: Watson listens, answers and speaks in 36 languages. Menus are available in English and German.
- **Your own character**: name, form of address and basis – *Christian (the Bible as the standard)*, *without religion (the laws of your country as the standard)* or described in your own words.
- **Respects the law**: every Watson respects the laws of the country you live in. He says honestly that he does not know every law and refers you to official bodies or experts for sensitive matters.
- **Free AI brains**: Watson uses free models via [OpenRouter](https://openrouter.ai) by default. A "conductor" chooses the right brain for each question. Paid models only if you switch them on.
- **Memory**: conversations, a notepad of facts, a knowledge book and learned abilities – all stored locally.
- **Eyes and hands**: read the screen as text, open programs, click and type – with four trust levels and fixed limits (never passwords, banking or payments; sending, deleting and buying are always confirmed).
- **Tools**: plug in tools via the Model Context Protocol (MCP), optional automations with n8n.
- **Phone**: chat, voice and permission questions on your phone via Tailscale, protected by password and fingerprint (passkeys).
- **Grows over time**: nightly reflection, self-test, checking new free models and careful self-repair (only with your OK).

## Installation

1. **Download** `Watson-Setup.exe` from the latest release:
   **[Releases → latest version](../../releases/latest)**
2. Start `Watson-Setup.exe`. Windows SmartScreen may say *"Windows protected your PC"* because the installer is
   not code-signed – click **More info → Run anyway**.
3. No administrator rights are needed. The setup assistant asks where you live, which language Watson should speak,
   your name and the basis Watson should have, shows a privacy note and then installs everything
   (usually a few minutes, with a time estimate). An internet connection is needed.
4. On first start Watson helps you to create a free OpenRouter key (about 2 minutes).

Requirements: Windows 10 or 11 (64-bit), about 3 GB free disk space, microphone and speakers for voice.

*Build it yourself:* run `installer\bauen.ps1` in PowerShell – it creates `installer\Ausgabe\Watson-Setup.exe`.

## Privacy

- **Stays on your computer:** conversations, memory, settings, recordings, voices. Keys are stored encrypted in the Windows Credential Manager.
- **Goes to the internet:** the questions you ask Watson are sent to OpenRouter and the AI models it routes to, so that Watson can think. Do not share passwords or very private data in conversations.
- Texts on web pages or the screen are never treated as commands – only you give Watson tasks.

## Honest limits

- The free AI models are sometimes slow or overloaded; Watson then automatically tries another one.
- Speech recognition takes a few seconds on a normal laptop CPU.
- Watson can make mistakes. Check important things yourself.

## License

Watson is free software under the **GNU General Public License v3.0** – see [LICENSE](LICENSE).
Third-party components and their licenses: see [THIRD_PARTY.md](THIRD_PARTY.md).
