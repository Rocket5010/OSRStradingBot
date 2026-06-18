# Deploy to Oracle Cloud (free, always-on)

Beginner guide. Goal: the bot runs 24/7 in the cloud for free, and you use its
dashboard from your own browser. You only touch the Linux terminal for this
one-time setup — daily use is the same web dashboard as local. Part of
[[Launch]].

> **Why this setup:** Oracle's free **Arm (Ampere A1)** instance is always-free
> and is not idle-reclaimed (the free AMD micro is — avoid it). The bot binds to
> `127.0.0.1` (private), and you reach it through an **SSH tunnel**, so nothing
> is exposed to the internet and no login code is needed. See [[Constraints]].

Anything in `<angle brackets>` is a placeholder — replace it with your value.

> **New to Linux? Rehearse locally first:** [[Practice in a Local VM]] runs these
> exact steps in a free local VM (Multipass/VirtualBox) — no cloud account, no
> bandwidth, nothing to break.

---

## 1. Create the server (in the Oracle web console)

1. Sign up at <https://www.oracle.com/cloud/free/> (Always Free).
2. Console → **Compute → Instances → Create instance**.
3. **Image:** Canonical **Ubuntu** (latest LTS).
4. **Shape:** click *Change shape* → **Ampere** → `VM.Standard.A1.Flex`.
   Set **1 OCPU** and **6 GB memory** (well within the free Arm allowance).
5. **SSH keys:** choose *Generate a key pair for me* and **download both keys**.
   Keep the **private** key safe — you need it to log in.
6. Click **Create**. When it's running, copy the **Public IP address**.

You do **not** need to open any extra ports. SSH (port 22) is open by default,
and that's all the tunnel uses.

---

## 2. Log in to the server

On Windows, open **PowerShell** and run (adjust the key path + IP):

```powershell
ssh -i C:\Users\sande\Downloads\<your-key>.key ubuntu@<VM_IP>
```

Type `yes` if asked to trust the host. You're now "in" the server — the prompt
changes to something like `ubuntu@...:~$`. Every command below runs there.

> If SSH complains the key is "too open", run once in PowerShell:
> `icacls C:\Users\sande\Downloads\<your-key>.key /inheritance:r /grant:r "%USERNAME%:R"`

---

## 3. Install the bot (copy-paste, one block at a time)

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

```bash
git clone https://github.com/Rocket5010/OSRStradingBot.git
cd OSRStradingBot
```

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Quick test that it starts (Ctrl+C to stop after you see "Uvicorn running"):

```bash
OSRS_BOT_UA="osrs-flip-bot/1.0 (sander.rocket@gmail.com)" .venv/bin/python -m bot.main
```

---

## 4. Make it run forever (auto-start + auto-restart)

Create a service file:

```bash
sudo nano /etc/systemd/system/osrsbot.service
```

Paste this (it matches the clone path above; change the email):

```ini
[Unit]
Description=OSRS Flip Bot
After=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/OSRStradingBot
Environment=OSRS_BOT_UA=osrs-flip-bot/1.0 (sander.rocket@gmail.com)
ExecStart=/home/ubuntu/OSRStradingBot/.venv/bin/python -m bot.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save and exit nano: **Ctrl+O**, **Enter**, **Ctrl+X**.

Turn it on:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now osrsbot
sudo systemctl status osrsbot      # should say "active (running)"; q to quit
```

The bot now starts on every boot and restarts itself if it crashes. To see
live logs: `journalctl -u osrsbot -f` (Ctrl+C to stop watching).

---

## 5. Open the dashboard from your PC (securely)

The bot listens only on the server's own `127.0.0.1`, so it's not reachable from
the internet. To view it, open an **SSH tunnel** from your Windows PowerShell:

```powershell
ssh -i C:\Users\sande\Downloads\<your-key>.key -L 8000:127.0.0.1:8000 ubuntu@<VM_IP>
```

Leave that window open, then browse to **<http://localhost:8000>** on your PC.
You're seeing the cloud bot's dashboard, tunneled privately over SSH. Close the
window to disconnect; the bot keeps running on the server.

> Want it without keeping a terminal open? You can later add a firewall rule for
> your home IP + a password — but the tunnel is the simplest secure option.

---

## 6. Updating the bot later

```bash
cd ~/OSRStradingBot
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart osrsbot
```

---

## Tuning for the free tier

- The weekly [[Watchlist Curator|curator]] is the heaviest job. On a small Arm
  shape it's fine; if it ever feels slow, lower the candidate cap (a future
  `curate_candidate_cap` config) or give the instance another OCPU (still free
  up to the Arm allowance).
- Everything else (5-min poll, dashboard) is light — see [[Constraints]].
