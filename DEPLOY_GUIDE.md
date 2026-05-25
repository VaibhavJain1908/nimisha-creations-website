# Seven Hills Packaging — Complete Deployment Guide

---

## Your Project Files at a Glance

```
seven-hills-v2/
│
├── website/                     ← Upload ALL 4 files to S3
│   ├── index.html               Page 1: Landing page (home)
│   ├── shop.html                Page 2: Product catalog + cart
│   ├── product.html             Page 3: Box configurator (L×W×H, ply, print)
│   └── checkout.html            Page 4: Checkout + Razorpay payment
│
└── infra/
    ├── lambda/
    │   └── order_handler.py     Backend: orders, Razorpay, emails
    └── terraform/
        ├── main.tf              All AWS infrastructure as code
        └── deploy.sh            One-shot deploy script
```

**How the pages connect:**
```
index.html  →  shop.html  →  product.html  →  checkout.html
(home)         (catalog)     (configure box)   (pay via Razorpay)
                    ↓
             (bags/labels/protective → configure inline → checkout.html)
```

---

## What You Need Before Starting

### 1. AWS Account
You already have this. Confirm you have IAM permissions for:
S3, CloudFront, Lambda, API Gateway, DynamoDB, SES, Secrets Manager, IAM, CloudWatch

### 2. AWS CLI configured
```bash
aws configure
# Enter your:
# AWS Access Key ID
# AWS Secret Access Key
# Default region:        ap-south-1
# Default output format: json

# Verify it works:
aws sts get-caller-identity
```

### 3. Terraform installed
```bash
# macOS:
brew install terraform

# Ubuntu/Amazon Linux:
sudo apt-get update && sudo apt-get install -y terraform
# OR download from https://developer.hashicorp.com/terraform/downloads

# Verify:
terraform version   # should be >= 1.5
```

### 4. Razorpay Live Keys
1. Login → https://dashboard.razorpay.com
2. Go to **Settings → API Keys**
3. Switch to **Live Mode** (toggle top-left)
4. Click **Generate Live Key**
5. Copy and save both:
   - **Key ID**: starts with `rzp_live_...`
   - **Key Secret**: shown only once — save it immediately

> For testing first, use **Test Mode** keys (`rzp_test_...`).  
> Test card: `4111 1111 1111 1111` · Any future expiry · CVV `123`  
> Test UPI: `success@razorpay`

---

## Step 1 — Personalise Your Files

Open each file and replace these placeholders:

### `website/index.html`
```
Search for → Replace with
+91 708-071-4711          → Your real phone number
sevenhills907@gmail.com  → Your real email
```

### `website/checkout.html`
```
Search for → Replace with
rzp_live_YOUR_KEY_ID     → Your Razorpay Live Key ID  (e.g. rzp_live_AbCdEf123456)
+917080714711            → Your WhatsApp number (in the WhatsApp URL)
```

### `website/product.html`
```
Search for → Replace with
+917080714711            → Your WhatsApp number (in the wa.me URL)
```

### `infra/terraform/main.tf`
```
Search for → Replace with
sevenhills907@gmail.com     → Your real email (owner_email variable)
sevenhills907@gmail.com  → Your sender email (sender_email variable)
sevenhills907@gmail.com           → Your actual domain
```

---

## Step 2 — Deploy Infrastructure

```bash
cd infra/terraform
chmod +x deploy.sh
```

Run the full deploy:
```bash
./deploy.sh
```

It will prompt you for your Razorpay keys:
```
Razorpay Key ID (rzp_live_...): rzp_live_xxxxxxxxxxxxxxxx
Razorpay Key Secret: xxxxxxxxxxxxxxxxxxxxxxxx
```

Or pass them as environment variables (better for CI/CD):
```bash
export TF_VAR_razorpay_key_id="rzp_live_xxxxxxxx"
export TF_VAR_razorpay_key_secret="your_secret_here"
./deploy.sh
```

