# Nimisha Creations — Fresh AWS Deployment Design

**Date:** 2026-06-12
**Goal:** Deploy the Nimisha Creations website on a fresh AWS account, free of cost, with the custom domain `www.nimishacreations.in`.

---

## 1. Infrastructure Overview

All resources are provisioned via Terraform in `ap-south-1` (Mumbai). Every service used falls within the AWS Free Tier.

| Service | Purpose | Free Tier |
|---|---|---|
| S3 | Stores HTML pages and product images | 5 GB free |
| CloudFront | CDN — global delivery, HTTPS termination | 1 TB / 10M requests/month free |
| API Gateway (HTTP) | Public URL for Lambda backend | 1M calls/month free |
| Lambda (Python 3.12) | Handles orders, Razorpay payments, email | 1M requests / 400K GB-s free |
| DynamoDB | `nimisha-orders` and `nimisha-products` tables | 25 GB free |
| SSM Parameter Store | Stores Razorpay key ID + secret (SecureString) | Free (standard parameters) |
| SES | Sends order confirmation emails | 62K emails/month free (from Lambda) |
| ACM Certificate | TLS cert for `www.nimishacreations.in` | Always free |

**Estimated monthly cost: ₹0** at startup scale. Razorpay charges 2% + ₹3 per transaction.

---

## 2. Code Changes Required in `main.tf`

The existing `main.tf` has three values hardcoded from the previous AWS account deployment. These must be fixed before Terraform can run on a fresh account.

### Fix 1 — ACM Certificate (new Terraform resource)

**Problem:** `viewer_certificate` block references a hardcoded `acm_certificate_arn` from the old account. That cert doesn't exist on the new account.

**Solution:** Add a `provider "aws" { alias = "us_east_1" }` block and a new `aws_acm_certificate` resource. Update the CloudFront `viewer_certificate` block to reference `aws_acm_certificate.website.arn`. Add a Terraform output `certificate_validation_cname` that prints the CNAME record the user must add to their DNS.

The ACM cert must be created in `us-east-1` (CloudFront requirement). The main provider stays `ap-south-1`.

Deployment is two-phase: Phase 1 creates the cert and prints the validation CNAME → user adds it to DNS and waits for ISSUED → Phase 2 runs the full deploy (CloudFront is created only after the cert is already valid).

### Fix 2 — CloudFront Distribution ID in Lambda Environment

**Problem:** `CF_DISTRIBUTION_ID = "E22P6B24TXTI9X"` is hardcoded in the Lambda `environment` block. The new deployment will create a different distribution ID.

**Solution:** Replace with `aws_cloudfront_distribution.website.id` so it always references whatever Terraform creates.

### Fix 3 — Account ID in IAM Policy

**Problem:** The IAM policy for Lambda's CloudFront invalidation permission hardcodes the old account's ID: `arn:aws:cloudfront::255325274897:distribution/E22P6B24TXTI9X`.

**Solution:** Add `data "aws_caller_identity" "current" {}` and replace the hardcoded ARN with `"arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/${aws_cloudfront_distribution.website.id}"`.

### Fix 4 — Clear Old Terraform State

**Problem:** `terraform.tfstate` and `terraform.tfstate.backup` reference resources on the old account. Running `terraform apply` with stale state will cause errors or attempt to modify non-existent resources.

**Solution:** Delete both state files before running `terraform init`. Terraform will treat this as a brand-new deployment.

---

## 3. Step-by-Step Deployment

### Pre-requisites (one-time setup)

1. **AWS credentials for the new account**
   - AWS Console → IAM → Users → your user → Security credentials → Create access key
   - Choose "CLI" as the use case, copy Key ID and Secret

2. **Configure AWS CLI**
   ```
   aws configure
   ```
   Enter: Key ID, Secret, region `ap-south-1`, output format `json`

3. **Verify credentials work**
   ```
   aws sts get-caller-identity
   ```
   Should return your new account ID, not `255325274897`.

4. **Python 3 on PATH** — required by `audit_all.py` which runs during deploy.

### Deploy

Deployment is a two-phase process because the ACM certificate must be DNS-validated before CloudFront can use it.

**Phase 1 — Create the ACM certificate (manual step)**

Delete the old Terraform state first:
```
cd infra\terraform
del terraform.tfstate
del terraform.tfstate.backup
terraform init
terraform apply -target=aws_acm_certificate.website
```

After this completes, Terraform will print a `certificate_validation_cname` output — a CNAME name and value. Add that CNAME record in your domain registrar (GoDaddy, Bigrock, Hostinger, etc.). Then wait 5–30 minutes for AWS to validate the cert.

Check validation status:
```
aws acm describe-certificate --certificate-arn <arn from output> --region us-east-1 --query "Certificate.Status"
```
Wait until it returns `"ISSUED"`.

**Phase 2 — Deploy everything**

Once the cert is `ISSUED`, run:
```
.\deploy.bat
```

The script does these steps automatically:
1. Checks AWS CLI, Terraform, and credentials
2. Prompts for Razorpay keys — press Enter to use the test keys already in `main.tf`
3. `terraform apply` — creates all remaining AWS resources (~5 minutes)
4. Runs `audit_all.py` pre-deploy checks
5. Patches `checkout.html` with the new API Gateway URL
6. Uploads all website files to S3
7. Invalidates CloudFront cache

### Post-Deploy: Domain & Email (one-time)

**Point Domain to CloudFront**

**Point Domain to CloudFront**
- After `deploy.bat` finishes, add a second CNAME in your domain registrar:
  - Name: `www`
  - Value: the CloudFront URL from `terraform output cloudfront_url` (without `https://`)

**SES Email Verification**
- AWS will send a verification email to `creationsnimisha51@gmail.com`
- Click the link in that email to verify the sender address
- Without this, order confirmation emails will not send

**Test the Site**
- Open `www.nimishacreations.in` in a browser
- Browse to Shop, add a product, go through checkout with Razorpay test card `4111 1111 1111 1111`
- Check DynamoDB `nimisha-orders` table for the test order record
- Check email for the order notification

---

## 4. What You Need (Checklist)

- [ ] New AWS account with IAM user + Access Key
- [ ] Python 3 installed and on PATH
- [ ] Access to DNS settings for `nimishacreations.in` (to add 2 CNAME records)
- [ ] `creationsnimisha51@gmail.com` accessible (for SES verification email)
- [ ] Razorpay live keys when ready for production (test keys are already in `main.tf`)

---

## 5. Error Handling & Known Issues

**S3 bucket name conflict** — `nimisha-creations-website-prod` must be globally unique. If another account already holds this name, Terraform will fail with `BucketAlreadyExists`. Fix: add a suffix to `bucket_name` in `locals` (e.g., `nimisha-creations-website-2026`).

**SES sandbox mode** — By default SES only sends to verified email addresses. To send to any customer email, request production access: AWS Console → SES → Account Dashboard → Request Production Access. Takes 24–48 hours. Until then, order emails only work for verified addresses.

**CloudFront takes time** — The distribution takes 5–10 minutes to fully deploy globally. The site may show errors briefly right after `terraform apply`.
