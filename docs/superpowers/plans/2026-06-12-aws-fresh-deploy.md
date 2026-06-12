# AWS Fresh-Account Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four hardcoded-from-old-account values in `infra/terraform/main.tf` so the project deploys cleanly on any fresh AWS account, then document the two-phase deploy procedure.

**Architecture:** All changes are confined to `infra/terraform/main.tf` (Terraform IaC) and `infra/terraform/deploy.bat` (deploy script). No application code changes. The ACM certificate must be created and DNS-validated in Phase 1 before the full infrastructure apply (Phase 2) because CloudFront requires an ISSUED cert to attach the custom domain.

**Tech Stack:** Terraform ≥ 1.5, AWS provider 5.x, PowerShell (Windows), AWS CLI v2

---

## File Map

| File | What changes |
|---|---|
| `infra/terraform/main.tf` | Add us-east-1 provider alias; add `aws_acm_certificate` resource; fix CloudFront `viewer_certificate`; fix Lambda `CF_DISTRIBUTION_ID` env var; add `data.aws_caller_identity`; fix IAM policy CloudFront ARN; add `certificate_validation_cname` output |
| `infra/terraform/deploy.bat` | Add clear warning + manual pre-step instructions at the top for fresh-account deploys |

---

## Pre-requisites (confirm before starting)

- `aws configure` done with the **new** account's credentials
- `aws sts get-caller-identity` returns a different account ID than `255325274897`
- Terraform ≥ 1.5 installed: `terraform version`
- Python 3 on PATH: `python --version`
- `infra/terraform/` is your working directory for all Terraform commands

---

## Task 1: Add us-east-1 Provider Alias

ACM certificates for CloudFront must be created in `us-east-1`. The main provider stays `ap-south-1`.

**Files:**
- Modify: `infra/terraform/main.tf` (after the existing `provider "aws"` block, around line 21)

- [ ] **Step 1: Add the provider alias block**

In `main.tf`, immediately after the existing `provider "aws" { region = "ap-south-1" }` block, add:

```hcl
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
```

- [ ] **Step 2: Validate syntax**

```powershell
cd infra\terraform
terraform init -upgrade
terraform validate
```

Expected output: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```powershell
git add infra/terraform/main.tf
git commit -m "infra: add us-east-1 provider alias for ACM cert"
```

---

## Task 2: Add ACM Certificate Resource

Replace the hardcoded cert ARN with a Terraform-managed cert. Terraform will create the cert and output the DNS CNAME the user must add to their registrar.

**Files:**
- Modify: `infra/terraform/main.tf` (add before the CloudFront distribution resource, around line 133)

- [ ] **Step 1: Add the ACM certificate resource**

In `main.tf`, add this block immediately before the `# CLOUDFRONT DISTRIBUTION` section comment:

```hcl
# ================================================================
# ACM CERTIFICATE — must be in us-east-1 for CloudFront
# ================================================================
resource "aws_acm_certificate" "website" {
  provider          = aws.us_east_1
  domain_name       = "www.nimishacreations.in"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = { Project = local.project }
}
```

- [ ] **Step 2: Validate syntax**

```powershell
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```powershell
git add infra/terraform/main.tf
git commit -m "infra: add aws_acm_certificate resource for www.nimishacreations.in"
```

---

## Task 3: Fix CloudFront viewer_certificate

Replace the hardcoded old-account cert ARN with a reference to the resource created in Task 2.

**Files:**
- Modify: `infra/terraform/main.tf` (inside `aws_cloudfront_distribution.website`, around line 189)

- [ ] **Step 1: Replace the viewer_certificate block**

Find and replace this exact block in the `aws_cloudfront_distribution "website"` resource:

```hcl
  viewer_certificate {
    acm_certificate_arn            = "arn:aws:acm:us-east-1:255325274897:certificate/f7cecec7-9802-4596-aa70-436ab2cee3e2"
    ssl_support_method             = "sni-only"
    minimum_protocol_version       = "TLSv1.2_2021"
  }
```

Replace with:

```hcl
  viewer_certificate {
    acm_certificate_arn            = aws_acm_certificate.website.arn
    ssl_support_method             = "sni-only"
    minimum_protocol_version       = "TLSv1.2_2021"
  }
