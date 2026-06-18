# Practice in a Local VM

Rehearse the whole Linux deploy on your own machine before touching the cloud —
same Ubuntu, same `systemd`, zero bandwidth/cloud risk. Once this works, the
[[Deploy to Oracle Cloud]] steps are nearly identical. Part of [[Launch]].

> **Lightest option: WSL2** (Option C) — real Ubuntu on Windows, one command, no
> VM to download. Best for learning the flow. **Multipass** (Option A) is the
> easiest true VM. **VirtualBox** (Option B) is the most cloud-realistic.
> All three run the *same* install + `systemd` steps; only setup + networking
> differ.

---

## Option A — Multipass (recommended)

1. Install Multipass for Windows: <https://multipass.run> → download → next-next-finish.
2. Open **PowerShell** and create the VM:

```powershell
multipass launch --name osrsbot --cpus 2 --memory 4G --disk 10G
```

3. Enter the VM (this is your Ubuntu terminal):

```powershell
multipass shell osrsbot
```

4. Install + run the bot — **exactly steps 3 and 4 from [[Deploy to Oracle Cloud]]**
   (apt install, git clone, venv, then the `systemd` service). They are identical.

5. Find the VM's IP from PowerShell:

```powershell
multipass info osrsbot
```

   Look for the `IPv4` line, e.g. `10.x.x.x`.

6. See the dashboard from your Windows browser. The bot binds privately by
   default, so for **local practice** tell it to listen on all interfaces by
   editing the service's environment. In the VM:

```bash
sudo systemctl edit osrsbot
```

   In the editor that opens, add these two lines, then save (Ctrl+O, Enter, Ctrl+X):

```ini
[Service]
Environment=OSRS_BOT_HOST=0.0.0.0
```

   Then restart and open the dashboard:

```bash
sudo systemctl restart osrsbot
```

   On Windows, browse to **`http://<VM_IP>:8000`** (the IP from step 5).

> `OSRS_BOT_HOST=0.0.0.0` is fine on a local VM (only your machine can reach it).
> **Never** do this on the public Oracle server — there you keep the default
> `127.0.0.1` and use the SSH tunnel from the [[Deploy to Oracle Cloud]] guide.

7. Clean up when done practicing:

```powershell
multipass delete osrsbot
multipass purge
```

---

## Option B — VirtualBox

1. Install **VirtualBox** (<https://www.virtualbox.org>) and download the
   **Ubuntu Server** ISO (<https://ubuntu.com/download/server>).
2. VirtualBox → **New** → Linux/Ubuntu 64-bit → 4 GB RAM → 2 CPUs → 15 GB disk.
3. Attach the ISO, start the VM, and follow the Ubuntu Server installer
   (accept defaults; create a username; **enable "Install OpenSSH server"** when
   asked).
4. **Networking for the dashboard** — easiest is a **Bridged Adapter**:
   VM Settings → Network → Attached to: **Bridged Adapter**. The VM then gets an
   IP on your home network (find it with `ip a` inside the VM).
5. Install + run the bot — **steps 3 and 4 from [[Deploy to Oracle Cloud]]**,
   identical.
6. Set `OSRS_BOT_HOST=0.0.0.0` the same way as Multipass step 6, then browse to
   `http://<VM_IP>:8000` from Windows.

---

## Option C — WSL2 (lightest; Linux on Windows)

Real Ubuntu running on Windows with no VM to manage. Best for learning the flow.

1. In **PowerShell (Administrator)**:

```powershell
wsl --install
```

   Reboot when asked. Ubuntu finishes setup and prompts for a username +
   password. (If `wsl --install` says it's already installed, run
   `wsl --install -d Ubuntu`.)

2. **Turn on systemd** (off by default in WSL). In the Ubuntu terminal:

```bash
sudo nano /etc/wsl.conf
```

   Add these lines, then save (Ctrl+O, Enter, Ctrl+X):

```ini
[boot]
systemd=true
```

   Then in **PowerShell**, restart WSL:

```powershell
wsl --shutdown
```

   Reopen Ubuntu (Start menu → Ubuntu). Verify systemd is on: `systemctl status`
   should show a tree, not an error.

3. Install + run the bot — **steps 3 and 4 from [[Deploy to Oracle Cloud]]**,
   identical.

4. **Dashboard:** set `OSRS_BOT_HOST=0.0.0.0` the same way as Option A step 6
   (`sudo systemctl edit osrsbot`), restart, then just open
   **`http://localhost:8000`** in your Windows browser — WSL2 forwards localhost
   automatically, no IP lookup needed.

> **Caveat:** WSL2 runs only while Windows is on and WSL has been started; it
> does **not** auto-start at boot by default. Great for practice and as a local
> host while your PC is on — but not a 24/7 replacement. For always-on, use the
> [[Deploy to Oracle Cloud|Oracle VM]].

---

## What this proves

If the bot runs as a `systemd` service in the VM, survives a reboot
(`sudo reboot`, then check `systemctl status osrsbot`), and the dashboard loads
in your browser — you've rehearsed the entire Oracle deploy. The only real
differences in the cloud are: the IP is public, and you switch from
`OSRS_BOT_HOST=0.0.0.0` back to the default `127.0.0.1` + an SSH tunnel for
security. See [[Constraints]] and [[Deploy to Oracle Cloud]].
