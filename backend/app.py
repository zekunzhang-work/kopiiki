import os
import shutil
import threading
import zipfile
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
from webtwin_assets import create_zip_file, ExtractionCancelled
import uuid
import time
import json
from threading import Lock, Event
from datetime import datetime, timezone
from env_config import load_kopiiki_env


load_kopiiki_env()

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

EXTRACTION_LOCK = Lock()
HISTORY_LOCK = Lock()
EXTRACTION_JOBS = {}
TERMINAL_STATUSES = {"complete", "error", "cancelled"}


# --- Configuration (moved from old WebTwin app.py) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')
EXTRACTED_FOLDER = os.path.join(BASE_DIR, 'extracted_sites')
JOBS_FOLDER = os.path.join(EXTRACTED_FOLDER, 'jobs')
TEMP_DOWNLOAD_FOLDER = os.path.join(DOWNLOAD_FOLDER, '.tmp')
HISTORY_FILE = os.path.join(DOWNLOAD_FOLDER, 'history.json')
MAX_ARCHIVE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {'html', 'css', 'js', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'mp4', 'webm'}
OS_INFO = "macOS" # For simplicity just a string now.

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(EXTRACTED_FOLDER, exist_ok=True)
os.makedirs(JOBS_FOLDER, exist_ok=True)
os.makedirs(TEMP_DOWNLOAD_FOLDER, exist_ok=True)


def cleanup_directory_contents(path):
    os.makedirs(path, exist_ok=True)
    for name in os.listdir(path):
        item_path = os.path.join(path, name)
        try:
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)
        except FileNotFoundError:
            pass


def cleanup_startup_artifacts():
    cleanup_directory_contents(JOBS_FOLDER)
    cleanup_directory_contents(TEMP_DOWNLOAD_FOLDER)


