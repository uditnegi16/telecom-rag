# Deploying the live demo

Target: a public URL a recruiter can open and use immediately, with a hard
8-question cap so a shared free-tier Groq key is not drained by one visitor.

Two options. **EC2** is recommended — you can stop the instance between
demos, which is the same pattern used for the earlier project.

---

## Option A — EC2 + Docker (recommended)

### 1. Launch
- AMI: **Ubuntu 24.04 LTS**
- Type: **t3.small** (2 GB RAM). *t3.micro is not enough: the cross-encoder
  and embedding model together need well over 1 GB resident.*
- Storage: **20 GB** gp3 (the image is ~3 GB with baked model weights)
- Security group inbound: **22** from your IP, **80** from `0.0.0.0/0`
- Key pair: create or reuse one

### 2. Install Docker
```bash
ssh -i your-key.pem ubuntu@<PUBLIC_IP>
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu && newgrp docker
```

### 3. Deploy
```bash
git clone https://github.com/uditnegi16/telecom-rag.git
cd telecom-rag
echo "GROQ_API_KEY=gsk_your_key_here" > .env
```

**The index must exist before the container starts.** Either commit
`data/processed/` to the repo, or build it on the instance:
```bash
# only if data/processed/ is not committed - needs the PDFs present
python3 -m scripts.ingest
```

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
docker compose -f deploy/docker-compose.prod.yml logs -f
```

First build takes ~10 minutes (torch plus baked model weights).

Live at `http://<PUBLIC_IP>`.

### 4. Cost control
```bash
# stop when not demoing - storage only, ~$2/month
aws ec2 stop-instances --instance-ids i-xxxxx
aws ec2 start-instances --instance-ids i-xxxxx
```
A stopped t3.small costs nothing in compute. Running is roughly $0.02/hour.

**The public IP changes on restart.** Attach an Elastic IP if the link must
stay stable — free while attached to a running instance.

---

## Option B — AWS App Runner

Less operational work, no SSH, HTTPS and a stable URL out of the box. Costs
more because it does not scale to zero.

```bash
aws ecr create-repository --repository-name telecom-rag
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin <ACCT>.dkr.ecr.ap-south-1.amazonaws.com
docker build -t telecom-rag .
docker tag telecom-rag:latest <ACCT>.dkr.ecr.ap-south-1.amazonaws.com/telecom-rag:latest
docker push <ACCT>.dkr.ecr.ap-south-1.amazonaws.com/telecom-rag:latest
```
Then App Runner → create service → ECR image → port **8501** → add
`GROQ_API_KEY` as an environment variable → 1 vCPU / 2 GB.

---

## Before sharing the link

- [ ] `GROQ_API_KEY` set as an environment variable, **never committed**
- [ ] Ask 9 questions in one browser and confirm the 9th is refused
- [ ] Confirm `/api/v1/quota` reports sane counts
- [ ] Ask one out-of-corpus question and confirm it abstains with evidence shown
- [ ] Check the corpus panel lists the two specs correctly
- [ ] Open on a phone — recruiters will

## Quota design

| Control | Value | Purpose |
|---|---|---|
| Per visitor | 8 questions | Stops one person draining the day |
| Global daily | 300 questions | Backstop against cookie clearing |
| Enforcement | Server-side | A client-side counter is a suggestion |
| Identity | Session cookie | Fair-use accounting, **not** a security boundary |

Both limits are environment variables (`DEMO_QUESTION_LIMIT`,
`DEMO_GLOBAL_DAILY_CAP`), so they can be raised for a live interview without
a rebuild.
