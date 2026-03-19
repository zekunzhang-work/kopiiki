import os
import shutil
import zipfile
import threading
import requests
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
from webtwin_assets import extract_assets, create_zip_file, fix_relative_urls
import uuid
import time
import json

# Optional specific playwright import (previously added during WebTwin refactor)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright is not installed. Will fallback to basic extraction if needed.")

app = Flask(__name__)
# Enable CORS to allow React frontend (e.g. localhost:5173) to send requests
CORS(app, expose_headers=["Content-Disposition"])

# Global map to store progress for SSE

# Global map to store progress for SSE
EXTRACTION_PROGRESS = {}

from threading import Lock, Event
EXTRACTION_LOCK = Lock()
ACTIVE_EXTRACTION_ID = None
CANCEL_TOKEN = Event()


# --- Configuration (moved from old WebTwin app.py) ---
DOWNLOAD_FOLDER = 'downloads'
EXTRACTED_FOLDER = 'extracted_sites'
MAX_ARCHIVE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {'html', 'css', 'js', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'mp4', 'webm'}
OS_INFO = "macOS" # For simplicity just a string now.

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(EXTRACTED_FOLDER, exist_ok=True)


def extract_with_playwright(url, output_dir, extract_id=None):
    """
    Advanced extraction using Playwright:
    1. Handles dynamic content and lazy loading.
    2. intercepts and captures all network responses in memory (solving double-fetch).
    3. injects removable anti-animation CSS.
    """
    def update_progress(msg, status="processing"):
        if extract_id and extract_id in EXTRACTION_PROGRESS:
            EXTRACTION_PROGRESS[extract_id]["message"] = msg
            if status:
                EXTRACTION_PROGRESS[extract_id]["status"] = status
                
    update_progress(f"Starting Playwright browser for {url}...")
    print(f"[{threading.current_thread().name}] Starting Playwright extraction for URL: {url}")
    
    html_content = ""
    error_msg = None
    timeout = 30 # seconds
    captured_assets = {} # url -> bytes

    def handle_response(response):
        # Only capture successful responses for assets
        try:
            if response.ok and response.request.resource_type in ["image", "stylesheet", "script", "font", "media"]:
                url = response.url
                # Avoid capturing data URIs or base64 directly as network events
                if url.startswith("http"):
                    body = response.body()
                    captured_assets[url] = body
        except Exception as e:
            # Body might not be available for some redirects or opaque responses
            pass
            
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--start-maximized'
                ]
            )
            
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                device_scale_factor=1,
                is_mobile=False,
                has_touch=False
            )
            
            page = context.new_page()
            page.on("response", handle_response)
            
            update_progress("Navigating to URL and bypassing anti-bot protections...")
            print(f"[{threading.current_thread().name}] Navigating to {url} ...")
            # Using networkidle to wait for lazy multi-media to stop requesting
            response = page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            
            if response and not response.ok:
                 print(f"[{threading.current_thread().name}] Warning: Page returned status {response.status}")
                 
            # 1. Define reusable crawling function
            disable_animation_css = """
            * {
                animation-duration: 0.001s !important;
                animation-delay: 0s !important;
                transition-duration: 0.001s !important;
                transition-delay: 0s !important;
            }
            """
            
            scroll_script = """
            async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    const distance = 300;
                    const scrollInterval = setInterval(() => {
                        const scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if (totalHeight >= scrollHeight - window.innerHeight) {
                            clearInterval(scrollInterval);
                            resolve();
                        }
                    }, 100);
                });
            }
            """

            def crawl_page(target_url, is_main=False):
                if not is_main:
                    update_progress(f"Crawling level-1 subpage: {target_url}...")
                    try:
                        page.goto(target_url, wait_until="networkidle", timeout=timeout * 1000)
                    except Exception:
                        pass
                
                page.add_style_tag(content=disable_animation_css)
                page.evaluate("""() => {
                    const styles = document.querySelectorAll('style');
                    const lastStyle = styles[styles.length - 1];
                    if (lastStyle) lastStyle.id = 'kopiiki-animation-freezer';
                }""")
                
                if is_main:
                    update_progress("Scanning for hidden mobile menus (Hamburger)...")
                    page.evaluate("""() => {
                        const menuSelectors = [
                            '[aria-label*="menu" i]', 
                            '[class*="hamburger" i]', 
                            '[class*="menu-toggle" i]', 
                            '[id*="hamburger" i]',
                            '[class*="navbar-toggler" i]',
                            '.w-nav-button'
                        ];
                        for (let sel of menuSelectors) {
                            const btns = document.querySelectorAll(sel);
                            for (let btn of btns) {
                                if (btn && btn.offsetParent !== null) { // if visible
                                    try { btn.click(); } catch(e) {}
                                }
                            }
                        }
                    }""")
                    page.wait_for_timeout(1000)
                    
                    update_progress("Scrolling to trigger lazy-loaded elements...")
                page.evaluate(scroll_script)
                page.wait_for_timeout(2000)
                
                html_raw = page.content()
                import re
                return re.sub(r'<style id="kopiiki-animation-freezer">.*?</style>', '', html_raw, flags=re.DOTALL)

            html_results = {}
            main_html = crawl_page(url, is_main=True)
            html_results[url] = main_html
            
            update_progress("Analyzing DOM for top-level navigation routes...")
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(main_html, "html.parser")
            from urllib.parse import urljoin, urlparse
            base_domain = urlparse(url).netloc
            normalized_start = url.rstrip('/')

            urls_to_crawl = []
            for a in soup.select("nav a, header a, .navbar a, blockquote a, [role='navigation'] a, [class*='menu'] a, [class*='sidebar'] a, .w-nav-link"):
                if CANCEL_TOKEN.is_set(): break
                href = a.get("href")
                if not href: continue
                full_url = urljoin(url, href)
                parsed_full = urlparse(full_url)
                if parsed_full.netloc != base_domain: continue
                if parsed_full.fragment: continue
                if parsed_full.path.startswith("mailto:") or parsed_full.path.startswith("tel:"): continue
                
                normalized_full = full_url.rstrip('/')
                if normalized_full != normalized_start and normalized_full not in [u.rstrip('/') for u in urls_to_crawl]:
                    urls_to_crawl.append(full_url)
                    if len(urls_to_crawl) >= 6: # Limit shadow depth to 6 sub-pages
                        break
                        
            for idx, sub_url in enumerate(urls_to_crawl):
                if CANCEL_TOKEN.is_set(): break
                try:
                    sub_html = crawl_page(sub_url)
                    html_results[sub_url] = sub_html
                except Exception as e:
                    print(f"Failed to crawl {sub_url}: {str(e)}")

        except PlaywrightTimeoutError:
             error_msg = f"Timeout loading {url} within {timeout} seconds."
             print(f"[{threading.current_thread().name}] Error: {error_msg}")
        except Exception as e:
             error_msg = f"Playwright error: {str(e)}"
             print(f"[{threading.current_thread().name}] Error: {error_msg}")
        finally:
             if 'browser' in locals():
                 browser.close()
                 
    if error_msg:
        raise Exception(error_msg)
        
    return html_results, captured_assets

