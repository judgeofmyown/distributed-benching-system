# host auotmation installation script
# !/usr/bin/env bash
set -e

echo "[*] Downloading and installing gVisor runtime components ..."
curl -fsSl https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | sudo tee /etc/apt/sources.list.d/gvisor.list

sudo apt-get update && sudo apt-get install -y runsc

echo "[*] Registering runsc inside Docker configurations."
sudo runsc install

echo "[*] Activating updates via Docket Daemon Restart."
sudo systemctl restart docker

echo "[+] Success, testing sandbox layer activation"
docker run --rm --runtime=runsc ubuntu dmesg | grep -i gvisor


