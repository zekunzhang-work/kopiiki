#!/usr/bin/env python3
import argparse
import sys
import os
import uuid
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
from threading import Event

# Add current dir to path to resolve local imports cleanly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import (
    extract_with_playwright,
    create_job_paths,
    cleanup_job_files,
    append_history_record,
    update_history_record,
    utc_now_iso,
)
from webtwin_assets import create_zip_file, ExtractionCancelled


def parse_args():
    parser = argparse.ArgumentParser(description="Run Kopiiki extraction from the command line.")
    parser.add_argument("url", help="Target website URL")
    parser.add_argument(
        "--mode",
        choices=["snapshot", "design"],
        default="snapshot",
        help="Output mode. snapshot creates an offline archive; design creates a Gemini Design Capsule.",
    )
    parser.add_argument(
        "--design",
        action="store_true",
        help="Shortcut for --mode design.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    url = args.url
    mode = "design" if args.design else args.mode

    if mode == "design":
        from gemini_design import ensure_gemini_configured

        gemini_error = ensure_gemini_configured()
        if gemini_error:
            print(f"❌ ERROR: {gemini_error}")
            sys.exit(1)

    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if not domain:
        domain = "extracted_site"
        
    safe_domain = secure_filename(domain) or "extracted_site"
    
    extract_id = "cli-" + str(uuid.uuid4())
    output_dir, temp_zip_path, zip_path = create_job_paths(extract_id, safe_domain, mode=mode)
    artifact_filename = os.path.basename(zip_path)
    cancel_event = Event()
    os.makedirs(output_dir, exist_ok=False)
    append_history_record({
        "id": extract_id,
        "url": url,
        "domain": domain,
        "safe_domain": safe_domain,
        "status": "processing",
        "message": "Starting CLI job...",
        "filename": None,
        "download_url": None,
        "relative_path": None,
        "size_bytes": 0,
        "mode": mode,
        "artifact_kind": "design_capsule" if mode == "design" else "snapshot",
        "model": None,
        "llm_status": "pending" if mode == "design" else None,
        "created_at": utc_now_iso(),
        "completed_at": None,
        "artifact_status": "none",
    })
    
    print(f"========== KOPIIKI CLI ==========")
    print(f"Target URL : {url}")
    print(f"Domain     : {domain}")
    print(f"Mode       : {mode}")
    print(f"=================================\n")
    
    try:
        artifact_metadata = {}
        if mode == "design":
            from design_capsule import create_design_capsule_zip

            print("[1/3] Capturing browser design evidence...")
            print("[2/3] Asking Gemini to synthesize DESIGN.md...")
            zip_path_tmp, artifact_metadata = create_design_capsule_zip(
                url=url,
                output_dir=output_dir,
                extract_id=extract_id,
                temp_zip_path=temp_zip_path,
                cancel_event=cancel_event,
                progress_callback=lambda message: print(f"      {message}"),
            )
        else:
            # 1. Run the headless Playwright scraper
            print("[1/2] Launching Headless Chromium & Deep Crawling...")
            html_results, captured_assets = extract_with_playwright(
                url,
                output_dir,
                extract_id=extract_id,
                cancel_event=cancel_event,
            )

            # 2. Package into ZIP with AST linking
            print("[2/2] Stitching DOM AST & Packaging Assets into ZIP...")
            zip_path_tmp = create_zip_file(
                html_results,
                captured_assets,
                url,
                output_dir,
                extract_id,
                temp_zip_path=temp_zip_path,
                cancel_event=cancel_event,
            )
        
        # 3. Finalize
        os.replace(zip_path_tmp, zip_path)
        artifact_size = os.path.getsize(zip_path)
        complete_message = "CLI Design Capsule generated." if mode == "design" else "CLI extraction successful."
        update_history_record(
            extract_id,
            status="complete",
            message=complete_message,
            filename=artifact_filename,
            download_url=f"/api/download/{artifact_filename}",
            relative_path=f"downloads/{artifact_filename}",
            size_bytes=artifact_size,
            completed_at=utc_now_iso(),
            artifact_status="available",
            model=artifact_metadata.get("model"),
            llm_status="complete" if mode == "design" else None,
            confidence=artifact_metadata.get("confidence"),
        )
        
        print(f"\n✅ SUCCESS!")
        print(f"Extract saved locally to: {zip_path}")

    except KeyboardInterrupt:
        cancel_event.set()
        update_history_record(
            extract_id,
            status="cancelled",
            message="CLI extraction cancelled.",
            completed_at=utc_now_iso(),
            artifact_status="none",
            llm_status="cancelled" if mode == "design" else None,
        )
        print("\nCancelled by user.")
        sys.exit(130)
    except ExtractionCancelled:
        update_history_record(
            extract_id,
            status="cancelled",
            message="CLI extraction cancelled.",
            completed_at=utc_now_iso(),
            artifact_status="none",
            llm_status="cancelled" if mode == "design" else None,
        )
        print("\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        update_history_record(
            extract_id,
            status="error",
            message=f"CLI extraction failed: {e}",
            completed_at=utc_now_iso(),
            artifact_status="none",
            llm_status="error" if mode == "design" else None,
        )
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
    finally:
        cleanup_job_files(output_dir, temp_zip_path)
        
if __name__ == "__main__":
    main()