cleanup_startup_artifacts()


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def load_history_unlocked():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as history_file:
            records = json.load(history_file)
            return records if isinstance(records, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_history_unlocked(records):
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    os.makedirs(TEMP_DOWNLOAD_FOLDER, exist_ok=True)
    temp_history_path = os.path.join(TEMP_DOWNLOAD_FOLDER, f"history-{uuid.uuid4().hex}.json")
    with open(temp_history_path, 'w', encoding='utf-8') as history_file:
        json.dump(records, history_file, indent=2)
        history_file.write('\n')
    os.replace(temp_history_path, HISTORY_FILE)


def safe_download_path(filename):
    safe_filename = secure_filename(filename or '')
    if not safe_filename.endswith('.zip') or safe_filename != filename:
        return None, safe_filename

    downloads_root = os.path.abspath(DOWNLOAD_FOLDER)
    file_path = os.path.abspath(os.path.join(DOWNLOAD_FOLDER, safe_filename))
    if os.path.commonpath([downloads_root, file_path]) != downloads_root:
        return None, safe_filename
    return file_path, safe_filename


def enrich_history_record(record):
    enriched = dict(record)
    file_path, _ = safe_download_path(record.get('filename'))
    artifact_status = record.get('artifact_status') or 'none'

    if artifact_status == 'deleted':
        enriched['exists'] = False
        enriched['size_bytes'] = 0
        enriched['artifact_status'] = 'deleted'
        return enriched

    if file_path:
        exists = os.path.exists(file_path)
        enriched['exists'] = exists
        enriched['size_bytes'] = os.path.getsize(file_path) if exists else 0
        enriched['artifact_status'] = 'available' if exists else 'missing'
        return enriched

    enriched['exists'] = False
    enriched['size_bytes'] = 0
    enriched['artifact_status'] = 'none'
    return enriched


def history_records_newest_first():
    with HISTORY_LOCK:
        records = load_history_unlocked()
    enriched = [enrich_history_record(record) for record in records]
    return sorted(enriched, key=lambda record: record.get('created_at') or '', reverse=True)


def append_history_record(record):
    with HISTORY_LOCK:
        records = load_history_unlocked()
        records.append(record)
        save_history_unlocked(records)


def update_history_record(record_id, **fields):
    with HISTORY_LOCK:
        records = load_history_unlocked()
        updated_record = None
        for record in records:
            if record.get('id') == record_id:
                record.update(fields)
                updated_record = dict(record)
                break
        save_history_unlocked(records)
    return updated_record


def mark_interrupted_history_records():
    with HISTORY_LOCK:
        records = load_history_unlocked()
        changed = False
        now = utc_now_iso()
        for record in records:
            if record.get('status') == 'processing':
                record.update({
                    'status': 'interrupted',
                    'message': 'Extraction was interrupted before completion.',
                    'completed_at': now,
                    'artifact_status': 'none',
                    'filename': None,
                    'download_url': None,
                    'relative_path': None,
                    'size_bytes': 0,
                })
                changed = True
        if changed:
            save_history_unlocked(records)


mark_interrupted_history_records()


def cleanup_job_files(output_dir, temp_zip_path):
    if output_dir and os.path.isdir(output_dir):
        shutil.rmtree(output_dir, ignore_errors=True)
    if temp_zip_path and os.path.exists(temp_zip_path):
        try:
            os.remove(temp_zip_path)
        except FileNotFoundError:
            pass


def ensure_not_cancelled(cancel_event):
    if cancel_event and cancel_event.is_set():
        raise ExtractionCancelled("Cancelled by user")


def update_job(extract_id, **fields):
    with EXTRACTION_LOCK:
        job = EXTRACTION_JOBS.get(extract_id)
        if not job:
            return
        job.update(fields)
        if job.get("status") in TERMINAL_STATUSES and not job.get("finished_at"):
            job["finished_at"] = time.time()


def job_progress_snapshot(extract_id):
    with EXTRACTION_LOCK:
        job = EXTRACTION_JOBS.get(extract_id)
        if not job:
            return None
        return {
            "status": job.get("status"),
            "message": job.get("message"),
            "url": job.get("url"),
            "mode": job.get("mode"),
            "download_url": job.get("download_url"),
            "filename": job.get("filename"),
        }


def prune_terminal_jobs_locked(max_age_seconds=300):
    now = time.time()
    stale_ids = [
        extract_id
        for extract_id, job in EXTRACTION_JOBS.items()
        if job.get("status") in TERMINAL_STATUSES
        and job.get("finished_at")
        and now - job["finished_at"] > max_age_seconds
    ]
    for extract_id in stale_ids:
        del EXTRACTION_JOBS[extract_id]


def create_job_paths(extract_id, safe_domain, mode="snapshot"):
    suffix = "-design" if mode == "design" else ""
    artifact_filename = f"{safe_domain}{suffix}-{extract_id[:8]}.zip"
    output_dir = os.path.join(JOBS_FOLDER, extract_id)
    temp_zip_path = os.path.join(TEMP_DOWNLOAD_FOLDER, f"{extract_id}-{artifact_filename}")
    final_zip_path = os.path.join(DOWNLOAD_FOLDER, artifact_filename)
    return output_dir, temp_zip_path, final_zip_path


def extract_with_playwright(url, output_dir, extract_id=None, cancel_event=None):
    """
    Advanced extraction using Playwright:
    1. Handles dynamic content and lazy loading.
    2. intercepts and captures all network responses in memory (solving double-fetch).
    3. injects removable anti-animation CSS.
    """
    def update_progress(msg, status="processing"):
        if extract_id:
            fields = {"message": msg}
            if status:
                fields["status"] = status
            update_job(extract_id, **fields)
                
    update_progress(f"Starting Playwright browser for {url}...")
    print(f"[{threading.current_thread().name}] Starting Playwright extraction for URL: {url}")
    
    html_content = ""
    error_msg = None
    timeout = 30 # seconds
    captured_assets = {} # url -> bytes

    def handle_response(response):
        # Only capture successful responses for assets
        try:
            if cancel_event and cancel_event.is_set():
                return
            if response.ok and response.request.resource_type in ["image", "stylesheet", "script", "font", "media"]:
                url = response.url
                # Avoid capturing data URIs or base64 directly as network events
                if url.startswith("http"):
                    body = response.body()
                    captured_assets[url] = body
        except Exception as e:
            # Body might not be available for some redirects or opaque responses
            pass
                
    ensure_not_cancelled(cancel_event)
    with sync_playwright() as p:
        try:
            ensure_not_cancelled(cancel_event)
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
                
            ensure_not_cancelled(cancel_event)
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
            ensure_not_cancelled(cancel_event)
            response = page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            ensure_not_cancelled(cancel_event)
                
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
                ensure_not_cancelled(cancel_event)
                if not is_main:
                    update_progress(f"Crawling level-1 subpage: {target_url}...")
                    try:
                        ensure_not_cancelled(cancel_event)
                        page.goto(target_url, wait_until="networkidle", timeout=timeout * 1000)
                        ensure_not_cancelled(cancel_event)
                    except ExtractionCancelled:
                        raise
                    except Exception:
                        pass
                    
                ensure_not_cancelled(cancel_event)
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
                    ensure_not_cancelled(cancel_event)
                        
                    update_progress("Scrolling to trigger lazy-loaded elements...")
                ensure_not_cancelled(cancel_event)
                page.evaluate(scroll_script)
                ensure_not_cancelled(cancel_event)
                page.wait_for_timeout(2000)
                ensure_not_cancelled(cancel_event)
                    
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
                ensure_not_cancelled(cancel_event)
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
                ensure_not_cancelled(cancel_event)
                try:
                    sub_html = crawl_page(sub_url)
                    html_results[sub_url] = sub_html
                except ExtractionCancelled:
                    raise
                except Exception as e:
                    print(f"Failed to crawl {sub_url}: {str(e)}")

        except ExtractionCancelled:
             raise
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


def process_extraction(extract_id):
    with EXTRACTION_LOCK:
        job = EXTRACTION_JOBS.get(extract_id)
        if not job:
            return
        url = job["url"]
        mode = job.get("mode", "snapshot")
        output_dir = job["output_dir"]
        temp_zip_path = job["temp_zip_path"]
        final_zip_path = job["final_zip_path"]
        artifact_filename = job["filename"]
        cancel_event = job["cancel_event"]

    try:
        ensure_not_cancelled(cancel_event)
        update_job(extract_id, message="Initializing extraction pipeline...", status="processing")

        artifact_metadata = {}
        if mode == "design":
            from design_capsule import create_design_capsule_zip

            zip_path_tmp, artifact_metadata = create_design_capsule_zip(
                url=url,
                output_dir=output_dir,
                extract_id=extract_id,
                temp_zip_path=temp_zip_path,
                cancel_event=cancel_event,
                progress_callback=lambda message: update_job(extract_id, message=message, status="processing"),
            )
        else:
            # 1. First extract the dynamic rendered HTML freezing animations, AND intercept all assets
            html_results, captured_assets = extract_with_playwright(
                url,
                output_dir,
                extract_id=extract_id,
                cancel_event=cancel_event,
            )

            # 2. Pack the HTML and all discovered fetched assets straight into a fully fledged ZIP
            ensure_not_cancelled(cancel_event)
            update_job(extract_id, message="Packaging everything into a downloadable ZIP archive...")
            zip_path_tmp = create_zip_file(
                html_results,
                captured_assets,
                url,
                output_dir,
                extract_id,
                temp_zip_path=temp_zip_path,
                cancel_event=cancel_event,
            )
        
        ensure_not_cancelled(cancel_event)
        os.replace(zip_path_tmp, final_zip_path)
        artifact_size = os.path.getsize(final_zip_path)
        download_url = f"/api/download/{artifact_filename}"
        complete_message = (
            "Design Capsule generated! Ready to download."
            if mode == "design"
            else "Extraction successful! Ready to download."
        )
        
        update_job(
            extract_id,
            status="complete",
            message=complete_message,
            download_url=download_url,
            filename=artifact_filename,
        )
        update_history_record(
            extract_id,
            status="complete",
            message="Extraction successful! Ready to download.",
            filename=artifact_filename,
            download_url=download_url,
            relative_path=f"downloads/{artifact_filename}",
            size_bytes=artifact_size,
            completed_at=utc_now_iso(),
            artifact_status="available",
            mode=mode,
            artifact_kind="design_capsule" if mode == "design" else "snapshot",
            model=artifact_metadata.get("model"),
            llm_status="complete" if mode == "design" else None,
            confidence=artifact_metadata.get("confidence"),
        )

    except ExtractionCancelled:
        print(f"Extraction Cancelled: {extract_id}")
        update_job(
            extract_id,
            status="cancelled",
            message="Extraction cancelled. Temporary files cleaned.",
            download_url=None,
        )
        update_history_record(
            extract_id,
            status="cancelled",
            message="Extraction cancelled. Temporary files cleaned.",
            filename=None,
            download_url=None,
            relative_path=None,
            size_bytes=0,
            completed_at=utc_now_iso(),
            artifact_status="none",
            llm_status="cancelled" if mode == "design" else None,
        )
    except Exception as e:
        print(f"Extraction Error: {e}")
        error_message = f"Extraction failed: {str(e)}"
        update_job(
            extract_id,
            status="error",
            message=error_message,
            download_url=None,
        )
        update_history_record(
            extract_id,
            status="error",
            message=error_message,
            filename=None,
            download_url=None,
            relative_path=None,
            size_bytes=0,
            completed_at=utc_now_iso(),
            artifact_status="none",
            llm_status="error" if mode == "design" else None,
        )
    finally:
        cleanup_job_files(output_dir, temp_zip_path)

@app.route('/api/extract', methods=['POST'])
def api_extract():
    data = request.json or {}
    url = data.get('url')
    mode = (data.get('mode') or 'snapshot').strip().lower()
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

    if mode not in {"snapshot", "design"}:
        return jsonify({"error": "mode must be either 'snapshot' or 'design'."}), 400

    if not PLAYWRIGHT_AVAILABLE:
        return jsonify({"error": "Playwright is not installed on the backend. Please install it."}), 500

    if mode == "design":
        from gemini_design import ensure_gemini_configured

        gemini_error = ensure_gemini_configured()
        if gemini_error:
            return jsonify({"error": gemini_error}), 400

    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if not domain:
        domain = "extracted_site"
    safe_domain = secure_filename(domain) or "extracted_site"

    # Generate an ID for this extraction job and store it
    extract_id = str(uuid.uuid4())
    output_dir, temp_zip_path, final_zip_path = create_job_paths(extract_id, safe_domain, mode=mode)
    artifact_filename = os.path.basename(final_zip_path)
    cancel_event = Event()
    created_at = utc_now_iso()

    with EXTRACTION_LOCK:
        prune_terminal_jobs_locked()
        active_job = next(
            (
                job
                for job in EXTRACTION_JOBS.values()
                if job.get("status") == "processing"
            ),
            None,
        )
        if active_job:
            return jsonify({
                "error": "Another extraction is already running.",
                "active_extract_id": active_job.get("extract_id"),
            }), 409

        EXTRACTION_JOBS[extract_id] = {
            "extract_id": extract_id,
            "status": "processing",
            "message": "Starting job...",
            "url": url,
            "mode": mode,
            "safe_domain": safe_domain,
            "output_dir": output_dir,
            "temp_zip_path": temp_zip_path,
            "final_zip_path": final_zip_path,
            "cancel_event": cancel_event,
            "filename": artifact_filename,
            "download_url": None,
            "created_at": time.time(),
            "finished_at": None,
        }

    try:
        os.makedirs(output_dir, exist_ok=False)
        os.makedirs(TEMP_DOWNLOAD_FOLDER, exist_ok=True)
        append_history_record({
            "id": extract_id,
            "url": url,
            "domain": domain,
            "safe_domain": safe_domain,
            "status": "processing",
            "message": "Starting job...",
            "filename": None,
            "download_url": None,
            "relative_path": None,
            "size_bytes": 0,
            "mode": mode,
            "artifact_kind": "design_capsule" if mode == "design" else "snapshot",
            "model": None,
            "llm_status": "pending" if mode == "design" else None,
            "created_at": created_at,
            "completed_at": None,
            "artifact_status": "none",
        })
    except Exception as e:
        with EXTRACTION_LOCK:
            EXTRACTION_JOBS.pop(extract_id, None)
        cleanup_job_files(output_dir, temp_zip_path)
        return jsonify({"error": f"Could not prepare extraction workspace: {str(e)}"}), 500
        
    # Start the worker thread
    thread = threading.Thread(target=process_extraction, args=(extract_id,))
    thread.daemon = True
    thread.start()
    
    # Return immediately so the client can connect to SSE
    return jsonify({"extract_id": extract_id})


@app.route('/api/config')
def api_config():
    from gemini_design import ensure_gemini_configured, gemini_mock_enabled, gemini_model_name

    gemini_error = ensure_gemini_configured()
    return jsonify({
        "playwright": {
            "available": PLAYWRIGHT_AVAILABLE,
        },
        "design_ai": {
            "provider": "gemini-developer-api",
            "configured": gemini_error is None,
            "mock": gemini_mock_enabled(),
            "model": gemini_model_name(),
            "missing_reason": gemini_error,
        },
    })
    

@app.route('/api/extract/stream/<extract_id>')
def api_extract_stream(extract_id):
    def event_stream():
        last_message = ""
        last_status = ""
        while True:
            progress = job_progress_snapshot(extract_id)
            if not progress:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Unknown extraction ID'})}\n\n"
                break
                
            # Send an update if status changed, or just to keep connection alive
            if progress["message"] != last_message or progress["status"] != last_status:
                last_message = progress["message"]
                last_status = progress["status"]
                yield f"data: {json.dumps(progress)}\n\n"
                    
            if progress["status"] in TERMINAL_STATUSES:
                # Clean up memory after sending completion
                time.sleep(1) # tiny wait to ensure client gets it
                with EXTRACTION_LOCK:
                    EXTRACTION_JOBS.pop(extract_id, None)
                break
                
            time.sleep(0.5)
            
    return Response(event_stream(), mimetype="text/event-stream")


@app.route('/api/extract/cancel', methods=['POST'])
def cancel_extraction():
    data = request.json or {}
    extract_id = data.get('extract_id')

    with EXTRACTION_LOCK:
        job = EXTRACTION_JOBS.get(extract_id)
        if not job:
            return jsonify({"status": "not_found", "message": "No matching extraction found."}), 404
        if job.get("status") in TERMINAL_STATUSES:
            return jsonify({"status": job["status"], "message": "Extraction already finished."})

        job["cancel_event"].set()
        job["message"] = "Cancellation requested. Stopping extraction..."

    return jsonify({"status": "cancelled", "message": "Cancellation signal sent."})


@app.route('/api/history', methods=['GET'])
def api_history():
    return jsonify({"records": history_records_newest_first()})


@app.route('/api/history/<record_id>', methods=['DELETE'])
def api_delete_history_record(record_id):
    with HISTORY_LOCK:
        records = load_history_unlocked()
        target_record = None
        for record in records:
            if record.get('id') == record_id:
                target_record = record
                break

        if not target_record:
            return jsonify({"status": "not_found", "message": "History record not found."}), 404

        if target_record.get('artifact_status') == 'deleted':
            return jsonify({
                "status": "deleted",
                "message": "Artifact was already deleted.",
                "record": enrich_history_record(target_record),
            })

        file_path, _ = safe_download_path(target_record.get('filename'))
        if not file_path:
            return jsonify({
                "status": "no_artifact",
                "message": "This history record has no downloadable artifact.",
                "record": enrich_history_record(target_record),
            }), 400

        if not os.path.exists(file_path):
            target_record.update({
                "artifact_status": "missing",
                "size_bytes": 0,
            })
            save_history_unlocked(records)
            return jsonify({
                "status": "missing",
                "message": "Artifact file is already missing.",
                "record": enrich_history_record(target_record),
            }), 404

        os.remove(file_path)
        now = utc_now_iso()
        target_record.update({
            "artifact_status": "deleted",
            "deleted_at": now,
            "message": "Artifact deleted.",
            "size_bytes": 0,
        })
        save_history_unlocked(records)

        return jsonify({
            "status": "deleted",
            "message": "Artifact deleted.",
            "record": enrich_history_record(target_record),
        })


@app.route('/api/download/<filename>')
def api_download(filename):
    zip_path, zip_filename = safe_download_path(filename)
    if not zip_path:
        return jsonify({"error": "Invalid download filename"}), 400
    
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
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
