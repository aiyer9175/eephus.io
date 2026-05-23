import http.server, socketserver, threading
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a,**k): pass
httpd = socketserver.TCPServer(("127.0.0.1",0), Q, bind_and_activate=False)
httpd.allow_reuse_address = True; httpd.server_bind(); httpd.server_activate()
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    errors = []
    console_messages = []
    page.on("pageerror", lambda e: errors.append(("pageerror", e.message)))
    page.on("console", lambda m: console_messages.append((m.type, m.text)))
    page.goto(f"http://127.0.0.1:{port}/#player=bryan_sanchez", wait_until="load", timeout=15000)
    page.wait_for_timeout(3000)
    content_html_len = page.evaluate("document.getElementById('content').innerHTML.length")
    view_state = page.evaluate("JSON.stringify(state.view)")
    has_player_detail = page.evaluate("!!document.querySelector('.detail-page-header')")
    body_text_sample = page.evaluate("document.body.innerText.slice(0, 500)")
    browser.close()

print('errors:', errors)
print('console errors:', [m for m in console_messages if m[0] == 'error'])
print('content html length:', content_html_len)
print('view state:', view_state)
print('has detail header:', has_player_detail)
print('body text first 500:')
print(body_text_sample)
