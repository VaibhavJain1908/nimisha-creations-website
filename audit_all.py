#!/usr/bin/env python3
"""
nimisha-creations FULL AUDIT SCRIPT
Run before deploying ANY file.
Usage: python audit_all.py
Place this file in D:/nimisha-creations/
Files must be in D:/nimisha-creations/website/ and D:/nimisha-creations/infra/lambda/
"""

import re, subprocess, tempfile, os, sys

WEBSITE = os.path.join(os.path.dirname(__file__), 'website')
LAMBDA  = os.path.join(os.path.dirname(__file__), 'infra', 'lambda')

PASS = '  ✓'
FAIL = '  ✗'
total_pass = 0
total_fail = 0

def check(label, ok):
    global total_pass, total_fail
    if ok:
        total_pass += 1
        print(f"{PASS} {label}")
    else:
        total_fail += 1
        print(f"{FAIL} {label}  ← FAIL")
    return ok

def read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def js_syntax(content):
    scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
    if not scripts: return True
    tmp = tempfile.mktemp(suffix='.js')
    with open(tmp, 'w', encoding='utf-8') as f: f.write(scripts[0])
    r = subprocess.run(['node', '--check', tmp], capture_output=True, text=True)
    os.unlink(tmp)
    if r.returncode:
        print(f"     JS error: {r.stderr.strip()[:120]}")
    return r.returncode == 0

# ═══════════════════════════════════════════════════════════════
print("\n" + "="*55)
print("  NIMISHA CREATIONS — PRE-DEPLOY AUDIT")
print("="*55)

# ── order_handler.py ────────────────────────────────────────────
print("\n[ order_handler.py ]")
lp = os.path.join(LAMBDA, 'order_handler.py')
if os.path.exists(lp):
    lam = read(lp)
    check("is_branding defined before use",      "is_branding = filename in BRANDING_PATHS" in lam)
    check("no CacheControl in presign params",   "CacheControl" not in lam)
    check("CF domain hardcoded",                 "www.nimishacreations.in" in lam)
    check("lazy cf_client (not module-level)",   "cf = boto3.client('cloudfront')" in lam)
    check("GET /orders route",                   "endswith('/orders') and method == 'GET'" in lam)
    check("POST /orders/{id}/status route",      "endswith('/status')" in lam)
    check("POST /branding/invalidate route",     "endswith('/branding/invalidate')" in lam)
    check("def deduct_stock exists",             "def deduct_stock" in lam)
    check("deduct_stock called on COD order",    lam.count("deduct_stock(order_data") >= 2)
    check("new owner email",                     "creationsnimisha51@gmail.com" in lam)
    check("old email removed",                   "nimishacreations@gmail.com" not in lam)
    check("Razorpay saves as pending",           "'status': 'pending'" in lam)
    check("CF invalidation logging",             "CF invalidation FAILED" in lam)
    # Python syntax
    import py_compile
    tmp = tempfile.mktemp(suffix='.py')
    with open(tmp,'w',encoding='utf-8') as f: f.write(lam)
    try:
        py_compile.compile(tmp, doraise=True)
        check("Python syntax clean",             True)
    except py_compile.PyCompileError as e:
        check(f"Python syntax clean ({e})",      False)
    os.unlink(tmp)
else:
    print(f"  ✗ FILE NOT FOUND: {lp}")
    total_fail += 1

# ── index.html ──────────────────────────────────────────────────
print("\n[ index.html ]")
ip = os.path.join(WEBSITE, 'index.html')
if os.path.exists(ip):
    idx = read(ip)
    check("free shipping text",                  "Free shipping on all orders" in idx)
    check("no ₹999 threshold",                   "Rs. 999" not in idx and "₹999" not in idx)
    check("no Easy Returns",                     "Easy Returns" not in idx)
    check("COD Available badge",                 "COD Available" in idx)
    check("logo hosted URL",                     "nimishacreations.in/images/logo.png" in idx)
    check("hero hosted URL",                     "nimishacreations.in/images/hero.jpg" in idx)
    check("all 5 cat images hosted",             all(f"nimishacreations.in/images/cat_{x}" in idx
                                                 for x in ['ethnic-dresses','coord-sets','kurta-sets','indo-western','kurtis']))
    check("loadFeatured called",                 "loadFeatured()" in idx)
    check("loadFeatured has timeout",            "AbortController" in idx)
    check("slider CSS present",                  "slider-imgs" in idx)
    check("buildCard not broken",                "addToCart(''+p.id+''" not in idx)
    check("newsletter dark bg in main CSS",      "background:var(--black)" in idx)
    check("newsletter NOT inside @media",        (lambda c: (lambda i: i<0 or c[max(0,i-500):i].rfind('@media') < c[max(0,i-500):i].rfind('}'))(c.find('.newsletter{padding:80px')))(idx))
    check("Instagram URL present",              "nimishacreations_kanpur" in idx)
    check("no email subscribe fn",               "subscribe()" not in idx and "nc_subs" not in idx)
    check("no broken symbols",                   not re.search(r'â€|ðŸ"\'|â†\x90', idx))
    check("JS syntax clean",                     js_syntax(idx))
else:
    print(f"  ✗ FILE NOT FOUND: {ip}")
    total_fail += 1