**What the deploy script does (in order):**
1. `terraform init` — downloads AWS provider plugin
2. `terraform plan` — shows what will be created (review this)
3. `terraform apply` — creates all AWS resources (~3–5 minutes)
4. Reads output values (S3 bucket name, CloudFront URL, API URL)
5. Injects the API Gateway URL into `checkout.html` automatically
6. Uploads all 4 HTML files to S3 with correct cache headers
7. Invalidates CloudFront cache so changes go live immediately

**At the end you'll see:**
```
✅  SEVEN HILLS PACKAGING LIVE!
    Website:  https://d1xxxxxxxxxxxx.cloudfront.net
    API:      https://xxxxxxxxxx.execute-api.ap-south-1.amazonaws.com/prod
    Bucket:   seven-hills-website-prod
```

Open the CloudFront URL in your browser — your site is live.

---

## Step 3 — Verify SES Emails

After deploy, AWS SES will send verification emails to both addresses.

**Check your inbox** for emails from AWS and click the verification links for:
- `sevenhills907@gmail.com` (or whatever you set as owner_email)
- `sevenhills907@gmail.com` (or your sender_email)

Verify the status:
```bash
aws ses get-identity-verification-attributes \
  --identities sevenhills907@gmail.com sevenhills907@gmail.com \
  --region ap-south-1
```

Both should show `"VerificationStatus": "Success"`.

### Move SES out of Sandbox (IMPORTANT for production)

By default SES is in **sandbox mode** — emails only go to verified addresses.  
To send to any customer email you must request production access:

1. AWS Console → **SES** → **Account Dashboard**
2. Click **Request Production Access**
3. Fill in the form (takes 24–48 hours to approve)

Until approved, the quote and order confirmation emails will only work for verified addresses.

---

## Step 4 — Test Everything End to End

### Test the website
```
1. Open your CloudFront URL
2. Click "Shop" → you see the product catalog
3. For bags/labels → select a size or enter dimensions → Add to Cart
4. For boxes → click "Configure & Buy" → set L×W×H → Add to Cart
5. Cart drawer opens with correct totals
6. Click "Proceed to Checkout"
7. Fill in the checkout form
```

### Test Razorpay payment (use Test Mode first)
```
1. Use rzp_test_ keys during testing
2. Open checkout.html → fill form → click "Pay Securely"
3. Razorpay modal opens
4. Use test card: 4111 1111 1111 1111 | expiry: 12/28 | CVV: 123
5. Payment succeeds → order confirmation screen shows
6. Check DynamoDB for the order record
7. Check your email for the order notification
```

### Verify order saved in DynamoDB
```bash
aws dynamodb scan \
  --table-name seven-hills-orders \
  --region ap-south-1 \
  --query 'Items[*].{Order:order_id.S, Total:total.S, Status:status.S, Name:contact.M.name.S}' \
  --output table
```

### Watch Lambda logs live
```bash
aws logs tail /aws/lambda/seven-hills-order-handler \
  --follow \
  --region ap-south-1
```

---

## Step 5 — Set Up Custom Domain (Optional but recommended)

### Option A — Domain registered in Route 53

```bash
# 1. Request ACM certificate (MUST be us-east-1 for CloudFront)
aws acm request-certificate \
  --domain-name sevenhills907@gmail.com \
  --subject-alternative-names "*.sevenhills907@gmail.com" \
  --validation-method DNS \
  --region us-east-1

# 2. Get the CNAME record AWS needs you to add
aws acm describe-certificate \
  --certificate-arn arn:aws:acm:us-east-1:XXXX:certificate/XXXX \
  --region us-east-1 \
  --query 'Certificate.DomainValidationOptions'

# 3. Add the CNAME to Route 53 (or your DNS provider)
# 4. Wait for validation (5–30 minutes)

# 5. Once cert is ISSUED, edit main.tf:
# Uncomment the 'aliases' block in the CloudFront distribution
# Uncomment the 'viewer_certificate' block with your ACM cert ARN
# Comment out cloudfront_default_certificate = true

# 6. Re-deploy infrastructure only:
./deploy.sh infra
```

### Option B — Domain registered elsewhere (GoDaddy, Bigrock, etc.)

Same steps above, but in step 3 add the CNAME records in your registrar's DNS panel instead of Route 53.

---

