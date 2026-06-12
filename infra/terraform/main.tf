# ================================================================
# Nimisha Creations — AWS Infrastructure
# Region: ap-south-1 (Mumbai)
# ================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "5.100.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "2.7.0"
    }
  }
}

provider "aws" {
  region = "ap-south-1"
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

locals {
  project      = "nimisha-creations"
  bucket_name  = "nimisha-creations-website-prod"
  lambda_name  = "nimisha-order-handler"
  orders_table = "nimisha-orders"
  owner_email  = "creationsnimisha51@gmail.com"
  api_stage    = "prod"
}

data "aws_caller_identity" "current" {}

# ================================================================
# S3 BUCKET
# ================================================================
resource "aws_s3_bucket" "website" {
  bucket        = local.bucket_name
  force_destroy = true
  tags          = { Project = local.project }
}

resource "aws_s3_bucket_public_access_block" "website" {
  bucket                  = aws_s3_bucket.website.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "website" {
  bucket = aws_s3_bucket.website.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "website" {
  bucket = aws_s3_bucket.website.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ================================================================
# CLOUDFRONT OAC
# ================================================================
resource "aws_cloudfront_origin_access_control" "website" {
  name                              = "${local.project}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_s3_bucket_policy" "website" {
  bucket = aws_s3_bucket.website.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CloudFrontRead"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.website.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.website.arn
          }
        }
      },
      {
        Sid       = "LambdaImageUpload"
        Effect    = "Allow"
        Principal = { AWS = aws_iam_role.lambda_exec.arn }
        Action    = ["s3:PutObject", "s3:GetObject"]
        Resource  = "${aws_s3_bucket.website.arn}/images/*"
      }
    ]
  })
  depends_on = [aws_cloudfront_distribution.website]
}


# ================================================================
# CLOUDFRONT FUNCTION — URL rewriter (removes .html from URLs)
# ================================================================
resource "aws_cloudfront_function" "url_rewrite" {
  name    = "${local.project}-url-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrite clean URLs to .html files"
  publish = true
  code    = <<-JS
    async function handler(event) {
      var request = event.request;
      var uri = request.uri;
      // If no extension and not root, append .html
      if (!uri.includes('.') && uri !== '/') {
        if (uri.endsWith('/')) {
          request.uri = uri + 'index.html';
        } else {
          request.uri = uri + '.html';
        }
      }
      return request;
    }
  JS
}

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

# ================================================================
# CLOUDFRONT DISTRIBUTION
# ================================================================
resource "aws_cloudfront_distribution" "website" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_200"
  comment             = "Nimisha Creations Website"

  origin {
    domain_name              = aws_s3_bucket.website.bucket_regional_domain_name
    origin_id                = "s3-${local.bucket_name}"
    origin_access_control_id = aws_cloudfront_origin_access_control.website.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-${local.bucket_name}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 31536000
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.url_rewrite.arn
    }
  }

  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  aliases = ["www.nimishacreations.in"]

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.website.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = { Project = local.project }
}

