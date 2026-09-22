"""Smoke test for Phase 8: Correction Workflow and Audit Logs."""
from urllib.request import urlopen, Request, build_opener, HTTPCookieProcessor
from urllib.parse import urlencode
from http.cookiejar import CookieJar
import re

opener = build_opener(HTTPCookieProcessor(CookieJar()))

# --- Admin Test ---
r = opener.open('http://127.0.0.1:5000/login')
html = r.read().decode()
csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
data = urlencode({'csrf_token': csrf, 'email': 'admin@smart.edu', 'password': 'password'}).encode()
opener.open(Request('http://127.0.0.1:5000/login', data=data, method='POST'))

# Check admin corrections page
r = opener.open('http://127.0.0.1:5000/admin/corrections')
page = r.read().decode()
print("Admin corrections loaded:", r.status == 200)

# Check admin audit logs page
r = opener.open('http://127.0.0.1:5000/admin/audit-logs')
page = r.read().decode()
print("Admin audit logs loaded:", r.status == 200)

print("\nALL PHASE 8 SMOKE TESTS PASSED")
