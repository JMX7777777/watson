#!/bin/bash
# Richtet die schnelle eigene Stimme für Watson ein (omnivoice.cpp, MIT-Lizenz) – in WSL Ubuntu-24.04.
# Ein Durchlauf: Werkzeuge holen, Quellcode (fester Stand), Watson-Ergänzung (--steps), bauen, Modelle laden.
# Aufruf (in Windows): wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/<Watson-Ordner>/werkzeuge/omnivoice-einrichten.sh
set -e
HIER="$(cd "$(dirname "$0")" && pwd)"
STAND=dbfc792d6fbe0cc3a776817f56de35a3744d7594
export DEBIAN_FRONTEND=noninteractive
command -v cmake >/dev/null && command -v g++ >/dev/null && command -v git >/dev/null && command -v curl >/dev/null || {
  apt-get update -qq && apt-get install -y -qq build-essential cmake git curl >/dev/null; }
mkdir -p /opt && cd /opt
if [ ! -d omnivoice.cpp ]; then
  git clone --recurse-submodules https://github.com/ServeurpersoCom/omnivoice.cpp.git
fi
cd omnivoice.cpp
git checkout -q "$STAND" && git submodule update --init --recursive -q
git apply --check "$HIER/omnivoice-steps.patch" 2>/dev/null && git apply "$HIER/omnivoice-steps.patch" || echo "Ergänzung ist schon drin."
rm -rf build && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build . --config Release -j "$(nproc)" 2>&1 | tail -n 3
mkdir -p ../models && cd ../models
for f in omnivoice-base-Q8_0.gguf omnivoice-tokenizer-Q8_0.gguf; do
  [ -s "$f" ] || curl -sSL --fail -o "$f" "https://huggingface.co/Serveurperso/OmniVoice-GGUF/resolve/main/$f"
done
ls -la /opt/omnivoice.cpp/build/tts-server /opt/omnivoice.cpp/models
echo "FERTIG: eigene Stimme ist eingerichtet."