```

- [ ] **Step 2: Validate syntax**

```powershell
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```powershell
git add infra/terraform/main.tf
git commit -m "infra: reference terraform-managed ACM cert in CloudFront"
```

---

## Task 4: Fix Lambda CF_DISTRIBUTION_ID Environment Variable

The Lambda function has the old CloudFront distribution ID hardcoded. Replace it with a Terraform reference so it always gets the correct ID after apply.

**Files:**
- Modify: `infra/terraform/main.tf` (inside `aws_lambda_function.order_handler` environment block, around line 368)

- [ ] **Step 1: Replace the hardcoded distribution ID**

Find this line in the `aws_lambda_function "order_handler"` environment variables block:

```hcl
      CF_DISTRIBUTION_ID   = "E22P6B24TXTI9X"
```

Replace with:

```hcl
      CF_DISTRIBUTION_ID   = aws_cloudfront_distribution.website.id
```

- [ ] **Step 2: Validate syntax**

```powershell
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```powershell
git add infra/terraform/main.tf
git commit -m "infra: replace hardcoded CF dist ID in Lambda env with terraform ref"
```

---

## Task 5: Fix IAM Policy CloudFront ARN

The Lambda IAM policy has a hardcoded account ID (`255325274897`) and distribution ID (`E22P6B24TXTI9X`) in the CloudFront invalidation permission. Fix both using Terraform data sources.

**Files:**
- Modify: `infra/terraform/main.tf` (add data source near top of file; fix IAM policy around line 331)

- [ ] **Step 1: Add the caller identity data source**

In `main.tf`, add this block immediately after the `locals { ... }` block (around line 31):

```hcl
data "aws_caller_identity" "current" {}
```

- [ ] **Step 2: Fix the CloudFront ARN in the IAM policy**

Find this line inside `aws_iam_role_policy "lambda_policy"` (in the Statement array):

```hcl
        Resource = "arn:aws:cloudfront::255325274897:distribution/E22P6B24TXTI9X"
```

Replace with:

```hcl
        Resource = "arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/${aws_cloudfront_distribution.website.id}"
```

- [ ] **Step 3: Validate syntax**

```powershell
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 4: Commit**

```powershell
git add infra/terraform/main.tf
git commit -m "infra: use caller identity data source to remove hardcoded account ID from IAM policy"
```

---

## Task 6: Add certificate_validation_cname Output

After Phase 1 apply, the user needs to know exactly which CNAME to add in their domain registrar. Add an output that prints it clearly.

**Files:**
- Modify: `infra/terraform/main.tf` (in the `# OUTPUTS` section at the bottom)

- [ ] **Step 1: Add the output**

In the `# OUTPUTS` section at the bottom of `main.tf`, add this block after the existing `output "cloudfront_url"` block:

```hcl
output "certificate_validation_cname" {
  description = "Add this CNAME record in your domain registrar to validate the ACM certificate"
  value = {
    name  = tolist(aws_acm_certificate.website.domain_validation_options)[0].resource_record_name
    value = tolist(aws_acm_certificate.website.domain_validation_options)[0].resource_record_value
    type  = tolist(aws_acm_certificate.website.domain_validation_options)[0].resource_record_type
  }
}
```

- [ ] **Step 2: Validate syntax**

```powershell
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```powershell
git add infra/terraform/main.tf
git commit -m "infra: add certificate_validation_cname output for DNS setup"
```

---

## Task 7: Add Fresh-Deploy Instructions to deploy.bat

Add a clearly visible comment block at the top of `deploy.bat` explaining the two-phase process for fresh-account deploys. The state deletion stays manual (automating it would destroy state on every run).

**Files:**
- Modify: `infra/terraform/deploy.bat` (add comment block after the `@echo off` line)

- [ ] **Step 1: Add the fresh-deploy comment block**

In `deploy.bat`, find the line:

```bat
@echo off
setlocal EnableDelayedExpansion
```

Replace with:

```bat
@echo off
setlocal EnableDelayedExpansion

