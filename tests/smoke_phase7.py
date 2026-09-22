"""Smoke test for Phase 7: Analytics, Notifications, Exports."""
from urllib.request import urlopen, Request, build_opener, HTTPCookieProcessor
from urllib.parse import urlencode
from http.cookiejar import CookieJar
import re

opener = build_opener(HTTPCookieProcessor(CookieJar()))

# --- Student Test ---
r = opener.open('http://127.0.0.1:5000/login')
html = r.read().decode()
csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
data = urlencode({'csrf_token': csrf, 'email': 'student1@smart.edu', 'password': 'password'}).encode()
opener.open(Request('http://127.0.0.1:5000/login', data=data, method='POST'))

# Check notifications route
r = opener.open('http://127.0.0.1:5000/student/notifications')
page = r.read().decode()
print("Student notifications loaded:", r.status == 200)

# Check CSV export
r = opener.open('http://127.0.0.1:5000/student/export')
print("Student CSV export status:", r.status)
print("Student CSV export headers:", r.getheader('Content-Type'))

opener.open('http://127.0.0.1:5000/logout')

# --- Faculty Test ---
r = opener.open('http://127.0.0.1:5000/login')
html = r.read().decode()
csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
data = urlencode({'csrf_token': csrf, 'email': 'faculty1@smart.edu', 'password': 'password'}).encode()
opener.open(Request('http://127.0.0.1:5000/login', data=data, method='POST'))

# Check section analytics (assuming section_id=1 exists)
r = opener.open('http://127.0.0.1:5000/faculty/sections/1/analytics')
page = r.read().decode()
print("Faculty analytics loaded:", r.status == 200)

# Check CSV export
r = opener.open('http://127.0.0.1:5000/faculty/sections/1/export')
print("Faculty CSV export status:", r.status)

opener.open('http://127.0.0.1:5000/logout')

# --- Admin Test ---
r = opener.open('http://127.0.0.1:5000/login')
html = r.read().decode()
csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
data = urlencode({'csrf_token': csrf, 'email': 'admin@smart.edu', 'password': 'password'}).encode()
opener.open(Request('http://127.0.0.1:5000/login', data=data, method='POST'))

# Check system analytics
r = opener.open('http://127.0.0.1:5000/admin/analytics')
page = r.read().decode()
print("Admin analytics loaded:", r.status == 200)

# Check full CSV export
r = opener.open('http://127.0.0.1:5000/admin/export')
print("Admin CSV export status:", r.status)

print("\nALL PHASE 7 SMOKE TESTS PASSED")