def create_zip_from_dir(source_dir, zip_filename):
    zipf = zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED)
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, source_dir)
            zipf.write(file_path, arcname)
    zipf.close()


def process_extraction(extract_id, url, output_dir, zip_path, safe_domain):
    try:
        if CANCEL_TOKEN.is_set():
            raise Exception("Cancelled by user")
        EXTRACTION_PROGRESS[extract_id]["message"] = "Initializing extraction pipeline..."
        
        # 1. First extract the dynamic rendered HTML freezing animations, AND intercept all assets
        html_results, captured_assets = extract_with_playwright(url, output_dir, extract_id=extract_id)
        
        # 2. Pack the HTML and all discovered fetched assets straight into a fully fledged ZIP
        if CANCEL_TOKEN.is_set(): raise Exception("Cancelled by user")
        EXTRACTION_PROGRESS[extract_id]["message"] = "Packaging everything into a downloadable ZIP archive..."
        zip_path_tmp = create_zip_file(html_results, captured_assets, url, output_dir, extract_id)
        
        # 6. Copy over to persistent download folder
        shutil.copy2(zip_path_tmp, zip_path)
        os.remove(zip_path_tmp)
        
        EXTRACTION_PROGRESS[extract_id]["status"] = "complete"
        EXTRACTION_PROGRESS[extract_id]["message"] = "Extraction successful! Ready to download."
        EXTRACTION_PROGRESS[extract_id]["download_url"] = f"/api/download/{safe_domain}"
        EXTRACTION_PROGRESS[extract_id]["filename"] = f"{safe_domain}.zip"

    except Exception as e:
        print(f"Extraction Error: {e}")
        EXTRACTION_PROGRESS[extract_id]["status"] = "error"
        EXTRACTION_PROGRESS[extract_id]["message"] = f"Extraction failed: {str(e)}"