# ================================================================
# DYNAMODB — ORDERS
# ================================================================
resource "aws_dynamodb_table" "orders" {
  name         = local.orders_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "order_id"

  attribute {
    name = "order_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = { Project = local.project }
}

# ================================================================
# DYNAMODB — PRODUCTS
# ================================================================
resource "aws_dynamodb_table" "products" {
  name         = "nimisha-products"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  tags = { Project = local.project }
}

# ================================================================
# SSM PARAMETERS — RAZORPAY KEYS (free tier)
# ================================================================
variable "razorpay_key_id" {
  description = "Razorpay API key ID"
  default     = "rzp_live_St9JtL0PEpOWKT"
}

variable "razorpay_key_secret" {
  description = "Razorpay API key secret"
  sensitive   = true
  default     = "8X7BRNWLKYyse5gKprvANhTC" #_RAZORPAY_SECRET"
}

resource "aws_ssm_parameter" "razorpay_key_id" {
  name  = "/nimisha/razorpay/key_id"
  type  = "String"
  value = var.razorpay_key_id
  tags  = { Project = local.project }
}

resource "aws_ssm_parameter" "razorpay_key_secret" {
  name  = "/nimisha/razorpay/key_secret"
  type  = "SecureString"
  value = var.razorpay_key_secret
  tags  = { Project = local.project }
}

# ================================================================
# SES EMAIL IDENTITY
# ================================================================
resource "aws_ses_email_identity" "owner" {
  email = local.owner_email
}

# ================================================================
# IAM ROLE — LAMBDA
# ================================================================
resource "aws_iam_role" "lambda_exec" {
  name = "${local.project}-lambda-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "${local.project}-lambda-policy"
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Scan", "dynamodb:Query", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
        Resource = aws_dynamodb_table.orders.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Scan", "dynamodb:Query", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
        Resource = aws_dynamodb_table.products.arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.website.arn}/images/*"
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = [
          aws_ssm_parameter.razorpay_key_id.arn,
          aws_ssm_parameter.razorpay_key_secret.arn,
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["cloudfront:CreateInvalidation"]
        Resource = "arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/${aws_cloudfront_distribution.website.id}"
      }
    ]
  })
}

# ================================================================
# LAMBDA FUNCTION
# ================================================================
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambda/order_handler.py"
  output_path = "${path.module}/lambda.zip"
}

resource "aws_lambda_function" "order_handler" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = local.lambda_name
  role             = aws_iam_role.lambda_exec.arn
  handler          = "order_handler.lambda_handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      ORDERS_TABLE         = local.orders_table
      PRODUCTS_TABLE       = "nimisha-products"
      OWNER_EMAIL          = local.owner_email
      SSM_KEY_ID_PARAM     = aws_ssm_parameter.razorpay_key_id.name
      SSM_KEY_SECRET_PARAM = aws_ssm_parameter.razorpay_key_secret.name
      RAZORPAY_KEY_ID      = var.razorpay_key_id
      RAZORPAY_KEY_SECRET  = var.razorpay_key_secret
      AWS_REGION_NAME      = "ap-south-1"
      S3_BUCKET            = local.bucket_name
      ADMIN_UPLOAD_TOKEN   = "nimisha_upload_2025"
      CF_DISTRIBUTION_ID   = aws_cloudfront_distribution.website.id
    }
  }

  tags = { Project = local.project }
}

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = 30
}

# ================================================================
# API GATEWAY
# ================================================================
resource "aws_apigatewayv2_api" "api" {
  name          = "${local.project}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["Content-Type", "Authorization", "X-Admin-Token"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_origins = ["*"]
    max_age       = 300
  }
}

resource "aws_cloudwatch_log_group" "apigw_logs" {
  name              = "/aws/apigateway/${local.project}-api"
  retention_in_days = 30
}

resource "aws_apigatewayv2_stage" "prod" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = local.api_stage
  auto_deploy = true
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.apigw_logs.arn
    format = jsonencode({
      requestId  = "$context.requestId"
      sourceIp   = "$context.identity.sourceIp"
      httpMethod = "$context.httpMethod"
      routeKey   = "$context.routeKey"
      status     = "$context.status"
    })
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.order_handler.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "routes" {
  for_each = toset([
    "GET /products",
    "GET /products/all",
    "POST /products",
    "PUT /products/{id}",
    "DELETE /products/{id}",
    "POST /products/stock",
    "POST /razorpay/create-order",
    "POST /razorpay/verify",
    "POST /order",
    "GET /orders",
    "POST /orders/{id}/status",
    "POST /upload/presign",
  ])
  api_id    = aws_apigatewayv2_api.api.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.order_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

# ================================================================
# OUTPUTS
# ================================================================
output "cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.website.domain_name}"
}

output "certificate_validation_cname" {
  description = "Add this CNAME record in your domain registrar to validate the ACM certificate"
  value = {
    name  = one(aws_acm_certificate.website.domain_validation_options).resource_record_name
    value = one(aws_acm_certificate.website.domain_validation_options).resource_record_value
    type  = one(aws_acm_certificate.website.domain_validation_options).resource_record_type
  }
}

output "s3_bucket" {
  value = aws_s3_bucket.website.id
}

output "cf_dist_id" {
  value = aws_cloudfront_distribution.website.id
}

output "api_base_url" {
  value = aws_apigatewayv2_stage.prod.invoke_url
}

output "orders_table" {
  value = aws_dynamodb_table.orders.name
}

output "products_table" {
  value = aws_dynamodb_table.products.name
}
