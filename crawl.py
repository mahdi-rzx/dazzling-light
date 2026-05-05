#!/usr/bin/env python3
"""
Incremental crawler for chem.libretexts.org.
- download_timeout: maximum total time (seconds) for the entire crawl job
- Stops gracefully when time is up, committing all progress
"""

import os
import time
import subprocess
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
from hashlib import md5

# ------------------------------------------------------------
# Configure git identity FIRST
# ------------------------------------------------------------
subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
OUTPUT_DIR = "archive"
FRONTIER_FILE = "frontier.txt"
DOWNLOADED_FILE = "downloaded.txt"
ERRORS_FILE = "errors.txt"
ASSETS_DIR = "assets"
ASSET_MAP_FILE = "asset_map.txt"
BASE_DOMAIN = "chem.libretexts.org"
SEED_URL = "https://chem.libretexts.org/"

# JOB_TIMEOUT = maximum seconds for the entire crawl run
JOB_TIMEOUT = float(os.environ.get("DOWNLOAD_TIMEOUT", 300))  # default 5 minutes
# MAX_URLS = cap on URLs per run (0 = unlimited, stop only on timeout)
MAX_URLS = int(os.environ.get("MAX_URLS_PER_RUN", 0))
# Per-request timeout (kept short so we don't waste job time on one slow URL)
REQUEST_TIMEOUT = 30

# Asset domains to download from
ASSET_DOMAINS = [
    "chem.libretexts.org",
    "a.mtstatic.com",
    "cdn.libretexts.net",
    "cdnjs.cloudflare.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "pro.fontawesome.com",
    "use.fontawesome.com",
    "cdn.jsdelivr.net",
    "static.cloudflareinsights.com",
]

# ------------------------------------------------------------
# Asset Map (persistent deduplication)
# ------------------------------------------------------------
def load_asset_map():
    """Load existing asset URL -> local path mapping."""
    asset_map = {}
    if os.path.exists(ASSET_MAP_FILE):
        with open(ASSET_MAP_FILE, "r") as f:
            for line in f:
                if " -> " in line:
                    url, local = line.strip().split(" -> ", 1)
                    asset_map[url] = local
    return asset_map

def save_asset_map(asset_map):
    """Save asset map to file."""
    with open(ASSET_MAP_FILE, "w") as f:
        for url, local in sorted(asset_map.items()):
            f.write(f"{url} -> {local}\n")

def asset_local_path(url):
    """Generate a unique local path for an asset."""
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1] or ""
    
    url_hash = md5(url.encode()).hexdigest()[:12]
    filename = f"{url_hash}{ext}"
    
    if ext in [".css"]:
        return os.path.join(ASSETS_DIR, "css", filename)
    elif ext in [".js"]:
        return os.path.join(ASSETS_DIR, "js", filename)
    elif ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp"]:
        return os.path.join(ASSETS_DIR, "img", filename)
    elif ext in [".woff", ".woff2", ".ttf", ".eot", ".otf"]:
        return os.path.join(ASSETS_DIR, "fonts", filename)
    else:
        return os.path.join(ASSETS_DIR, "other", filename)

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def clean_url(url):
    """Remove fragment and query string to avoid duplicates."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

def local_path(url):
    """Convert URL to a local file path."""
    parsed = urlparse(url)
    path = parsed.path.lstrip("/")
    if not path:
        path = "index.html"
    else:
        parts = path.split("/")
        last = parts[-1]
        if "." not in last:
            parts.append("index.html")
        path = "/".join(parts)
    return os.path.join(OUTPUT_DIR, parsed.netloc, path)

def ensure_dir(filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

def load_set(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return {line.strip() for line in f if line.strip()}
    return set()

def append_line(filepath, line):
    with open(filepath, "a") as f:
        f.write(line + "\n")

def remove_line(filepath, line):
    if not os.path.exists(filepath):
        return
    with open(filepath, "r") as f:
        lines = f.readlines()
    with open(filepath, "w") as f:
        for l in lines:
            if l.strip() != line.strip():
                f.write(l)

def git_commit_push(files, message):
    """Commit and push, but don't crash if push fails."""
    try:
        subprocess.run(["git", "add"] + files, check=True, timeout=30)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff.returncode != 0:
            subprocess.run(["git", "commit", "-m", message], check=True, timeout=30)
            subprocess.run(["git", "push"], check=True, timeout=60)
        else:
            print("  No changes to commit.")
    except subprocess.TimeoutExpired:
        print("  Git operation timed out, continuing...")
    except Exception as e:
        print(f"  Git error (non-fatal): {e}")