REM ================================================================
REM  FRESH-ACCOUNT DEPLOY — read this if deploying to a new account
REM
REM  Before running this script for the first time on a new AWS account:
REM
REM  1. Configure AWS CLI with the new account credentials:
REM       aws configure
REM
REM  2. Delete old state files (ONLY on first deploy):
REM       del terraform.tfstate
REM       del terraform.tfstate.backup
REM
REM  3. Create the ACM certificate and get the DNS validation CNAME:
REM       terraform init
REM       terraform apply -target=aws_acm_certificate.website
REM
REM  4. Copy the "certificate_validation_cname" output values.
REM     Add that CNAME record in your domain registrar (GoDaddy, etc).
REM
REM  5. Wait for the cert status to become ISSUED (5-30 min):
REM       aws acm describe-certificate --certificate-arn <arn> --region us-east-1 --query "Certificate.Status"
REM
REM  6. Once ISSUED, run this script:
REM       .\deploy.bat
REM
REM  After first deploy, add a second CNAME in your registrar:
REM    Name:  www
REM    Value: <cloudfront_url output, without https://>
REM ================================================================

```

- [ ] **Step 2: Verify the bat file still runs without errors**

```powershell
# Dry-run check — just verify syntax by checking the first few lines parse
Get-Content infra\terraform\deploy.bat | Select-Object -First 40
```

Expected: the comment block and existing script steps are both visible, no truncation.

- [ ] **Step 3: Commit**

```powershell
git add infra/terraform/deploy.bat
git commit -m "infra: add fresh-account deploy instructions to deploy.bat"
```

---

## Task 8: Final Terraform Plan Verification

Run a full `terraform plan` to confirm all 4 fixes work together. This is the integration check — it catches any cross-resource reference issues that individual validates miss.

**Files:** None changed — verification only.

- [ ] **Step 1: Confirm AWS credentials are for the new account**

```powershell
aws sts get-caller-identity
```

Expected: your new account ID in the `Account` field (not `255325274897`).

- [ ] **Step 2: Delete old state files (if not already done)**

```powershell
cd infra\terraform
if (Test-Path terraform.tfstate) { Remove-Item terraform.tfstate }
if (Test-Path terraform.tfstate.backup) { Remove-Item terraform.tfstate.backup }
```

- [ ] **Step 3: Init and plan**

```powershell
terraform init -upgrade
terraform plan
```

Expected: Terraform shows a plan to create ~24 resources. Confirm:
- `aws_acm_certificate.website` is in the plan (not an import, a create)
- `aws_cloudfront_distribution.website` viewer_certificate references `aws_acm_certificate.website.arn`
- `aws_lambda_function.order_handler` env var `CF_DISTRIBUTION_ID` shows `(known after apply)` — not a hardcoded string
- No resource references account ID `255325274897`

- [ ] **Step 4: Exit plan without applying (Phase 1 comes next)**

Press `Ctrl+C` or just let the plan output finish — do NOT run `terraform apply` yet. Phase 1 is `terraform apply -target=aws_acm_certificate.website`, then DNS validation, then `.\deploy.bat`.

---

## Deployment Runbook (After All Tasks Complete)

This is the full sequence to go live. Run it after all 8 tasks above are committed.

**Phase 1 — Create cert, get validation CNAME**
```powershell
cd infra\terraform
del terraform.tfstate
del terraform.tfstate.backup
terraform init
terraform apply -target=aws_acm_certificate.website
```
Copy the `certificate_validation_cname` output. Add the CNAME in your registrar.

Check until ISSUED:
```powershell
aws acm describe-certificate --certificate-arn <arn from output> --region us-east-1 --query "Certificate.Status"
```

**Phase 2 — Deploy everything**
```powershell
.\deploy.bat
```
Press Enter when prompted for Razorpay keys (uses test keys from `main.tf`).

**Phase 3 — Point domain**

In your registrar, add:
- Name: `www`
- Type: `CNAME`
- Value: CloudFront URL from `terraform output cloudfront_url` (strip `https://`)

**Phase 4 — Verify SES**

Check `creationsnimisha51@gmail.com` inbox for AWS verification email. Click the link.

**Phase 5 — Smoke test**

Open `https://www.nimishacreations.in` → Shop → add product → Checkout.
Razorpay test card: `4111 1111 1111 1111` | expiry `12/28` | CVV `123`

Check the order landed in DynamoDB:
```powershell
aws dynamodb scan --table-name nimisha-orders --region ap-south-1 --query "Items[*].{ID:order_id.S,Status:status.S}" --output table
```
