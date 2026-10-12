# START HERE — MUH on AWS Lightsail for a $100-credit account

This is the lowest-complexity demonstration path for a beginner. The existing
\`docs/AWS_PUBLIC_DEMO.md\` describes the more expensive Elastic Beanstalk + RDS
architecture for a larger audience. For a small, controlled public-access demo
use **Lightsail Ubuntu + Docker Compose + PostgreSQL + Caddy HTTPS**, all on
one $24/month 4 GiB Lightsail instance (subject to AWS region/bundle pricing).

**No AWS deployment occurs when this branch is committed.** Follow the steps
below in your own AWS account. Never paste passwords, SSH private keys or
your \`.env\` file into chats or GitHub.

## 1. Verify the $100 credit and set a budget BEFORE making resources

1. Sign into https://console.aws.amazon.com/ .
2. Use the top-right account menu -> Billing and Cost Management.
3. Check **Free Tier / Credits**: remaining credit, eligible services, plan
   (Free or Paid) and expiry. The Free plan may restrict some services.
4. In **Budgets**, create a monthly Cost Budget of **$30**, with alerts at
   50%, 80% and 100% sent to your email. Verify the email if AWS asks you
   to do so. Budgets alert you: they do not automatically stop the service.
5. Do not create RDS, an Application Load Balancer, a NAT gateway or a
   managed container environment for this Lightsail approach.

## 2. Create one Lightsail instance

Go to https://lightsail.aws.amazon.com/ -> **Create instance**.

* Location: **London / eu-west-2**, or your preferred region if the bundle is
  not shown.
* Platform: **Linux/Unix**, Blueprint: **OS Only**, **Ubuntu 24.04 LTS**.
* Networking: plan with **public IPv4** (dual stack is fine).
* Size: **Medium / 4 GB RAM / 2 vCPU / 80 GB SSD**, published **$24/mo**.
  This is a starting point, not proven throughput for simultaneous model
  searches. Don't select the $44/8GB plan without a budget review.
* Name: \`midshire-ed-demo\`. Click **Create instance**.

After it is running:

1. On the instance -> **Networking** -> attach a **static IPv4** via Create
   static IP; write the IP down. An attached static IP has no separate
   Lightsail fee; an unattached one may.
2. Under IPv4 firewall: allow **HTTP TCP 80** and **HTTPS TCP 443** from
   Anywhere. SSH TCP 22 is needed for administration: restrict its source
   once the browser SSH workflow is confirmed; leave 8000, 5432 CLOSED.
   If IPv6 is enabled, review its firewall separately.
3. Click **Connect using SSH** on the instance (browser terminal).
   All commands below are run in that terminal, NOT in your computer's terminal.

## 3. Install Docker, Compose and Git on Ubuntu

Paste this block into the Lightsail browser SSH terminal:

\`\`\`bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker compose version
\`\`\`

If the host reports a different architecture (\`uname -m\` shows \`aarch64\`),
change \`Architectures: amd64\` to \`Architectures: arm64\` before installing
Docker. Ubuntu 24.04 should report \`noble\` with
\`lsb_release -cs\`. Docker must be running; use \`sudo systemctl status docker\`.

For simplicity and security, use \`sudo docker ...\` rather than giving your
regular user effectively root-level access through the \`docker\` group.

## 4. Allow the server read-only access to your PRIVATE GitHub repository

Generate one **read-only deploy key** on the Lightsail host:

\`\`\`bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -N "" -f ~/.ssh/muh_lightsail_deploy -C "midshire-lightsail-readonly"
cat ~/.ssh/muh_lightsail_deploy.pub
\`\`\`

**Copy the single line beginning \`ssh-ed25519\` — it is the PUBLIC key.**
Never copy or show \`~/.ssh/muh_lightsail_deploy\` (without \`.pub\`).

On GitHub in a different browser tab:

1. Open https://github.com/mrsonuk/Simulation_model/settings/keys .
2. **Add deploy key** -> Title \`Midshire Lightsail read-only\`.
3. Paste the public key; **leave "Allow write access" UNCHECKED**. Save.

Back in the Lightsail SSH terminal:

\`\`\`bash
cat > ~/.ssh/config <<'EOF'
Host github-muh
    HostName github.com
    User git
    IdentityFile ~/.ssh/muh_lightsail_deploy
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T git@github-muh
\`\`\`

On the first connection, compare the GitHub host key fingerprint with the
official https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
before answering \`yes\`. GitHub may say you have authenticated but do not
have shell access — that is expected.

Clone the separate AWS branch:

\`\`\`bash
cd ~
git clone --depth 1 --single-branch --branch deploy/aws-midshire-public \
    git@github-muh:mrsonuk/Simulation_model.git
cd Simulation_model
\`\`\`

## 5. Generate your local secrets and temporary HTTPS hostname

No domain purchase is needed for a **short-lived test**:
\`sslip.io\` provides free public DNS based on your Lightsail static IP.
It is operated by a third party, so use a domain you control before presenting
it as a permanent client service.

Paste this block from inside the \`~/Simulation_model\` directory:

\`\`\`bash
python3 - <<'PY'
import os, secrets
from pathlib import Path
path = Path(".env")
if path.exists():
    raise SystemExit(".env already exists: refusing to overwrite your working passwords.")
ip = input("Paste the Lightsail STATIC public IPv4 address: ").strip()
parts = ip.split(".")
if len(parts) != 4 or not all(p.isdecimal() and 0 <= int(p) <= 255 for p in parts):
    raise SystemExit("This does not look like an IPv4 address.")
site = "midshire." + "-".join(parts) + ".sslip.io"
path.write_text(
    "POSTGRES_PASSWORD=" + secrets.token_hex(24) + "\n"
    "MIDSHIRE_SESSION_SECRET=" + secrets.token_urlsafe(48) + "\n"
    "SITE_DOMAIN=" + site + "\n"
)
os.chmod(path, 0o600)
print("Your demo URL will be: https://" + site)
PY
\`\`\`

IMPORTANT: The \`.env\` file contains TWO SECRETS. The branch's
\`.gitignore\` and \`.dockerignore\` exclude it. Don't upload it or
post its contents. Keep a secure backup if you need to recreate the server.
Never regenerate it when updating the application.

## 6. Start the app, database and HTTPS proxy

\`\`\`bash
sudo docker compose -f compose.lightsail.yaml config --quiet
sudo docker compose -f compose.lightsail.yaml up -d --build
sudo docker compose -f compose.lightsail.yaml ps
\`\`\`

The Compose file starts exactly three containers:

* \`app\`: MUH Flask app via Gunicorn, one worker/one expensive job at a time;
* \`db\`: PostgreSQL 16, private Docker network, persistent Docker volume;
* \`https\`: Caddy, automatic free TLS via Let's Encrypt, public ports 80/443.

There are **no published database or app ports**. Only Caddy is accessible
from the internet. To follow startup:

\`\`\`bash
sudo docker compose -f compose.lightsail.yaml logs --tail=50 app
sudo docker compose -f compose.lightsail.yaml logs --tail=50 https
\`\`\`

Once Caddy has provisioned a certificate:

\`\`\`bash
SITE_DOMAIN=$(grep '^SITE_DOMAIN=' .env | cut -d= -f2-)
curl -fsS "https://$SITE_DOMAIN/healthz"
\`\`\`

Expected: \`{"status":"ok"}\`. Now open
\`https://<YOUR_PRINTED_SITE_DOMAIN>\` in a normal browser. The MUH tool
should display the baseline and tabs.

If Caddy cannot obtain a certificate, make sure:
the STATIC IP is attached, DNS resolves to it, ports 80+443 are allowed in the
Lightsail firewall, and no other process occupies those ports. Check
\`sudo docker compose -f compose.lightsail.yaml logs https\`.

If the app repeatedly restarts, check \`logs app\` and \`logs db\`. It will
intentionally refuse to start if its security configuration is incomplete.

## 7. Test two separate visitors BEFORE sharing with NHS colleagues

1. Open the HTTPS URL normally as visitor A, and in a separate private/incognito
   browser window as visitor B.
2. A creates a scenario; B creates another. B must not see A's private scenario.
3. Apply different scenarios; A's reset must not reset B's view.
4. Confirm precomputed baseline, the four-hour measure, pathway diagrams and
   workforce + estate searches display.
5. Start one arbitrary new simulation to verify the server is sufficiently
   resourced. Large searches can take substantial time and are limited.
6. Keep the URL among a SMALL group of invited testers, even though it requires
   no login: rate limiting inside the app is anonymous-cookie based and can be
   bypassed by resetting cookies. This is NOT a hardened unlimited-public
   service, and there is no ALB/AWS WAF in this budget architecture.
7. Never upload confidential hospital data or identifiable patient information.

## 8. Update the application safely

Keep \`.env\` and database volumes intact:

\`\`\`bash
cd ~/Simulation_model
git pull --ff-only
sudo docker compose -f compose.lightsail.yaml up -d --build
sudo docker compose -f compose.lightsail.yaml ps
\`\`\`

\`docker compose down\` stops containers **but keeps the database**. Do NOT
run \`docker compose down -v\` unless you explicitly want to erase all saved
scenarios/results.

## 9. Backups and costs

Consider enabling Lightsail's **automatic instance snapshots** under the
instance **Snapshots** tab. They cost extra (AWS currently lists
$0.05/GB-month of snapshot storage), and are not the same as regular
Postgres-aware backups.

For a manual Postgres export into a permission-restricted host file:

\`\`\`bash
cd ~/Simulation_model
umask 077
sudo docker compose -f compose.lightsail.yaml exec -T db \
    pg_dump -U midshire midshire > midshire-backup.sql
chmod 600 midshire-backup.sql
\`\`\`

The backup contains visitors' saved scenarios. Store it securely, off-server
if needed, and delete it when no longer required. Schedule an anonymous
scenario retention process before expanding access.

To stop charges, DELETE the Lightsail instance once the demo ends, and
release any unattached static IP and unwanted snapshots. Merely stopping an
ordinary Lightsail instance does **not** eliminate its instance charge.
Inspect Billing, Credits and Cost Explorer regularly. Budgets are alerts,
not a hard spending cap.

## 10. Scale later

The $24/mo Lightsail option is deliberately one host, one Flask worker,
PostgreSQL on the same machine, and limited CPU. It may slow down under
simultaneous full searches. A larger public launch requires separate
database/worker services, durable SQS jobs, load balancing, WAF, monitoring,
performance benchmarking, and a privacy/retention policy. The more extensive
architecture is documented in [AWS_PUBLIC_DEMO.md](AWS_PUBLIC_DEMO.md).

Official references:
- Lightsail pricing: https://aws.amazon.com/lightsail/pricing/
- Lightsail instance setup: https://docs.aws.amazon.com/lightsail/latest/userguide/getting-started-with-amazon-lightsail.html
- Caddy HTTPS: https://caddyserver.com/docs/automatic-https
- GitHub read-only deploy keys: https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys
- Docker Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- Temporary sslip.io DNS: https://sslip.io/
