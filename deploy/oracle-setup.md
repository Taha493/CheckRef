# Setting up the Oracle Cloud server for CiteSure

What you get for free: one **Ampere Arm server with 4 CPU cores and 24 GB of memory**
("Always Free"), which runs CiteSure, Caddy (HTTPS) and, if wanted, the local AI model.

This guide covers what only you can do in the browser: the account, the server, the
firewall and pointing DuckDNS at it. When you can log in to the server (step 6), the
CiteSure installation itself is done with the phase 11 setup script.

---

## 1. Create the account

1. Go to <https://www.oracle.com/cloud/free/> → **Start for free**.
2. Fill in your details. Oracle asks for a **debit or credit card** to verify you are a real
   person. It places a small temporary hold; Always Free resources are never charged.
3. **Home region — choose carefully, it cannot be changed later.** The free Arm servers
   are only available in your home region, and some regions are often "out of capacity".
   Good choices near Pakistan: **India West (Mumbai)**, **India South (Hyderabad)**,
   **UAE East (Dubai)** or **Saudi Arabia West (Jeddah)**.
4. Wait for the "Your account is ready" email (minutes to an hour), then sign in at
   <https://cloud.oracle.com>.

## 2. Make an SSH key on your laptop

The key is how you (and nothing else) log in to the server. In a terminal on your laptop:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/citesure -C citesure
```

Press Enter twice (or set a passphrase). This creates two files:
- `~/.ssh/citesure` — the **private** key. Never share it or paste it anywhere.
- `~/.ssh/citesure.pub` — the **public** key. This one goes to Oracle in step 3.

Show the public key with `cat ~/.ssh/citesure.pub`.

## 3. Create the server

Menu (☰) → **Compute** → **Instances** → **Create instance**.

| Setting | Value |
|---|---|
| Name | `citesure` |
| Image | **Change image** → **Canonical Ubuntu** → **24.04** (not "Minimal") |
| Shape | **Change shape** → **Ampere** → **VM.Standard.A1.Flex** → **4 OCPUs**, **24 GB memory** |
| Networking | **Create new virtual cloud network** and **new public subnet** (the defaults) |
| Public IPv4 address | **Assign a public IPv4 address**: yes |
| Add SSH keys | **Paste public keys** → paste the content of `~/.ssh/citesure.pub` |
| Boot volume | Tick **Specify a custom boot volume size** → **100 GB** (free up to 200 GB in total) |

Click **Create**. After a minute or two the state turns green (**Running**). Copy the
**Public IP address** from the instance page.

**"Out of capacity for shape VM.Standard.A1.Flex"?** This is common. Try again later (early
morning often works), try another **Availability domain** in the Placement section, or
start with **2 OCPUs / 12 GB** and resize later (Instance → **Edit** → shape).

## 4. Open the web ports (Oracle's firewall)

The server only allows SSH (port 22) at first. Open 80 and 443 for the website:

1. On the instance page, click the **subnet** link → **Security** tab (or "Security Lists")
   → **Default Security List for …**.
2. **Add Ingress Rules**, twice:

| Source CIDR | IP protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

(Ubuntu on Oracle also has its own firewall inside the server; the setup script opens the
same two ports there.)

## 5. Point citesure.duckdns.org at the server

1. Sign in at <https://www.duckdns.org>.
2. In the row for **citesure**, type the server's **public IP** into the **current ip**
   box and click **update ip**.
3. Check from your laptop after a minute: `ping citesure.duckdns.org` shows that IP.

Keep the DuckDNS **token** (top of the DuckDNS page) private. The setup script will ask
for it on the server and keep the address updated by itself.

## 6. Log in once to check

```bash
ssh -i ~/.ssh/citesure ubuntu@citesure.duckdns.org
```

Type `yes` the first time. You should see an `ubuntu@citesure:~$` prompt. Type `exit` to
leave. **Stop here** — the next step is the CiteSure setup script (phase 11).

---

## Good to know

- **Idle servers can be reclaimed.** On a pure Always Free account Oracle may stop a server
  that stays nearly idle (CPU, network and memory all under 20%) for 7 days. A loaded AI
  model keeps memory use above that line. The sure way to avoid it is to upgrade the
  account to **Pay As You Go** (Billing → Upgrade): Always Free resources stay free, and
  idle servers are no longer reclaimed. If you do, set a **budget alert** of e.g. US$1
  (Billing → Budgets) so any accidental paid resource is noticed at once.
- **The public IP** stays the same as long as the server exists (stopping and starting
  keeps it; only deleting the server loses it).
- **Costs:** everything in this guide is inside the Always Free limits (4 OCPUs, 24 GB
  memory, 200 GB storage, 10 TB outbound traffic a month).
