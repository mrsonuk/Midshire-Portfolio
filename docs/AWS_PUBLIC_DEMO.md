# MUH on AWS: public interactive demonstration

**Deployment status:** This branch contains deployment files and public-demo protections. No AWS account has been modified and **there is no live URL until you deploy it**.

**Recommended first deployment:** Elastic Beanstalk **Docker on Amazon Linux 2023**, **load-balanced with an Application Load Balancer**, one EC2 instance, one Gunicorn worker, and **Amazon RDS PostgreSQL**. Put **AWS WAF** on the ALB. Use a domain that has an **AWS Certificate Manager (ACM)** certificate and require HTTPS. This design is a **bounded public demonstrator, not a production multi-instance service**.

Why Beanstalk: AWS announced in March 2026 that App Runner would cease admitting new customers in April 2026. Existing App Runner customers may continue to use it; Beanstalk with Docker does not require prior App Runner access.

## 0. Boundaries / prerequisites

* Repo: private \`mrsonuk/Simulation_model\`. Source branch to deploy: \`deploy/aws-midshire-public\`. Do not deploy the legacy Cambridge entry point.
* Python 3.11 via \`Dockerfile\`; Gunicorn on **8000** (1 worker, 4 request threads); \`/healthz\` is an unprotected health check.
* Public-demo mode **fails to start** unless \`MIDSHIRE_SESSION_SECRET\` has >=32 characters and \`MIDSHIRE_DATABASE_URL\` is a PostgreSQL SQLAlchemy URL. Do not set \`MIDSHIRE_PUBLIC_MODE=0\` on a publicly accessible endpoint.
* Browser sessions are signed, Secure, HttpOnly, SameSite=Lax; visitors' saved scenarios and applied selections are independent. Every write must carry the CSRF token from the served page.
* Simulation jobs and their status are visitor-specific; the in-process scheduler runs one expensive job at once and queues at most three more. Results cached from the same *numerical input configuration* can be shared because the model contains no patient-level records. No source patient feed is connected.
* **Do not auto-scale above one EC2 instance or configure more than one Gunicorn worker.** In-progress job state is currently in process memory. A process restart loses running jobs (not completed results); for multiple instances you must first replace \`jobs.py\` with an SQS/durable-worker setup.
* The public app does not accept real patient data. Midshire is fictional; this model is not a clinical decision support tool.

You need an AWS account with Beanstalk, EC2, ALB, RDS, ACM, WAF, Secrets Manager, CloudWatch, IAM and VPC permissions; an owned DNS domain; and a checkout of this private GitHub branch on a development machine with Git, Docker, AWS CLI and [EB CLI](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3.html).

## 1. Verify the source locally

\`\`\`bash
git fetch origin
git switch deploy/aws-midshire-public
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uec_hybrid.tests.public
python -m uec_hybrid.tests.run
docker build -t midshire-aws .
\`\`\`

This public security test uses a temporary SQLite database **only in the test runner**. Do **not** use local SQLite for the hosted service. It checks two separate browsers cannot read, edit, apply, delete, export or compare each other's scenarios, and checks CSRF and job ownership.

For a local *non-public* visual smoke test (localhost only):
\`\`\`bash
MIDSHIRE_PUBLIC_MODE=0 python -m uec_hybrid.midshire
# browser: http://127.0.0.1:5050
\`\`\`

## 2. Create the cloud infrastructure (AWS Console)

Use **Europe (London), eu-west-2** unless there is an organisational reason to choose another region.

**A. Create an RDS PostgreSQL database.**

1. RDS > Databases > Create database > PostgreSQL. Name the initial database \`midshire\`, use a dedicated login, enable encryption and automated backups. Choose a suitable sized instance (a small production-appropriate tier for rehearsal; benchmark before public traffic).
2. Keep **Public access = No** and place RDS in private subnets in the same VPC as Beanstalk. Give it its own security group initially with no inbound rule.
3. Keep the master or dedicated application's password in **AWS Secrets Manager**. Prefer a least-privilege application database user. Do not connect from an Internet-accessible machine or allow \`0.0.0.0/0\` to TCP 5432.
4. Build the SQLAlchemy URL (URL-encode special characters in password):
   \`postgresql+psycopg://midshire_user:<URL_ENCODED_PASSWORD>@<PRIVATE_RDS_ENDPOINT>:5432/midshire?sslmode=require\`
5. Store this full URL as a **secret text value** in Secrets Manager, e.g. \`midshire/public/database-url\`. Do not paste it into a GitHub file.

**B. Create the signing secret.**

Generate a random secret offline:
\`\`\`bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
\`\`\`
Store this in Secrets Manager as \`midshire/public/session-secret\`. Keep the same value across deployments: changing it invalidates all visitors' session cookies.

**C. Set up Elastic Beanstalk.**

1. Elastic Beanstalk > Create application (e.g. \`midshire-ed\`) > Environment type **Web server**.
2. Platform **Docker / Amazon Linux 2023**, **Load balanced**, with an **Application Load Balancer** (not single-instance mode). Set minimum **1**, maximum **1** instances. A \`t3.large\` (2 vCPU/8 GiB) is a starting test size, **not guaranteed capacity** for heavy searches. Increase only after measurements.
3. Place the ALB in public subnets and the application EC2 instance in appropriately protected subnets. Configure VPC routing/outbound access needed to fetch images and update packages. Do not expose port 8000 directly to the internet.
4. After the Beanstalk instance security group exists, on the RDS security group allow **TCP 5432 from that specific Beanstalk instance security group only**.
5. In the Beanstalk configuration, set runtime environment **secrets** (source: Secrets Manager):
   * \`MIDSHIRE_DATABASE_URL\` -> secret ARN \`midshire/public/database-url\`
   * \`MIDSHIRE_SESSION_SECRET\` -> secret ARN \`midshire/public/session-secret\`
   Give the **EC2 instance profile IAM role** \`secretsmanager:GetSecretValue\` on those two secrets only. If they use a customer-managed KMS key, also grant the required \`kms:Decrypt\`.
6. The committed \`.ebextensions/01-midshire.config\` sets \`PORT=8000\`, \`MIDSHIRE_PUBLIC_MODE=1\`, \`MIDSHIRE_WORKERS=1\`, one running job and three queued jobs. It also directs health checks to \`/healthz\`. Do not override these with unsafe values.

**D. Add HTTPS and DNS before sharing the URL.**

1. ACM > request a public certificate for a subdomain you own, e.g. \`midshire-ed.example.com\`, and validate ownership via DNS.
2. On the Beanstalk **Application Load Balancer**, add an **HTTPS:443 listener** using that certificate, forwarding to the default target group (which uses HTTP to the instance). Redirect the HTTP:80 listener to HTTPS:443, or disable public HTTP.
3. Add a Route 53 alias/CNAME to the ALB/Beanstalk environment according to AWS instructions. The standard \`*.elasticbeanstalk.com\` hostname is **not** automatically covered by your ACM certificate; the custom domain is needed for trustworthy browser HTTPS.
4. Add a **regional AWS WAF web ACL** to the ALB with managed common-rule protection and a **source-IP-based rate rule**. Start in COUNT mode for tuning, then switch to blocking. Set alerts for 4xx/5xx and blocked requests. The application's cookie-based quotas are complementary, not a substitute for WAF IP controls.

**E. Configure a secure public data policy.**

Do not accept uploads containing patient identifiers. Treat saved scenario names and free-text notes as visitor-provided content. Publish a short privacy/retention note; maintain a process to expire old anonymous scenarios and model result cache. Before broader access, schedule retention cleanup (this branch does not yet provide an automated scheduled purge).

## 3. Deploy the Docker source via EB CLI

From **your local checkout** of the deployment branch:

\`\`\`bash
pipx install awsebcli
aws sts get-caller-identity
eb init
# Choose application midshire-ed, AWS region eu-west-2, Docker on Amazon Linux 2023.
eb create midshire-public --elb-type application --instance_type t3.large --min-instances 1 --max-instances 1
eb scale 1 midshire-public
eb deploy midshire-public
eb status midshire-public
\`\`\`

If you already created the environment in the console, **skip \`eb create\`** and use \`eb use midshire-public\`, then \`eb deploy\`. Set Secrets Manager references, RDS access and HTTPS before making the address public. The first deployment may report unhealthy until those prerequisites are set; check Beanstalk Events and CloudWatch Logs rather than turning public mode off.

Beanstalk builds the committed \`Dockerfile\`, whose WSGI command is:
\`\`\`
gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 120 'uec_hybrid.midshire.server:create_app()'
\`\`\`

For repeat deployments, first run the GitHub Actions \`MUH AWS public-demo readiness\` workflow on this branch (tests + container build), then \`eb deploy\`. The workflow **does not deploy to your AWS account**, so it requires no AWS credentials or GitHub secrets.

## 4. Public acceptance test

**Do not launch broadly until every check passes.**

1. \`https://<YOUR_HOST>/healthz\` returns \`{"status":"ok"}\`; the main page and \`/api/m/meta\` load.
2. Open two private/incognito browser sessions: create distinct scenarios in A and B, apply different ones, reset A; B is unchanged. A cannot retrieve B's ID via the API or download B's inputs.
3. The page loads prepared baseline/results quickly. A new run starts a visible job and eventually finishes; at most **one** expensive simulation is running per process.
4. Try four different browsers starting novel runs: one runs, up to three queue; a fifth receives HTTP **429**. Inaccessible or cancelled job IDs are not readable from another visitor.
5. A state-changing API request without the page's CSRF header returns **403**; session cookie has **Secure**, **HttpOnly**, **SameSite=Lax**.
6. Restart the Beanstalk instance: saved scenarios and completed results are still present (PostgreSQL); running jobs may need restarting (known limitation).
7. Confirm WAF association, HTTPS redirect, private RDS, CloudWatch alerts and database backup settings.
8. Inspect the model and data caveats visibly: fictional adult ED, synthetic patients, illustrative staffing/costs, not clinically validated.

## 5. Operational limits and next architecture step

This branch is designed for a **limited public pilot** with one web worker and one host, rather than a fully horizontally scaled platform.

* Public request limits per session: **240 requests/minute**, **12 run requests/hour**, **6 package searches/hour**, **40 assistant requests/hour**. Visitors can clear cookies; AWS WAF supplies source-IP enforcement.
* Maximum in-flight jobs: **one running + three queued**, and only one queued/running job per visitor. The worker job status remains in memory; after host restart, a new request must start unfinished runs again. Completed results remain in RDS.
* A true multi-instance deployment needs a durable job queue (Amazon SQS), separate worker service (ECS/Fargate), result store in PostgreSQL, and appropriate worker state persistence before increasing instance count.
* Prepared examples are the fastest way for groups to explore baseline, no-extra-resource and investment scenarios. Arbitrary new package searches may take substantial computation time.
* Editing the illustrative unit costs results in a separate full package search, rather than reusing the original priced package and potentially showing an inconsistent saved scenario; this may take additional time.

**Cost and removal:** Beanstalk uses EC2, ALB, RDS, Secrets Manager, WAF, CloudWatch and data transfer; all incur AWS charges. Set an AWS Budget alert. To remove the demo, terminate the Beanstalk environment, delete RDS only after backup/export decisions, and separately remove the ALB/WAF associations, DNS, secrets and other associated resources. Nothing is removed automatically from your account by this branch.

## AWS references

* [Docker on Elastic Beanstalk](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/docker.html)
* [EB CLI create options](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb3-create.html)
* [Runtime secrets from Secrets Manager](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.secrets.env-vars.html)
* [HTTPS on Elastic Beanstalk](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/configuring-https.html)
* [AWS App Runner availability change](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html)
