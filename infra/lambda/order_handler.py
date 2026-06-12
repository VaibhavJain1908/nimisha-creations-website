import json
import boto3
import hmac
import hashlib
import os
import uuid
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))
ses      = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))
ssm      = boto3.client('ssm', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))
s3       = boto3.client('s3',  region_name=os.environ.get('AWS_REGION', 'ap-south-1'))

ORDERS_TABLE      = os.environ.get('ORDERS_TABLE',         'nimisha-orders')
PRODUCTS_TABLE    = os.environ.get('PRODUCTS_TABLE',        'nimisha-products')
OWNER_EMAIL       = os.environ.get('OWNER_EMAIL',           'creationsnimisha51@gmail.com')
SSM_KEY_ID_PARAM  = os.environ.get('SSM_KEY_ID_PARAM',     '/nimisha/razorpay/key_id')
SSM_KEY_SECRET_PARAM = os.environ.get('SSM_KEY_SECRET_PARAM', '/nimisha/razorpay/key_secret')
S3_BUCKET         = os.environ.get('S3_BUCKET',             'nimisha-creations-website-prod')
IMAGES_PREFIX  = 'images/'
ADMIN_TOKEN    = os.environ.get('ADMIN_UPLOAD_TOKEN',   'nimisha_upload_2025')
CF_DIST_ID     = os.environ.get('CF_DISTRIBUTION_ID',    'E22P6B24TXTI9X')

# ── JSON helper — DynamoDB returns Decimal, JSON can't serialize it ─
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

def jdump(obj):
    return json.dumps(obj, cls=DecimalEncoder)

def cors_headers():
    return {
        'Access-Control-Allow-Origin':  '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Admin-Token',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Content-Type': 'application/json'
    }

def respond(status, body):
    return {'statusCode': status, 'headers': cors_headers(), 'body': jdump(body)}

def check_admin(event, body):
    token = (event.get('headers') or {}).get('x-admin-token', '') or body.get('admin_token', '')
    return token == ADMIN_TOKEN

