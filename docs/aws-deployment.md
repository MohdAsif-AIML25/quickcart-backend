# Deploying QuickCart to AWS

This guide puts the whole stack (React frontend, API, PostgreSQL, Redis) on **one EC2 instance**
with Docker Compose. It is the cheapest and simplest deployment that is still
real: a public URL, containers that restart on failure, secrets kept off GitHub.

```text
Your laptop ──git push──▶ GitHub
                             │ git clone / git pull
                             ▼
Internet ──HTTP :80──▶ EC2 instance (Ubuntu, Docker)
                       ├── web    (nginx: serves the React app, forwards /api/ to api)
                       ├── api    (FastAPI, not reachable from the internet)
                       ├── db     (PostgreSQL, not reachable from the internet)
                       └── redis  (not reachable from the internet)
```

**Why this design and not ECS, RDS, and a load balancer?** Those are the right
tools for a production system with real traffic, but each one costs money every
hour and adds a week of learning. For a portfolio project, one server proves the
same skills (Docker, networking, secrets, deployment) for almost nothing. The
last section shows the upgrade path, which you should be able to *explain* in an
interview even if you have not built it.

---

## Before you start: cost

Read this section first. AWS bills by the hour for whatever is running.

- **New accounts (created on or after 15 July 2025)** get USD 100 in credits at
  sign-up and can earn up to USD 100 more. On the *free plan* you cannot be
  charged, but the account closes automatically when the credits run out or
  after six months, whichever comes first.
- **Older accounts** get the classic 12-month free tier with monthly limits.
- `t3.micro` is free-tier eligible for both kinds of account.
- A public IPv4 address is billed per hour (about USD 0.005). It is small, but
  it is why an instance you forgot about still costs money.

Do these two things today:

1. In the AWS console, open **Billing and Cost Management → Budgets** and create
   a monthly cost budget of USD 5 with an email alert.
2. **Stop the instance** when you are not showing the project to anyone.
   **Terminate** it when you no longer need it.

---

## Step 1: Launch the EC2 instance

In the AWS console, pick a region close to you (for example **Asia Pacific
(Mumbai) ap-south-1**), then go to **EC2 → Instances → Launch instances**.

| Setting | Value |
|---|---|
| Name | `quickcart-server` |
| AMI | Ubuntu Server 24.04 LTS |
| Instance type | `t3.micro` |
| Key pair | Create new → name `quickcart-key` → RSA → `.pem` → download it and keep it safe |
| Storage | 20 GiB, gp3 |

**Network settings → Edit → Security group rules.** A security group is the
instance's firewall. Add exactly these two inbound rules:

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | **My IP** | Only you can log in to the server |
| HTTP | 80 | Anywhere (0.0.0.0/0) | Everyone can reach the shop |

Do **not** open ports 5432 (PostgreSQL) or 6379 (Redis). The database must
never be reachable from the internet.

Click **Launch instance**. When its state is *Running*, copy its
**Public IPv4 address**. It is written as `YOUR_IP` below.

## Step 2: Connect to the server

**Easiest (works in the browser):** select the instance → **Connect** →
**EC2 Instance Connect** → **Connect**.

**From PowerShell on your laptop:**

```powershell
ssh -i "$HOME\Downloads\quickcart-key.pem" ubuntu@YOUR_IP
```

If Windows says *"UNPROTECTED PRIVATE KEY FILE"*, restrict the file to your user:

```powershell
icacls "$HOME\Downloads\quickcart-key.pem" /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

If the connection times out later, your home IP address has probably changed.
Edit the SSH rule in the security group and choose **My IP** again.

## Step 3: Install Docker on the server

Run these on the server. They are the official Docker instructions for Ubuntu.

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Allow your user to run Docker without `sudo`, then log out and back in:

```bash
sudo usermod -aG docker ubuntu
exit
```

Reconnect and check:

```bash
docker --version
docker compose version
```

### Add swap (important on t3.micro)

`t3.micro` has 1 GiB of memory. Building the image while PostgreSQL is running
can run out of memory and freeze the server. A swap file prevents that:

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h      # the Swap row should show 1.0Gi
```

## Step 4: Get the code and create the secrets

```bash
git clone https://github.com/MohdAsif-AIML25/quickcart-backend.git
cd quickcart-backend
cp .env.prod.example .env.prod
```

Generate two random values:

```bash
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24))"
```

Open the file with `nano .env.prod`, paste both values over the placeholders,
and save (Ctrl+O, Enter, Ctrl+X). Then make the file readable only by you:

```bash
chmod 600 .env.prod
```

`.env.prod` exists **only on the server**. It is listed in `.gitignore`, so it
can never be pushed to GitHub. Use new values here, not the ones from your
laptop.

## Step 5: Start the stack

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

The first build takes a few minutes. Then check:

```bash
docker compose -f docker-compose.prod.yml ps        # four services "Up" and "healthy"
curl http://localhost/api/health
```

From your laptop, open these in a browser. Use `http://`, not `https://`.

| Address | What you should see |
|---|---|
| `http://YOUR_IP/` | The QuickCart shop |
| `http://YOUR_IP/api/docs` | Swagger, the API documentation |

✅ **Checkpoint:** the shop loads from the public IP, you can sign up, and after
Step 6 you can create a product on the Admin page and buy it.

## Step 6: Create the first admin

Sign up in the shop (**Sign up** button), then promote that account on the server:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec db \
  psql -U quickcart -d quickcart -c "UPDATE users SET role = 'admin' WHERE email = 'you@example.com';"
