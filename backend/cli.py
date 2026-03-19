#!/usr/bin/env python3
import sys
import os
import uuid
import shutil
from urllib.parse import urlparse
from werkzeug.utils import secure_filename

# Add current dir to path to resolve local imports cleanly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import extract_with_playwright, CANCEL_TOKEN, EXTRACTION_PROGRESS
from webtwin_assets import create_zip_file

def main():
    if len(sys.argv) < 2:
        print("Usage: python cli.py <url>")
        print("Example: python cli.py https://example.com")
        sys.exit(1)

    url = sys.argv[1]
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if not domain:
        domain = "extracted_site"
        
    safe_domain = secure_filename(domain)
    
    # Path configuration
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXTRACTED_FOLDER = os.path.join(BASE_DIR, 'extracted_sites')
    DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')
    
    os.makedirs(EXTRACTED_FOLDER, exist_ok=True)
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    
    output_dir = os.path.join(EXTRACTED_FOLDER, safe_domain)
    zip_path = os.path.join(DOWNLOAD_FOLDER, f"{safe_domain}.zip")
    
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    extract_id = "cli-" + str(uuid.uuid4())
    EXTRACTION_PROGRESS[extract_id] = {"message": "Starting...", "status": "processing"}
    
    print(f"========== KOPIIKI CLI ==========")
    print(f"Target URL : {url}")
    print(f"Domain     : {domain}")
    print(f"=================================\n")
    
    try:
        # 1. Run the headless Playwright scraper
        print("[1/2] Launching Headless Chromium & Deep Crawling...")
        html_results, captured_assets = extract_with_playwright(url, output_dir, extract_id=extract_id)
        
        # 2. Package into ZIP with AST linking
        print("[2/2] Stitching DOM AST & Packaging Assets into ZIP...")
        zip_path_tmp = create_zip_file(html_results, captured_assets, url, output_dir, extract_id)
        
        # 3. Finalize
        shutil.copy2(zip_path_tmp, zip_path)
        os.remove(zip_path_tmp)
        
        print(f"\n✅ SUCCESS!")
        print(f"Extract saved locally to: {zip_path}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
        
if __name__ == "__main__":
    main()