@app.route('/api/extract', methods=['POST'])
def api_extract():
    data = request.json or {}
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

    if not PLAYWRIGHT_AVAILABLE:
        return jsonify({"error": "Playwright is not installed on the backend. Please install it."}), 500

    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if not domain:
        domain = "extracted_site"
    safe_domain = secure_filename(domain)
    
    output_dir = os.path.join(EXTRACTED_FOLDER, safe_domain)
    zip_path = os.path.join(DOWNLOAD_FOLDER, f"{safe_domain}.zip")
    
    # Cleanup previous runs for this domain
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    # Generate an ID for this extraction job and store it
    extract_id = str(uuid.uuid4())
    EXTRACTION_PROGRESS[extract_id] = {
        "status": "processing",
        "message": "Starting job...",
        "url": url,
        "download_url": None
    }
    
    # Start the worker thread
    thread = threading.Thread(target=process_extraction, args=(extract_id, url, output_dir, zip_path, safe_domain))
    thread.daemon = True
    thread.start()
    
    # Return immediately so the client can connect to SSE
    return jsonify({"extract_id": extract_id})
    

@app.route('/api/extract/stream/<extract_id>')
def api_extract_stream(extract_id):
    def event_stream():
        last_message = ""
        while True:
            if extract_id not in EXTRACTION_PROGRESS:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Unknown extraction ID'})}\n\n"
                break
                
            progress = EXTRACTION_PROGRESS[extract_id]
            
            # Send an update if status changed, or just to keep connection alive
            if progress["message"] != last_message or progress["status"] in ["complete", "error"]:
                last_message = progress["message"]
                yield f"data: {json.dumps(progress)}\n\n"
                
            if progress["status"] in ["complete", "error"]:
                # Clean up memory after sending completion
                time.sleep(1) # tiny wait to ensure client gets it
                if extract_id in EXTRACTION_PROGRESS:
                    del EXTRACTION_PROGRESS[extract_id]
                break
                
            time.sleep(0.5)
            
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/api/download/<domain>')
def api_download(domain):
    safe_domain = secure_filename(domain)
    # Support both with and without .zip extension in the URL
    if not safe_domain.endswith('.zip'):
        zip_filename = f"{safe_domain}.zip"
    else:
        zip_filename = safe_domain
        
    zip_path = os.path.join(DOWNLOAD_FOLDER, zip_filename)
    
    if os.path.exists(zip_path):
        return send_file(
            zip_path, 
            as_attachment=True, 
            download_name=zip_filename,
            mimetype='application/zip'
        )
    return jsonify({"error": "File not found"}), 404

@app.route('/api/extract-json', methods=['POST'])
def api_extract_json():
    # TODO: This is the stub for Kopiiki-Agent
    # Instead of a zipped folder, we would return a parsed JSON / DOM Tree representation
    # natively optimized for our LLM to generate React components.
    return jsonify({"message": "Not implemented yet. Reserved for Kopiiki-Agent."})

# ── Static file serving for Docker single-port mode ──────────────
# When KOPIIKI_STATIC_DIR is set, Flask serves the pre-built frontend
# so that both API and UI live on a single port (no separate Vite server).
STATIC_DIR = os.environ.get('KOPIIKI_STATIC_DIR')
if STATIC_DIR and os.path.isdir(STATIC_DIR):
    from flask import send_from_directory

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        # Serve the requested file if it exists, otherwise serve index.html (SPA)
        file_path = os.path.join(STATIC_DIR, path)
        if path and os.path.exists(file_path):
            return send_from_directory(STATIC_DIR, path)
        return send_from_directory(STATIC_DIR, 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    print(f"\n{'='*50}")
    print(f"  🔮 Kopiiki Backend running on port {port}")
    if STATIC_DIR:
        print(f"  📁 Serving frontend from: {STATIC_DIR}")
    print(f"{'='*50}\n")
    # threaded=False and debug=False are CRITICAL for sync_playwright
    app.run(host='0.0.0.0', port=port, debug=False, threaded=False)


@app.route('/api/extract/cancel', methods=['POST'])
def cancel_extraction():
    data = request.json or {}
    extract_id = data.get('extract_id')
    global ACTIVE_EXTRACTION_ID
    with EXTRACTION_LOCK:
        if ACTIVE_EXTRACTION_ID == extract_id:
            CANCEL_TOKEN.set()
            if extract_id in EXTRACTION_PROGRESS:
                EXTRACTION_PROGRESS[extract_id]["status"] = "cancelled"
                EXTRACTION_PROGRESS[extract_id]["message"] = "Cancelled by user."
            return jsonify({"message": "Cancellation signal sent."})
        return jsonify({"message": "No matching active extraction found."}), 404
