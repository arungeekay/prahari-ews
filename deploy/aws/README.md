# Deploying PRAHARI on AWS at the lowest cost

PRAHARI is one container (FastAPI serving the built React app) with the seed-42 data and models
baked in. It needs about 2 GB of RAM at build time (one-off data generation and model training)
and well under that to serve. Traffic during evaluation is a handful of users. That profile makes
a single small always-on box the right shape; anything with load balancers, orchestration or
per-request billing costs more and adds failure modes for a live demo.

## Cheapest that is safe for a live demo

| Option | Approx. cost | Notes |
|---|---|---|
| **Lightsail instance, 2 GB RAM, 2 vCPU (Linux, bundle `small_3_1`)** | **about $12 per month (hourly billed, so about $6 for two weeks)** | Fixed price, static IP included, 2 TB transfer, no VPC or security-group work. Best choice. The $7 plan (1 GB) can serve the app but the one-off image build needs swap and is slow; confirm current prices with `aws lightsail get-bundles`. |
| EC2 t4g.small (2 vCPU, 2 GB, Graviton, ap-south-1) | about $12 per month | Same idea with more knobs. Choose it if you already have a VPC and key pair. |
| EC2 t3.micro under an eligible free tier | $0 | Only 1 GB RAM: the build needs swap and serving is tight. Workable, not comfortable. |
| The IDBI sandbox t3.medium, if it is ever granted | $0 to you | The requested spec in `submissions/Sandbox_Access_Request.md`. |

Not recommended for this: App Runner (always-on 1 vCPU 2 GB is about $56 per month), ECS Fargate
(about $15 per month plus about $16 for a load balancer), Lambda (30-second warm-up of the
portfolio tables on every cold start is the one thing a live demo cannot have).

## Lightsail from the CLI (one command)

With an AWS profile that carries `deploy/aws/iam-policy.json`:

```bash
AWS_PROFILE=prahari bash deploy/aws/lightsail-deploy.sh          # create, open ports, static IP, wait for health, print URL
AWS_PROFILE=prahari bash deploy/aws/lightsail-deploy.sh status
AWS_PROFILE=prahari bash deploy/aws/lightsail-deploy.sh destroy   # after 19 September
```

## Lightsail from the console in ten minutes

1. Lightsail console, Create instance, region Mumbai (ap-south-1), Linux, OS only, **Ubuntu 24.04**,
   plan **$12 (2 GB RAM, 2 vCPUs, 60 GB SSD)**; the $7 plan (1 GB) works only with the swap the script adds and a slower first build.
2. Expand "Add launch script" and paste `deploy/aws/userdata.sh` (copy it from GitHub's Raw view so the
   line endings stay Unix LF; a Windows editor may save CRLF, which breaks bash). If your public repo URL differs,
   change `REPO` at the top of the script first.
3. Create. Then Networking tab: add firewall rules for **HTTP 80** and **HTTPS 443** (SSH 22 is
   there by default). Attach a **static IP** (free while attached) so the address never changes.
4. Wait 5 to 10 minutes. The first boot installs Docker and builds the image, which generates the
   data and trains the models once. Then open

   `https://<static IP with dots replaced by dashes>.sslip.io`

   for example `https://13-233-10-20.sslip.io`. Caddy obtains a free Let's Encrypt certificate for
   that name automatically; no domain purchase is needed. `/api/health` must read `"status":"ok"`.
5. Put that URL on slide 13 and in the GitHub repo variable `PRAHARI_URL` (keep-alive is belt and
   braces here, the instance does not sleep).

If you have a real domain, set `PRAHARI_HOST=demo.yourdomain.in` at the top of the script and
point an A record at the static IP; Caddy will issue the certificate for it instead.

## EC2 instead of Lightsail

Same script as EC2 user data on an Ubuntu 24.04 AMI, instance type `t4g.small` (or `t3.small`
for x86), security group allowing 22, 80, 443, and an Elastic IP. Everything else is identical.

## Operating it

```bash
ssh ubuntu@<ip>
cd /opt/prahari
docker compose ps                      # both containers healthy
docker compose logs -f prahari         # application log
cat /var/log/prahari-url.txt           # the URL the script derived
# redeploy after pushing new code to GitHub (reset, not pull: survives a rewritten branch):
sudo git config --global --add safe.directory /opt/prahari/repo   # once per box
cd repo && sudo git fetch origin refined && sudo git reset --hard origin/refined && cd .. && sudo docker compose build && sudo docker compose up -d
```