```

(If you changed `POSTGRES_USER` or `POSTGRES_DB` in `.env.prod`, use those names
after `-U` and `-d`.)

It should print `UPDATE 1`. Reload the shop: an **Admin** link appears in the
navigation bar. (`scripts/promote_admin.py` refuses to run when
`ENVIRONMENT=production`, on purpose, so the first admin is created with SQL.)

## Step 7: Deploy a new version

After you push new commits to GitHub:

```bash
cd ~/quickcart-backend
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Only the images whose files changed are rebuilt (`api`, `web`, or both). New
Alembic migrations are applied automatically when the API starts. The database
volume is untouched.

## Everyday commands

```bash
# Tip: add this line to ~/.bashrc so you can type "dc ps", "dc logs api", ...
alias dc='docker compose -f docker-compose.prod.yml --env-file .env.prod'

dc ps                      # status
dc logs -f api             # follow the API logs (Ctrl+C to stop)
dc logs -f web             # nginx access log: every request from a browser
dc restart api             # restart only the API
dc down                    # stop everything; data volumes are KEPT
dc exec -T db pg_dump -U quickcart quickcart > backup.sql   # backup the database to a file
```

Never run `dc down -v` unless you want to delete the database: `-v` removes the volumes.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Browser cannot reach `http://YOUR_IP/` | Port 80 is not open, or you typed `https://` | Check the security group's HTTP rule; use `http://` |
| The shop loads but shows "Request failed (HTTP 502)" | nginx is up, the API is not | `dc ps`, then `dc logs api` |
| `web` never starts | It waits until `api` is healthy | `dc logs api`; check the health path in the API `Dockerfile` |
| SSH times out | Your home IP changed | Edit the SSH rule → **My IP** |
| `required variable ... is missing` | Forgot `--env-file .env.prod` | Add the flag (or use the `dc` alias) |
| `api` keeps restarting | The app failed at start-up | `dc logs api` and read the last error |
| `password authentication failed` | You changed `POSTGRES_PASSWORD` after the first start. The old password is stored in the volume. | Put the original password back. On a server with no data to keep: `dc down -v`, then start again. |
| Build is killed or the server freezes | Out of memory | Add the swap file from Step 3 |
| The public IP changed | You stopped and started the instance | Use the new IP, or allocate an Elastic IP (billed while the instance is stopped) |

## Shutting down

- **Stop** (EC2 → Instance state → Stop): the disk is kept, compute billing
  stops, the public IP changes on the next start. The containers start again
  automatically because of `restart: unless-stopped`.
- **Terminate**: deletes the instance and its disk. Afterwards, check
  **EC2 → Volumes** and **Elastic IPs** and delete anything left over.

---

## How the frontend is served

The `web` container is built from `frontend/Dockerfile` in two stages: Node
builds the React app into static files, then nginx serves them. The same nginx
forwards every `/api/...` request to the `api` container
(`frontend/nginx.conf`).

```text
GET http://YOUR_IP/               → nginx → index.html + JS + CSS
GET http://YOUR_IP/cart           → nginx → index.html  (React Router shows the cart page)
GET http://YOUR_IP/api/products   → nginx → http://api:8000/products
```

This one decision removes three common deployment problems:

| Problem | Why it does not happen here |
|---|---|
| **CORS** errors | The page and the API share one origin, so the browser never makes a cross-origin request. |
| **Mixed content** (an `https://` page calling an `http://` API) | Both are served through the same address and protocol. |
| The API exposed to the internet | Only nginx publishes a port. The API has none. |

Two settings on the `api` service in `docker-compose.prod.yml` make it work behind nginx:

- `UVICORN_ROOT_PATH=/api` tells FastAPI its public address starts with `/api`, so Swagger loads `/api/openapi.json`.
- `FORWARDED_ALLOW_IPS=*` makes the API read the visitor's address from the
  `X-Forwarded-For` header that nginx sets. Without it, every visitor would
  appear to be nginx, and five login attempts by anyone would lock out everyone.

---

## The upgrade path (know it, do not build it yet)

This single-server design has real weaknesses. Be ready to name them and say
what you would change:

| Weakness today | Production answer | Why |
|---|---|---|
| Database on the same disk as the app, no automatic backups | **Amazon RDS for PostgreSQL** | Managed backups, patching, and failover |
| Redis on the same server | **Amazon ElastiCache** | Managed, survives app-server replacement |
| Images on a local volume | **Amazon S3** | Shared by every server, practically unlimited, durable |
| One server; a deploy means a short outage | **ECR + ECS Fargate** behind an **Application Load Balancer** | Several copies of the API, rolling deploys, health-based replacement |
| Plain HTTP | **ACM certificate** on the load balancer, plus a domain in Route 53 | HTTPS |
| Frontend files served from the app server | **S3 + CloudFront** | Static files from a CDN close to the user; the server only handles API calls |
| Secrets in a file on the server | **AWS Secrets Manager** or SSM Parameter Store | Encrypted, audited, rotated |
| `git pull` by hand | GitHub Actions deploy job | Repeatable deployments |
| Migrations run when the container starts | A separate one-off migration task | With several API copies, two would migrate at the same time |

A good interview sentence: *"I deployed it on a single EC2 instance with Docker
Compose to keep the cost near zero. The trade-off is that the database and the
app share one machine, so in production I would move PostgreSQL to RDS and run
the API on ECS behind a load balancer."*

## References

- [AWS Free Tier: credits and account plans](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html)
- [AWS Free Tier: choosing a plan](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html)
- [EC2 Free Tier eligible instance types](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html)
- [AWS public IPv4 address charge](https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights)
- [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
