# Practice in a Local VM

Rehearse the whole Linux deploy on your own machine before touching the cloud —
same Ubuntu, same `systemd`, zero bandwidth/cloud risk. Once this works, the
[[Deploy to Oracle Cloud]] steps are nearly identical. Part of [[Launch]].

> **Easiest option: Multipass.** It spins up a real Ubuntu VM with one command —
> far less fuss than VirtualBox for someone new to Linux. VirtualBox steps are
> below as an alternative.

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

## What this proves

If the bot runs as a `systemd` service in the VM, survives a reboot
(`sudo reboot`, then check `systemctl status osrsbot`), and the dashboard loads
in your browser — you've rehearsed the entire Oracle deploy. The only real
differences in the cloud are: the IP is public, and you switch from
`OSRS_BOT_HOST=0.0.0.0` back to the default `127.0.0.1` + an SSH tunnel for
security. See [[Constraints]] and [[Deploy to Oracle Cloud]].
