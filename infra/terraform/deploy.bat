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

set PATH=C:\Program Files\Amazon\AWSCLIV2;%PATH%
set REGION=ap-south-1
set WEBSITE_DIR=..\..\website
set BUCKET_NAME=nimisha-creations-web-2026

set CHECKPOINT_DISABLE=1
set TF_PLUGIN_CACHE_DIR=%APPDATA%\terraform.d\plugin-cache
if not exist "%TF_PLUGIN_CACHE_DIR%" mkdir "%TF_PLUGIN_CACHE_DIR%"

echo.
echo =====================================================
echo   Nimisha Creations - Deploy Script
echo =====================================================
echo.

echo [STEP 1/9] Checking AWS CLI...
aws --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] AWS CLI not found.
    exit /b 1
)
echo [OK] AWS CLI found.

echo [STEP 2/9] Checking Terraform...
terraform --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Terraform not found.
    exit /b 1
)
echo [OK] Terraform found.

echo [STEP 3/9] Verifying AWS credentials...
set AWS_PAGER=
aws sts get-caller-identity --region %REGION% >nul 2>&1
if errorlevel 1 (
    echo [ERROR] AWS credentials not working. Run: aws configure
    exit /b 1
)
echo [OK] AWS credentials OK.

echo [STEP 4/9] Razorpay keys...
echo.
echo TEST keys are set in main.tf (safe for development).
echo Press Enter to use test keys, or type your live Key ID.
echo.
set /p INPUT_KEY="  Razorpay Key ID [Enter = use test default]: "
if not "!INPUT_KEY!"=="" (
    set TF_VAR_razorpay_key_id=!INPUT_KEY!
    set /p TF_VAR_razorpay_key_secret="  Razorpay Key Secret: "
    echo [OK] Live keys set.
) else (
    echo [OK] Using built-in test keys.
)

echo.
echo [STEP 5/9] Running terraform init...
terraform init -upgrade
if errorlevel 1 (
    echo [ERROR] terraform init failed.
    exit /b 1
)
echo [OK] Terraform init complete.

echo.
echo [STEP 6/9] Running terraform plan and apply...
terraform plan -out=tfplan
if errorlevel 1 (
    echo [ERROR] terraform plan failed.
    exit /b 1
)
terraform apply tfplan
if errorlevel 1 (
    echo [ERROR] terraform apply failed.
    exit /b 1
)
if exist tfplan del /f tfplan
echo [OK] Infrastructure deployed.

echo.
echo.
echo [STEP 7/9] Running pre-deploy audit...
python "%~dp0..\..\audit_all.py"
if errorlevel 1 (
    echo [ERROR] Audit failed - fix issues before deploying.
    exit /b 1
)
echo [OK] Audit passed.

echo [STEP 8/9] Reading Terraform outputs...
for /f "delims=" %%i in ('terraform output -raw cloudfront_url 2^>nul') do set CF_URL=%%i
for /f "delims=" %%i in ('terraform output -raw s3_bucket 2^>nul') do set BUCKET=%%i
for /f "delims=" %%i in ('terraform output -raw cf_dist_id 2^>nul') do set CF_ID=%%i
for /f "delims=" %%i in ('terraform output -raw api_base_url 2^>nul') do set API_URL=%%i

if "!CF_URL!"=="" (
    echo [ERROR] Could not read Terraform outputs.
    exit /b 1
)
echo [OK] CF URL  : !CF_URL!
echo [OK] API URL : !API_URL!
echo [OK] Bucket  : !BUCKET!

echo.
echo [STEP 9/9] Uploading website files...
set PATCH_DIR=C:\nimisha_deploy
if exist "!PATCH_DIR!" rmdir /S /Q "!PATCH_DIR!"
mkdir "!PATCH_DIR!"
xcopy /E /I /Q "%WEBSITE_DIR%\*" "!PATCH_DIR!\" >nul

powershell -NoProfile -Command "(Get-Content 'C:\nimisha_deploy\checkout.html' -Raw) -replace 'https://YOUR_API_GATEWAY_URL/prod','!API_URL!' | Set-Content 'C:\nimisha_deploy\checkout.html' -Encoding UTF8"
if errorlevel 1 (
    echo [ERROR] Failed to patch checkout.html
    exit /b 1
)
echo [OK] checkout.html patched.

aws s3 sync C:\nimisha_deploy\ s3://!BUCKET!/ --region %REGION% --delete --exclude "*" --include "*.html" --cache-control "max-age=300, must-revalidate" --content-type "text/html"
if errorlevel 1 (
    echo [ERROR] S3 HTML upload failed.
    exit /b 1
)

aws s3 sync C:\nimisha_deploy\ s3://!BUCKET!/images/ --region %REGION% --exclude "*.html" --exclude "*.bak"
if errorlevel 1 (
    echo [ERROR] S3 assets upload failed.
    exit /b 1
)

rmdir /S /Q "C:\nimisha_deploy" >nul 2>&1
echo [OK] Files uploaded to S3.

echo [INFO] Invalidating CloudFront cache (30-60 sec)...
for /f "delims=" %%i in ('aws cloudfront create-invalidation --distribution-id !CF_ID! --paths "/*" --query Invalidation.Id --output text 2^>nul') do set INVID=%%i
if "!INVID!"=="" (
    echo [WARN] Cache invalidation skipped.
) else (
    aws cloudfront wait invalidation-completed --distribution-id !CF_ID! --id !INVID!
    echo [OK] Cache cleared.
)

echo.
echo =====================================================
echo   NIMISHA CREATIONS IS LIVE!
echo   Website : !CF_URL!
echo   API     : !API_URL!
echo   Bucket  : !BUCKET!
echo   Admin   : !CF_URL!/admin.html
echo =====================================================
echo.
echo [NEXT] Check creationsnimisha51@gmail.com for SES verification email.
echo [NEXT] Login to admin: !CF_URL!/admin.html
echo [NEXT] Default login: admin / nimisha2025
echo [NEXT] Add your products from the admin panel.
echo.
