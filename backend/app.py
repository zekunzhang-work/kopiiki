import os
import shutil
import zipfile
import threading
import requests
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from webtwin_assets import extract_assets, create_zip_file, fix_relative_urls

# Optional specific playwright import (previously added during WebTwin refactor)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright is not installed. Will fallback to basic extraction if needed.")

app = Flask(__name__)
# Enable CORS to allow React frontend (e.g. localhost:5173) to send requests
CORS(app)

# --- Configuration (moved from old WebTwin app.py) ---
DOWNLOAD_FOLDER = 'downloads'
EXTRACTED_FOLDER = 'extracted_sites'
MAX_ARCHIVE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {'html', 'css', 'js', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'mp4', 'webm'}
OS_INFO = "macOS" # For simplicity just a string now.

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(EXTRACTED_FOLDER, exist_ok=True)


def extract_with_playwright(url, output_dir):
    """
    Advanced extraction using Playwright to handle dynamic content, lazy loading and strip animations.
    Ported from the refactored WebTwin.
    """
    print(f"[{threading.current_thread().name}] Starting Playwright extraction for URL: {url}")
    
    html_content = ""
    error_msg = None
    timeout = 30 # seconds
    
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
            
            print(f"[{threading.current_thread().name}] Navigating to {url} ...")
            # Using networkidle to wait for lazy multi-media to stop requesting
            response = page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            
            if response and not response.ok:
                 print(f"[{threading.current_thread().name}] Warning: Page returned status {response.status}")
                 
            # 1. Disable animations immediately via injected CSS
            disable_animation_css = """
            * {
                animation-duration: 0.001s !important;
                animation-delay: 0s !important;
                transition-duration: 0.001s !important;
                transition-delay: 0s !important;
            }
            """
            page.add_style_tag(content=disable_animation_css)
            
            # 2. Emulate scroll to trigger lazy loading
            scroll_script = """
            async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    const distance = 300;
                    const scrollInterval = setInterval(() => {
                        const scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;

                        if(totalHeight >= scrollHeight){
                            clearInterval(scrollInterval);
                            window.scrollTo(0, 0); // Scroll back to top
                            resolve();
                        }
                    }, 200);
                });
            }
            """
            print(f"[{threading.current_thread().name}] Scrolling to trigger lazy loading...")
            page.evaluate(scroll_script)
            
            # Short wait to let the last triggered images network requests settle
            page.wait_for_timeout(2000)
            
            # Fetch the final static DOM snapshot
            html_content = page.content()
            print(f"[{threading.current_thread().name}] Extraction completed. HTML length: {len(html_content)}")

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
        
    return html_content

def create_zip_from_dir(source_dir, zip_filename):
    zipf = zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED)
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, source_dir)
            zipf.write(file_path, arcname)
    zipf.close()


@app.route('/api/extract', methods=['POST'])
def api_extract():
    data = request.json or {}
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

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

    # Core logic: Extract HTML explicitly using Playwright
    try:
        if not PLAYWRIGHT_AVAILABLE:
            return jsonify({"error": "Playwright is not installed on the backend. Please install it."}), 500
            
        # 1. First extract the dynamic rendered HTML freezing animations
        raw_html_content = extract_with_playwright(url, output_dir)
        
        # 2. Fix all relative links directly using the legacy BS4 logic
        print(f"[{threading.current_thread().name}] Fixing relative URL references...")
        fixed_html = fix_relative_urls(raw_html_content, url)
        
        # 3. Use unified session for fast asset download
        session_obj = requests.Session()
        headers = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36' }
        
        # 4. Spin up the legacy Wget/Crawler style deep asset fetcher
        print(f"[{threading.current_thread().name}] Start deep fetching linked CSS/JS/IMG assets...")
        assets = extract_assets(fixed_html, url, session_obj=session_obj, headers=headers)
        
        # 5. Pack the HTML and all discovered fetched assets straight into a fully fledged ZIP
        zip_path_tmp = create_zip_file(fixed_html, assets, url, session_obj, headers)
        
        # 6. Copy over to persistent download folder
        shutil.copy2(zip_path_tmp, zip_path)
        os.remove(zip_path_tmp)
        
        return send_file(zip_path, as_attachment=True, download_name=f"{safe_domain}.zip")
        
    except Exception as e:
        print(f"Extraction Error: {e}")
        return jsonify({"error": str(e)}), 500

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