def lambda_handler(event, context):
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path   = event.get('rawPath', '/')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers(), 'body': ''}

    try:
        body = json.loads(event.get('body') or '{}')
    except Exception:
        body = {}

    # ═══════════════════════════════════════════════════════════════
    # PRODUCTS API
    # ═══════════════════════════════════════════════════════════════

    # GET /products — public, returns all active products
    if path.endswith('/products') and method == 'GET':
        table = dynamodb.Table(PRODUCTS_TABLE)
        result = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('active').ne(False)
        )
        products = sorted(result.get('Items', []),
                          key=lambda p: p.get('createdAt', ''), reverse=True)
        return respond(200, {'products': products})

    # GET /products/all — admin only, returns ALL products including hidden
    if path.endswith('/products/all') and method == 'GET':
        if not check_admin(event, body):
            return respond(401, {'error': 'Unauthorized'})
        table = dynamodb.Table(PRODUCTS_TABLE)
        result = table.scan()
        products = sorted(result.get('Items', []),
                          key=lambda p: p.get('createdAt', ''), reverse=True)
        return respond(200, {'products': products})

    # POST /products — admin only, create product
    if path.endswith('/products') and method == 'POST':
        if not check_admin(event, body):
            return respond(401, {'error': 'Unauthorized'})
        product = {
            'id':          body.get('id') or ('p' + uuid.uuid4().hex[:8]),
            'name':        body.get('name', ''),
            'category':    body.get('category', ''),
            'emoji':       body.get('emoji', '👗'),
            'price':       Decimal(str(body.get('price', 0))),
            'salePrice':   Decimal(str(body['salePrice'])) if body.get('salePrice') else None,
            'badge':       body.get('badge') or None,
            'featured':    body.get('featured', False),
            'description': body.get('description', ''),
            'images':      body.get('images', []),
            'categories':  body.get('categories', []),
            'variants':    body.get('variants', []),
            'active':      body.get('active', True),
            'createdAt':   body.get('createdAt') or datetime.now().isoformat(),
            'updatedAt':   datetime.now().isoformat(),
        }
        # Remove None values (DynamoDB doesn't accept None)
        product = {k: v for k, v in product.items() if v is not None}
        dynamodb.Table(PRODUCTS_TABLE).put_item(Item=product)
        return respond(200, {'success': True, 'product': product})

    # PUT /products/{id} — admin only, update product
    if path.startswith('/prod') and '/products/' in path and method == 'PUT':
        if not check_admin(event, body):
            return respond(401, {'error': 'Unauthorized'})
        pid = path.split('/')[-1]
        body['id'] = pid
        body['updatedAt'] = datetime.now().isoformat()
        if body.get('price'):
            body['price'] = Decimal(str(body['price']))
        if body.get('salePrice'):
            body['salePrice'] = Decimal(str(body['salePrice']))
        else:
            body.pop('salePrice', None)
        body = {k: v for k, v in body.items() if v is not None and k != 'admin_token'}
        dynamodb.Table(PRODUCTS_TABLE).put_item(Item=body)
        return respond(200, {'success': True})

    # DELETE /products/{id} — admin only
    if path.startswith('/prod') and '/products/' in path and method == 'DELETE':
        if not check_admin(event, body):
            return respond(401, {'error': 'Unauthorized'})
        pid = path.split('/')[-1]
        dynamodb.Table(PRODUCTS_TABLE).delete_item(Key={'id': pid})
        return respond(200, {'success': True})

    # POST /products/stock — update stock for a variant
    if path.endswith('/products/stock') and method == 'POST':
        if not check_admin(event, body):
            return respond(401, {'error': 'Unauthorized'})
        pid   = body.get('id')
        size  = body.get('size')
        colour= body.get('colour')
        stock = int(body.get('stock', 0))
        table = dynamodb.Table(PRODUCTS_TABLE)
        result = table.get_item(Key={'id': pid})
        product = result.get('Item')
        if not product:
            return respond(404, {'error': 'Product not found'})
        variants = product.get('variants', [])
        for v in variants:
            if v.get('size') == size and v.get('colour') == colour:
                v['stock'] = stock
                break
        table.update_item(
            Key={'id': pid},
            UpdateExpression='SET variants = :v, updatedAt = :u',
            ExpressionAttributeValues={':v': variants, ':u': datetime.now().isoformat()}
        )
        return respond(200, {'success': True})

    # ═══════════════════════════════════════════════════════════════
    # IMAGE UPLOAD
    # ═══════════════════════════════════════════════════════════════
    if path.endswith('/upload/presign') and method == 'POST':
        if not check_admin(event, body):
            return respond(401, {'error': 'Unauthorized'})
        filename     = body.get('filename', 'image.jpg')
        content_type = body.get('content_type', 'image/jpeg')
        # Allow fixed paths for branding assets (logo, hero, category images)
        BRANDING_PATHS = [
            'images/logo.png', 'images/hero.jpg',
            'images/cat_ethnic-dresses.jpg', 'images/cat_coord-sets.jpg',
            'images/cat_kurta-sets.jpg', 'images/cat_indo-western.jpg',
            'images/cat_kurtis.jpg'
        ]
        is_branding = filename in BRANDING_PATHS
        if is_branding:
            key = filename
        else:
            ext      = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
            safe_ext = ext if ext in ['jpg','jpeg','png','webp','gif'] else 'jpg'
            key      = f"{IMAGES_PREFIX}{uuid.uuid4().hex}.{safe_ext}"
        presigned = s3.generate_presigned_url(
            'put_object',
            Params={'Bucket': S3_BUCKET, 'Key': key},
            ExpiresIn=300
        )
        public_url = f"https://www.nimishacreations.in/{key}"
        return respond(200, {'presigned_url': presigned, 'public_url': public_url, 'key': key})

    # ═══════════════════════════════════════════════════════════════
    # ORDERS
    # ═══════════════════════════════════════════════════════════════
    if path.endswith('/razorpay/create-order') and method == 'POST':
        import urllib.request, base64
        try:
            key_id     = ssm.get_parameter(Name=SSM_KEY_ID_PARAM)['Parameter']['Value']
            key_secret = ssm.get_parameter(Name=SSM_KEY_SECRET_PARAM, WithDecryption=True)['Parameter']['Value']
        except Exception:
            key_id     = os.environ.get('RAZORPAY_KEY_ID', '')
            key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
        amount   = int(body.get('amount', 0))
        currency = body.get('currency', 'INR')
        receipt  = 'nc_' + str(uuid.uuid4())[:8]
        payload  = json.dumps({'amount': amount, 'currency': currency, 'receipt': receipt}).encode()
        creds    = base64.b64encode(f'{key_id}:{key_secret}'.encode()).decode()
        req      = urllib.request.Request(
            'https://api.razorpay.com/v1/orders', data=payload,
            headers={'Authorization': f'Basic {creds}', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as r:
            rz = json.loads(r.read())
        return respond(200, {'order_id': rz['id'], 'amount': amount, 'currency': currency, 'key_id': key_id})

    elif path.endswith('/razorpay/verify') and method == 'POST':
        rz_order_id   = body.get('razorpay_order_id', '')
        rz_payment_id = body.get('razorpay_payment_id', '')
        rz_signature  = body.get('razorpay_signature', '')
        try:
            key_secret = ssm.get_parameter(Name=SSM_KEY_SECRET_PARAM, WithDecryption=True)['Parameter']['Value']
        except Exception:
            key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
        message  = f'{rz_order_id}|{rz_payment_id}'
        expected = hmac.new(key_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, rz_signature):
            order_id   = 'NC' + datetime.now().strftime('%y%m%d') + str(uuid.uuid4())[:4].upper()
            order_data = {'order_id': order_id, 'razorpay_order_id': rz_order_id,
                'razorpay_payment_id': rz_payment_id, 'contact': body.get('contact', {}),
                'shipping': body.get('shipping', {}), 'cart': body.get('cart', []),
                'total': body.get('total', 0), 'payment_method': 'razorpay',
                'status': 'pending', 'created_at': datetime.now().isoformat()}
            dynamodb.Table(ORDERS_TABLE).put_item(Item=order_data)
            deduct_stock(order_data.get('cart', []))
            send_order_email(order_data)
            return respond(200, {'success': True, 'order_id': order_id})
        return respond(400, {'success': False, 'error': 'Verification failed'})

    # GET /orders — list all orders for admin
    if path.endswith('/orders') and method == 'GET':
        auth = (event.get('headers') or {}).get('x-admin-token','') or (event.get('headers') or {}).get('X-Admin-Token','')
        if auth != ADMIN_TOKEN:
            return respond(403, {'error': 'Unauthorized'})
        result = dynamodb.Table(ORDERS_TABLE).scan()
        orders = result.get('Items', [])
        orders.sort(key=lambda o: o.get('created_at', ''), reverse=True)
        return respond(200, {'orders': orders})

    # POST /orders/{id}/status — update order status
    if '/orders/' in path and path.endswith('/status') and method == 'POST':
        auth = (event.get('headers') or {}).get('x-admin-token','') or (event.get('headers') or {}).get('X-Admin-Token','')
        if auth != ADMIN_TOKEN:
            return respond(403, {'error': 'Unauthorized'})
        oid = path.split('/orders/')[1].replace('/status','')
        new_status = body.get('status','pending')
        tracking = body.get('tracking', None)
        if tracking:
            dynamodb.Table(ORDERS_TABLE).update_item(
                Key={'order_id': oid},
                UpdateExpression='SET #s = :s, tracking = :t',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':s': new_status, ':t': tracking}
            )
        else:
            dynamodb.Table(ORDERS_TABLE).update_item(
                Key={'order_id': oid},
                UpdateExpression='SET #s = :s',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':s': new_status}
            )
        return respond(200, {'success': True})

    elif path.endswith('/order') and method == 'POST':
        # Razorpay orders must only be saved after signature verification via /razorpay/verify
        if body.get('payment_method', 'cod') == 'razorpay':
            return respond(400, {'error': 'Razorpay orders must be confirmed via /razorpay/verify'})
        order_id   = 'NC' + datetime.now().strftime('%y%m%d') + str(uuid.uuid4())[:4].upper()
        order_data = {'order_id': order_id, 'contact': body.get('contact', {}),
            'shipping': body.get('shipping', {}), 'cart': body.get('cart', []),
            'total': body.get('total', 0), 'payment_method': body.get('payment_method', 'cod'),
            'status': 'pending', 'created_at': datetime.now().isoformat()}
        dynamodb.Table(ORDERS_TABLE).put_item(Item=order_data)
        deduct_stock(order_data.get('cart', []))
        send_order_email(order_data)
        return respond(200, {'success': True, 'order_id': order_id})

    # POST /branding/invalidate — invalidate CF cache after branding upload
    if path.endswith('/branding/invalidate') and method == 'POST':
        auth = (event.get('headers') or {}).get('x-admin-token','') or (event.get('headers') or {}).get('X-Admin-Token','')
        if auth != ADMIN_TOKEN:
            return respond(403, {'error': 'Unauthorized'})
        s3_key = body.get('key','')
        if not s3_key:
            return respond(400, {'error': 'Missing key'})
        try:
            cf = boto3.client('cloudfront')
            dist_id = os.environ.get('CF_DISTRIBUTION_ID', 'E22P6B24TXTI9X')
            print(f'Creating invalidation for key: {s3_key}, dist: {dist_id}')
            cf.create_invalidation(
                DistributionId=dist_id,
                InvalidationBatch={
                    'Paths': {'Quantity': 1, 'Items': [f'/{s3_key}']},
                    'CallerReference': f'branding-{uuid.uuid4().hex}'
                }
            )
            return respond(200, {'success': True})
        except Exception as e:
            print(f'CF invalidation FAILED: {type(e).__name__}: {e}')
            return respond(500, {'error': str(e)})

    return respond(404, {'error': 'Route not found'})