## Step 6 — Update Website Content

Any time you change an HTML file:

```bash
# From infra/terraform directory:
./deploy.sh website

# This uploads changed files and clears CloudFront cache
# Site is updated within ~30 seconds
```

---

## Day-to-Day Operations

### View all orders
```bash
aws dynamodb scan \
  --table-name seven-hills-orders \
  --region ap-south-1 \
  --output json | python3 -m json.tool
```

### View all quote leads
```bash
aws dynamodb scan \
  --table-name seven-hills-leads \
  --region ap-south-1 \
  --output json | python3 -m json.tool
```

### Update Lambda code (after editing order_handler.py)
```bash
cd infra/terraform
./deploy.sh infra   # Terraform detects the code change and re-deploys Lambda
```

### Update product prices (edit PRODUCTS array in shop.html)
```bash
# Edit shop.html, then:
./deploy.sh website
```

### Check Lambda errors
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/seven-hills-order-handler \
  --filter-pattern "ERROR" \
  --region ap-south-1
```

---

## Monthly Cost Estimate

| Service          | Free Tier          | Estimated Cost      |
|------------------|--------------------|---------------------|
| CloudFront       | 1TB/month free     | ₹0–₹400/month       |
| S3               | 5GB free           | < ₹10/month         |
| Lambda           | 1M requests free   | ₹0 (startup scale)  |
| API Gateway      | 1M requests free   | ₹0 (startup scale)  |
| DynamoDB         | 25GB free          | ₹0 (startup scale)  |
| Secrets Manager  | —                  | ₹6/secret/month     |
| SES              | 62,000 emails free | ~₹0.08/1000 emails  |
| **Total**        |                    | **₹10–₹500/month**  |

Razorpay: 2% per transaction + ₹3 fixed (domestic UPI/cards).

---

## Troubleshooting

### "terraform: command not found"
```bash
# Install Terraform from https://developer.hashicorp.com/terraform/downloads
# Verify: terraform version
```

### "Error: No valid credential sources found"
```bash
aws configure   # re-enter your AWS keys
aws sts get-caller-identity   # verify it works
```

### "BucketAlreadyExists" error
The S3 bucket name must be globally unique. Edit `main.tf`:
```hcl
locals {
  bucket_name = "seven-hills-website-prod-yourname"  # add something unique
}
```

### Site shows old version after update
```bash
# Manually invalidate CloudFront:
aws cloudfront create-invalidation \
  --distribution-id YOUR_CF_DIST_ID \
  --paths "/*" \
  --region ap-south-1
```

### Razorpay modal doesn't open
- Check browser console for errors
- Confirm `rzp_live_YOUR_KEY_ID` in checkout.html is replaced with actual key
- Confirm `https://checkout.razorpay.com/v1/checkout.js` loads (check network tab)
- If testing, use `rzp_test_` key, not `rzp_live_`

### Orders not saving / emails not sending
```bash
# Check Lambda logs:
aws logs tail /aws/lambda/seven-hills-order-handler --follow --region ap-south-1

# Common cause: SES email not verified
# Check:
aws ses get-identity-verification-attributes \
  --identities sevenhills907@gmail.com \
  --region ap-south-1
```

### Destroy everything (if needed)
```bash
cd infra/terraform
terraform destroy
# Warning: deletes ALL resources including S3 bucket and all data
```

---

## Quick Reference Card

| Task                        | Command                                  |
|-----------------------------|------------------------------------------|
| Full deploy (first time)    | `./deploy.sh`                            |
| Update website files only   | `./deploy.sh website`                    |
| Update infra only           | `./deploy.sh infra`                      |
| View live Lambda logs       | `aws logs tail /aws/lambda/seven-hills-order-handler --follow --region ap-south-1` |
| View all orders             | `aws dynamodb scan --table-name seven-hills-orders --region ap-south-1`            |
| View all leads              | `aws dynamodb scan --table-name seven-hills-leads --region ap-south-1`             |
| Invalidate CF cache         | `aws cloudfront create-invalidation --distribution-id ID --paths "/*"`             |
| Destroy all AWS resources   | `terraform destroy`                      |