# ── shop.html ───────────────────────────────────────────────────
print("\n[ shop.html ]")
sp = os.path.join(WEBSITE, 'shop.html')
if os.path.exists(sp):
    shp = read(sp)
    check("free shipping text",                  "Free shipping on all orders" in shp)
    check("no ₹999 threshold",                   "Rs. 999" not in shp)
    check("no Returns & Exchange link",          "Returns & Exchange" not in shp)
    check("OOS overlay in buildCard",            "Out of Stock" in shp)
    check("WA float hides on cart open",         "querySelector('.wa-float-btn')" in shp)
    check("JS syntax clean",                     js_syntax(shp))
else:
    print(f"  ✗ FILE NOT FOUND: {sp}")
    total_fail += 1

# ── product.html ────────────────────────────────────────────────
print("\n[ product.html ]")
pp = os.path.join(WEBSITE, 'product.html')
if os.path.exists(pp):
    prd = read(pp)
    check("free shipping text",                  "Free shipping on all orders" in prd)
    check("no ₹999 threshold",                   "Rs. 999" not in prd)
    check("no Returns drow",                     not re.search(r'dkey.*?Returns', prd))
    check("Delivery only (not Delivery & Returns)", "Delivery & Returns" not in prd)
    check("checkAddReady fn",                    "checkAddReady" in prd)
    check("OOS check in checkAddReady",          "Out of Stock" in prd)
    check("auto-select first variant",           "Auto-select" in prd)
    check("add-bag-btn id",                      'id="add-bag-btn"' in prd)
    check("WA float hides on cart open",         "querySelector('.wa-float-btn')" in prd)
    check("JS syntax clean",                     js_syntax(prd))
else:
    print(f"  ✗ FILE NOT FOUND: {pp}")
    total_fail += 1

# ── checkout.html ───────────────────────────────────────────────
print("\n[ checkout.html ]")
cp = os.path.join(WEBSITE, 'checkout.html')
if os.path.exists(cp):
    chk = read(cp)
    check("free delivery text",                  "Free delivery on all orders" in chk)
    check("no ₹999 threshold",                   "Rs. 999" not in chk)
    check("no NEFT option",                      "neft" not in chk.lower())
    check("Razorpay SDK loaded",                 "checkout.razorpay.com" in chk)
    check("paise conversion (total*100)",        "total*100" in chk)
    check("showSuccess fn",                      "showSuccess" in chk)
    check("Razorpay create-order call",          "razorpay/create-order" in chk)
    check("no broken symbols",                   not re.search(r'â€|ðŸ"\'|â†\x90', chk))
    check("lock icon as HTML entity",            "&#128274;" in chk)
    check("back arrow as HTML entity",           "&larr;" in chk)
    check("JS syntax clean",                     js_syntax(chk))
else:
    print(f"  ✗ FILE NOT FOUND: {cp}")
    total_fail += 1

# ── admin.html ──────────────────────────────────────────────────
print("\n[ admin.html ]")
ap = os.path.join(WEBSITE, 'admin.html')
if os.path.exists(ap):
    adm = read(ap)
    check("hash routing in initAdmin",           "validPages" in adm)
    check("showPg sets URL hash",                "window.location.hash=name" in adm)
    check("fetchOrdersFromAPI fn",               "fetchOrdersFromAPI" in adm)
    check("orders fetched on tab switch",        "fetchOrdersFromAPI().then" in adm)
    check("status sync to API",                  "orders/'+_curOrdId" in adm)
    check("toggleStatusBoxes standalone fn",     "function toggleStatusBoxes(" in adm)
    check("confirm-box HTML",                    'id="confirm-box"' in adm)
    check("tracking-box HTML",                   'id="tracking-box"' in adm)
    check("delivered-box HTML",                  'id="delivered-box"' in adm)
    check("WA confirmed message",                "newStatus==='confirmed'" in adm)
    check("WA shipped message",                  "newStatus==='shipped'" in adm)
    check("WA delivered message",                "newStatus==='delivered'" in adm)
    check("payment banner Razorpay",             "PAYMENT COMPLETED" in adm)
    check("payment banner COD",                  "COLLECT ON DELIVERY" in adm)
    check("customer email as mailto",            "mailto:" in adm)
    check("branding page",                       'id="pg-branding"' in adm)
    check("uploadBrandAsset fn",                 "uploadBrandAsset" in adm)
    check("blob fetch for preview",              "cache:'no-store'" in adm)
    check("CF invalidate after upload",          "branding/invalidate" in adm)
    check("closeOrdModal resets boxes",          "confirm-msg').value=''" in adm)
    check("JS syntax clean",                     js_syntax(adm))
else:
    print(f"  ✗ FILE NOT FOUND: {ap}")
    total_fail += 1

# ── SUMMARY ─────────────────────────────────────────────────────
print("\n" + "="*55)
print(f"  RESULT: {total_pass} passed, {total_fail} failed")
if total_fail == 0:
    print("  ✓ ALL CHECKS PASSED — SAFE TO DEPLOY")
else:
    print(f"  ✗ {total_fail} ISSUE(S) FOUND — DO NOT DEPLOY")
print("="*55 + "\n")
sys.exit(0 if total_fail == 0 else 1)