def deduct_stock(cart):
    """Reduce stock for each item in the cart after order is placed."""
    try:
        table = dynamodb.Table(PRODUCTS_TABLE)
        for item in cart:
            pid  = item.get('id')
            size = item.get('size','')
            colour = item.get('colour','')
            qty  = int(item.get('qty', 1))
            if not pid:
                continue
            result = table.get_item(Key={'id': pid})
            product = result.get('Item')
            if not product:
                continue
            variants = product.get('variants', [])
            updated = False
            for v in variants:
                if v.get('size','') == size and v.get('colour','') == colour:
                    current = int(v.get('stock', 0))
                    v['stock'] = max(0, current - qty)
                    updated = True
                    break
            if updated:
                table.update_item(
                    Key={'id': pid},
                    UpdateExpression='SET variants = :v, updatedAt = :u',
                    ExpressionAttributeValues={
                        ':v': variants,
                        ':u': datetime.now().isoformat()
                    }
                )
    except Exception as e:
        print(f'Stock deduction error: {e}')


def send_order_email(order):
    try:
        contact = order.get('contact', {})
        shipping= order.get('shipping', {})
        cart    = order.get('cart', [])
        rows    = ''.join([
            f"<tr><td style='padding:6px 12px'>{i.get('emoji','')} {i.get('name','')}</td>"
            f"<td style='padding:6px 12px'>{i.get('qty',1)}</td>"
            f"<td style='padding:6px 12px'>₹{float(i.get('price',0)):,.0f}</td></tr>"
            for i in cart])
        is_razorpay = order.get('payment_method','') == 'razorpay'
        payment_banner = f"""
          <div style="background:{'#1a7a3c' if is_razorpay else '#7a6a1a'};padding:16px 24px;margin-bottom:0;text-align:center">
            {'<p style="color:#fff;font-size:18px;font-weight:700;margin:0;letter-spacing:.04em">&#10003; PAYMENT RECEIVED — Rs. '+f"{float(order.get('total',0)):,.0f}"+'</p><p style="color:rgba(255,255,255,.8);font-size:11px;letter-spacing:.16em;text-transform:uppercase;margin:4px 0 0">Razorpay · Payment ID: '+order.get('razorpay_payment_id','')+'</p>' if is_razorpay else '<p style="color:#fff;font-size:16px;font-weight:700;margin:0;letter-spacing:.04em">&#9888; NEW COD ORDER — COLLECT ON DELIVERY</p>'}
          </div>""" if True else ""
        html = f"""<div style="font-family:sans-serif;max-width:560px;margin:0 auto;border:1px solid #e0d6cc">
          <div style="background:#0A0A0A;padding:20px 24px">
            <p style="color:#B8960C;font-size:11px;letter-spacing:.2em;text-transform:uppercase;margin:0">Parveena Agarwal — Admin Alert</p>
          </div>
          {payment_banner}
          <div style="padding:24px">
            <table width="100%" style="margin-bottom:16px">
              <tr><td style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#888;padding-bottom:4px">Order ID</td><td style="font-family:monospace;font-weight:600">{order.get('order_id')}</td></tr>
              <tr><td style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#888;padding:6px 0 4px">Customer</td><td>{contact.get('name')} · {contact.get('phone')}</td></tr>
              <tr><td style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#888;padding:6px 0 4px">Email</td><td><a href="mailto:{contact.get('email','')}">{contact.get('email','—')}</a></td></tr>
              <tr><td style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#888;padding:6px 0 4px">Ship To</td><td>{shipping.get('addr1','')}, {shipping.get('city','')}, {shipping.get('state','')} — {shipping.get('pin','')}</td></tr>
            </table>
            <table width="100%" style="border-collapse:collapse;margin-bottom:16px">
              <tr style="background:#f9f6f2"><th style="padding:8px 12px;text-align:left;font-size:10px;letter-spacing:.12em;text-transform:uppercase">Item</th><th style="padding:8px 12px;font-size:10px;letter-spacing:.12em;text-transform:uppercase">Qty</th><th style="padding:8px 12px;text-align:right;font-size:10px;letter-spacing:.12em;text-transform:uppercase">Price</th></tr>
              {rows}
            </table>
            <div style="display:flex;justify-content:space-between;padding:12px 0;border-top:2px solid #0A0A0A">
              <span style="font-weight:600;letter-spacing:.06em;text-transform:uppercase;font-size:13px">Total</span>
              <span style="font-weight:700;font-size:16px">Rs. {float(order.get('total',0)):,.0f}</span>
            </div>
            <a href="https://www.nimishacreations.in/admin#orders" style="display:block;text-align:center;margin-top:20px;padding:14px;background:#0A0A0A;color:#fff;text-decoration:none;font-size:11px;letter-spacing:.2em;text-transform:uppercase">Open Admin Panel</a>
          </div>
        </div>"""
        ses.send_email(
            Source=OWNER_EMAIL,
            Destination={'ToAddresses': [OWNER_EMAIL]},
            Message={
                'Subject': {'Data': f"New Order {order.get('order_id')} — ₹{float(order.get('total',0)):,.0f}"},
                'Body': {'Html': {'Data': html}}
            })
    except Exception as e:
        print(f'Email error: {e}')