def should_download_asset(url):
    """Check if this asset URL should be downloaded."""
    try:
        parsed = urlparse(url)
        return parsed.netloc in ASSET_DOMAINS
    except:
        return False

def get_or_download_asset(url, asset_map):
    """Get local path for asset, downloading if needed."""
    if url in asset_map:
        return "/" + asset_map[url], False
    
    try:
        local = asset_local_path(url)
        ensure_dir(local)
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            with open(local, "wb") as f:
                f.write(resp.content)
            asset_map[url] = local
            return "/" + local, True
    except Exception as e:
        print(f"  Failed to download asset {url}: {e}")
    
    return None, False

def rewrite_html_for_local_assets(html_content, page_url, asset_map):
    """Replace asset URLs with local paths."""
    soup = BeautifulSoup(html_content, "html.parser")
    new_assets = []
    
    for link in soup.find_all("link", href=True):
        asset_url = urljoin(page_url, link["href"])
        if should_download_asset(asset_url):
            local, is_new = get_or_download_asset(asset_url, asset_map)
            if local:
                link["href"] = local
                if is_new:
                    new_assets.append(asset_map[asset_url])
    
    for script in soup.find_all("script", src=True):
        asset_url = urljoin(page_url, script["src"])
        if should_download_asset(asset_url):
            local, is_new = get_or_download_asset(asset_url, asset_map)
            if local:
                script["src"] = local
                if is_new:
                    new_assets.append(asset_map[asset_url])
    
    for img in soup.find_all("img", src=True):
        if img["src"].startswith("data:"):
            continue
        asset_url = urljoin(page_url, img["src"])
        if should_download_asset(asset_url):
            local, is_new = get_or_download_asset(asset_url, asset_map)
            if local:
                img["src"] = local
                if is_new:
                    new_assets.append(asset_map[asset_url])
    
    for source in soup.find_all("source", src=True):
        asset_url = urljoin(page_url, source["src"])
        if should_download_asset(asset_url):
            local, is_new = get_or_download_asset(asset_url, asset_map)
            if local:
                source["src"] = local
                if is_new:
                    new_assets.append(asset_map[asset_url])
    
    return str(soup), new_assets

def time_remaining(start_time, timeout):
    """Check if we have time left. Returns (remaining_seconds, should_stop)."""
    elapsed = time.time() - start_time
    remaining = timeout - elapsed
    if remaining <= 0:
        return 0, True
    # Stop if less than 30 seconds remain (save time for git push)
    if remaining < 30:
        return remaining, True
    return remaining, False

