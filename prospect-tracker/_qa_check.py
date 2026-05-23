import http.server, socketserver, threading, json
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a,**k): pass
httpd = socketserver.TCPServer(("127.0.0.1",0), Q, bind_and_activate=False)
httpd.allow_reuse_address = True; httpd.server_bind(); httpd.server_activate()
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()

from playwright.sync_api import sync_playwright

results = {}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(e.message))

    # Test 1: farm page
    page.goto(f"http://127.0.0.1:{port}/", wait_until="load", timeout=15000)
    page.wait_for_timeout(3000)
    page.click('.section-tab[data-section="farm"]')
    page.wait_for_timeout(2000)
    results["farm"] = {
        "rows": page.evaluate("document.querySelectorAll('.farm-row').length"),
        "header_visible": page.evaluate("!!document.querySelector('.farm-header')"),
        "section_visible": page.evaluate("document.getElementById('farm-section').style.display !== 'none'"),
        "errors_so_far": list(errors),
    }

    # Test 2: Bryan Sanchez detail page
    errors.clear()
    page.goto(f"http://127.0.0.1:{port}/#player=bryan_sanchez", wait_until="load", timeout=15000)
    page.wait_for_timeout(3000)
    results["sanchez"] = {
        "view_state": page.evaluate("JSON.stringify(state.view)"),
        "has_detail_header": page.evaluate("!!document.querySelector('.detail-page-header')"),
        "content_html_len": page.evaluate("document.getElementById('content').innerHTML.length"),
        "errors": list(errors),
    }

    browser.close()

print(json.dumps(results, indent=2))