Optional environment variables (add under `environment:` in `/opt/prahari/docker-compose.yml`):
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY` for LLM-polished documents; `DATA_SOURCE=idbi_sandbox`
with `IDBI_BASE_URL` and `IDBI_API_KEY` if the bank ever exposes its catalogue.

### Keys and state files
`deploy/aws/*.pem` (the instance SSH key), `.ec2-state-*` and `.userdata.lf.sh` are gitignored and
excluded by `scripts/publish.py`. If a key ever reaches a public repository, treat it as
compromised: install a new key on the instance (replace `~/.ssh/authorized_keys`), delete the EC2
key pair, and rewrite the branch. This happened once on 4 September 2026 and was handled that way
within minutes; the key that served the instance was rotated and the leaked one no longer works.

## Cost control

Lightsail bills hourly; delete the instance after the felicitation date (19 September) and the
charge stops. A snapshot before deleting costs about $0.05 per GB-month if you want to bring it
back later. The static IP is free while attached and about $0.005 per hour when detached, so
release it when you delete the instance.

## Step by step in the AWS console (one-time, about 15 minutes)

### A. Sign in and pick the region
1. Sign in at https://console.aws.amazon.com as the account owner (root) or an administrator.
2. If you sign in as root, first enable MFA on the root user: account menu (top right), Security
   credentials, Multi-factor authentication. Then never use root for day-to-day work.
3. Region selector (top right): choose **Asia Pacific (Mumbai) ap-south-1**. IAM is global; Lightsail
   is regional and the instance will live in Mumbai.

### A2. Redeem your AWS credits first
Do this before creating anything, so the very first charge is covered.
1. Search "Billing" in the top bar and open **Billing and Cost Management**.
2. Left menu **Credits** (under "Billing"). Click **Redeem credit**.
3. Enter the promotional code from the email, complete the security check, **Redeem**. Repeat for each
   code.
4. The Credits page now lists each credit with **Amount remaining**, **Expiration date** and
   **Applicable products**. Read the applicable-products line:
   - If it says "All services" or lists **Amazon Lightsail**, continue with Lightsail below.
   - If Amazon Lightsail is **not** listed (some promotional credits exclude it), use the EC2 path in
     section G instead: same launch script, same cost class, and EC2 is covered by every AWS credit.
5. Credits apply automatically to eligible usage on the monthly bill; there is nothing to attach to
   the instance. The account still needs a valid payment method on file for the redemption to be
   accepted. Bills, at the end of the month, will show the usage and a matching credit line.

### B. Create a least-privilege IAM user for the deployment
1. Search "IAM" in the top search bar, open **IAM**.
2. Left menu **Policies**, **Create policy**, tab **JSON**. Delete the default text and paste the
   contents of `deploy/aws/iam-policy.json`. **Next**. Policy name `PrahariLightsailDeploy`,
   description "Lightsail-only deployment of the PRAHARI demo". **Create policy**.
3. Left menu **Users**, **Create user**. User name `prahari-deployer`. Leave "Provide user access to
   the AWS Management Console" **unchecked** (this user is for the CLI only). **Next**.
4. Permissions options: **Attach policies directly**. Search `PrahariLightsailDeploy`, tick it.
   **Next**, **Create user**.
5. Open the user, tab **Security credentials**, section **Access keys**, **Create access key**.
   Use case **Command Line Interface (CLI)**, tick the confirmation box, **Next**, description
   "PRAHARI deploy laptop", **Create access key**.
6. The next page shows the **Access key** and the **Secret access key** once. Keep the page open for
   step C (or download the .csv and delete it afterwards). Do not paste them anywhere else.

### C. Configure the profile on this laptop
1. Open a new **PowerShell** window (not the Claude session).
2. Run:
   ```
   aws configure --profile prahari
   ```
   and answer the four prompts: the access key, the secret access key, default region `ap-south-1`,
   default output `json`. This writes `%USERPROFILE%\.aws\credentials` and `config`.
3. Verify:
   ```
   aws sts get-caller-identity --profile prahari
   aws lightsail get-bundles --profile prahari --region ap-south-1 --query "bundles[?supportedPlatforms[0]=='LINUX_UNIX'].[bundleId,price,ramSizeInGb,cpuCount]" --output table
   ```
   The first prints the account id and `user/prahari-deployer`; the second lists the Linux plans and
   current prices (confirm `small_3_1` is the 2 GB plan).
4. Close the IAM access-key page.

### D. Optional but sensible: a budget alert
Search "Billing", open **Billing and Cost Management**, **Budgets**, **Create budget**, template
"Monthly cost budget", amount 20 USD, your email. You will be told if anything unexpected accrues.

### E. Hand over
Tell the agent "profile prahari is ready". It will push the public repo (with your go-ahead), run
`deploy/aws/lightsail-deploy.sh`, and report the HTTPS URL once `/api/health` reads `ok`.

### F. After 19 September (clean up)
1. `AWS_PROFILE=prahari bash deploy/aws/lightsail-deploy.sh destroy` (or Lightsail console: delete
   the instance, then Networking, release the static IP).
2. IAM, Users, `prahari-deployer`, Security credentials, deactivate and delete the access key, then
   delete the user.
3. Check Billing, Bills, that the month's Lightsail charge is a few dollars and nothing else appears.

### G. EC2 path (use if your credits do not cover Lightsail, or Lightsail caps your plan size)
New AWS accounts are often limited to the smallest Lightsail plans: `CreateInstances` returns
"your account can not create an instance using this Lightsail plan size" for the 2 GB plan. The
EC2 path below has no such cap and was the route actually used for the September 2026 deployment.
Same launch script, same box size, covered by every AWS credit. The IAM policy in
`deploy/aws/iam-policy.json` already includes the EC2 permissions this needs.
```bash
AWS_PROFILE=prahari bash deploy/aws/ec2-deploy.sh            # key pair, security group, t4g.small, Elastic IP, wait for health, URL
AWS_PROFILE=prahari bash deploy/aws/ec2-deploy.sh status
AWS_PROFILE=prahari bash deploy/aws/ec2-deploy.sh destroy    # terminate and release the Elastic IP
```
Cost: t4g.small (2 vCPU, 2 GB, Graviton) is about $12 per month in Mumbai plus about $1 for the
8 GB root volume, hourly billed. The Elastic IP is free while attached to a running instance.