# ------------------------------------------------------------
# Main crawl logic
# ------------------------------------------------------------
def main():
    start_time = time.time()
    
    downloaded = load_set(DOWNLOADED_FILE)
    errors = load_set(ERRORS_FILE)
    asset_map = load_asset_map()
    
    print(f"Job timeout: {JOB_TIMEOUT}s ({JOB_TIMEOUT/60:.1f} minutes)")
    print(f"Max URLs: {'unlimited' if MAX_URLS == 0 else MAX_URLS}")
    print(f"Cached assets: {len(asset_map)}")
    print(f"Already downloaded: {len(downloaded)} pages")
    print()

    # Load or create frontier
    frontier = []
    if os.path.exists(FRONTIER_FILE):
        with open(FRONTIER_FILE) as f:
            frontier = [line.strip() for line in f if line.strip()]
        print(f"Frontier: {len(frontier)} URLs waiting")
    else:
        frontier.append(SEED_URL)
        with open(FRONTIER_FILE, "w") as f:
            f.write(SEED_URL + "\n")
        subprocess.run(["git", "add", FRONTIER_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Initialize frontier"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Initialized frontier with seed URL")

    seen = downloaded | errors | set(frontier)
    counter = 0
    total_new_assets = 0

    for url in frontier[:]:
        # ⏰ Check time before each URL
        remaining, should_stop = time_remaining(start_time, JOB_TIMEOUT)
        if should_stop:
            print(f"\n⏰ Time's up! ({JOB_TIMEOUT}s elapsed)")
            print(f"   Processed: {counter} pages this run")
            print(f"   New assets: {total_new_assets}")
            break
        
        # Check URL limit
        if MAX_URLS > 0 and counter >= MAX_URLS:
            print(f"\n📊 Reached max URLs limit ({MAX_URLS})")
            break
        
        url = clean_url(url.strip())
        if not url:
            continue

        # Skip already processed
        if url in downloaded or url in errors:
            print(f"⊘ Already processed: {url}")
            remove_line(FRONTIER_FILE, url)
            git_commit_push([FRONTIER_FILE], f"Remove stale {url}")
            continue

        print(f"[{counter+1}] Downloading: {url}")
        print(f"    ⏳ {remaining:.0f}s remaining")

        try:
            resp = requests.get(url, timeout=min(REQUEST_TIMEOUT, remaining), allow_redirects=True)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"    ⚠ Timeout/connection error: {e}")
            continue  # stays in frontier, retry next run
        except Exception as e:
            print(f"    ⚠ Unexpected error: {e}")
            continue

        # Check time again after download
        remaining, should_stop = time_remaining(start_time, JOB_TIMEOUT)
        if should_stop:
            print(f"\n⏰ Ran out of time after downloading {url}")
            print(f"   (URL will be processed next run)")
            break

        status = resp.status_code

        if status == 200:
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                print(f"    ⊘ Skipping non-HTML: {content_type}")
                remove_line(FRONTIER_FILE, url)
                seen.add(url)
                git_commit_push([FRONTIER_FILE], f"Skip non-HTML {url}")
                continue

            content = resp.text
            
            # Process assets
            print(f"    📦 Processing assets...")
            rewritten_html, new_assets = rewrite_html_for_local_assets(content, url, asset_map)
            total_new_assets += len(new_assets)
            if new_assets:
                print(f"    ✨ Downloaded {len(new_assets)} new assets")
            
            # Save HTML
            filepath = local_path(url)
            ensure_dir(filepath)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(rewritten_html)

            # Mark as downloaded
            append_line(DOWNLOADED_FILE, url)
            downloaded.add(url)
            remove_line(FRONTIER_FILE, url)
            seen.add(url)

            # Extract links (quick operation)
            soup = BeautifulSoup(content, "html.parser")
            new_links = 0
            for a in soup.find_all("a", href=True):
                abs_link = urljoin(url, a["href"])
                parsed = urlparse(abs_link)
                if parsed.netloc == BASE_DOMAIN:
                    cleaned = clean_url(abs_link)
                    skip_ext = [".pdf", ".zip", ".png", ".jpg", ".jpeg", 
                               ".gif", ".svg", ".css", ".js", ".ico",
                               ".woff", ".woff2", ".ttf", ".mp4", ".mp3"]
                    if not any(cleaned.lower().endswith(ext) for ext in skip_ext):
                        if cleaned not in seen:
                            append_line(FRONTIER_FILE, cleaned)
                            seen.add(cleaned)
                            new_links += 1
            if new_links:
                print(f"    🔗 Found {new_links} new links")

            # Commit
            all_files = [filepath, FRONTIER_FILE, DOWNLOADED_FILE]
            if new_assets:
                all_files += new_assets
                all_files.append(ASSET_MAP_FILE)
                save_asset_map(asset_map)
            
            print(f"    💾 Committing...")
            git_commit_push(all_files, f"Add {url}")
            counter += 1

        elif status == 429 or status >= 500:
            print(f"    ⚠ Temporary error {status}, will retry")
            continue
        else:
            print(f"    ⊘ Permanent error {status}")
            append_line(ERRORS_FILE, url)
            errors.add(url)
            remove_line(FRONTIER_FILE, url)
            seen.add(url)
            git_commit_push([FRONTIER_FILE, ERRORS_FILE], f"Error {status}: {url}")
            counter += 1

    # Final summary
    elapsed = time.time() - start_time
    print(f"\n{'='*50}")
    print(f"✅ Run complete!")
    print(f"   Time: {elapsed:.0f}s of {JOB_TIMEOUT}s budget")
    print(f"   Pages: {counter} processed")
    print(f"   Assets: {total_new_assets} new (total: {len(asset_map)})")
    print(f"   Frontier: {len(load_set(FRONTIER_FILE))} remaining")
    print(f"   Downloaded: {len(downloaded)} total")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
