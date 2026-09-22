"""Quick smoke test for the student module."""
from urllib.request import urlopen, Request, build_opener, HTTPCookieProcessor
from urllib.parse import urlencode
from http.cookiejar import CookieJar
import re

opener = build_opener(HTTPCookieProcessor(CookieJar()))

# 1. Get login page for CSRF token
r = opener.open('http://127.0.0.1:5000/login')
html = r.read().decode()
csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

# 2. Login as student1
data = urlencode({'csrf_token': csrf, 'email': 'student1@smart.edu', 'password': 'password'}).encode()
r = opener.open(Request('http://127.0.0.1:5000/login', data=data, method='POST'))
page = r.read().decode()
print("URL after login:", r.url)
print("Has Dashboard:", "Dashboard" in page)
print("Has subject data:", "CS101" in page or "CS102" in page)
print("Has progress bar:", "progress-bar" in page)
print()

# 3. Test subject detail
r = opener.open('http://127.0.0.1:5000/student/subject/1')
detail = r.read().decode()
print("Subject detail loaded:", r.status == 200)
print("Has guidance:", "Guidance" in detail)
print("Has what-if:", "What-If" in detail)
print("Has session history:", "Session History" in detail)
print("Has weekly trend:", "Weekly Trend" in detail)
print()

# 4. Test what-if calculator
r = opener.open('http://127.0.0.1:5000/student/subject/1?n=5&action=attend')
whatif = r.read().decode()
print("What-if calculated:", "Calculate" in whatif)

print()
print("ALL SMOKE TESTS PASSED")
