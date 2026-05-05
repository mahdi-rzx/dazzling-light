#!/usr/bin/env python3
"""
Incremental crawler for chem.libretexts.org - with deduplicated asset downloading.
- Downloads each unique asset ONCE
- All pages point to the same local asset files
- Much more efficient for large sites
"""

import os
import re
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
ASSET_MAP_FILE = "asset_map.txt"  # Maps original URL -> local path
BASE_DOMAIN = "chem.libretexts.org"
SEED_URL = "https://chem.libretexts.org/"

TIMEOUT = float(os.environ.get("DOWNLOAD_TIMEOUT", 30))
MAX_URLS = int(os.environ.get("MAX_URLS_PER_RUN", 0))

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
    
    # Create a hash-based filename to avoid collisions
    url_hash = md5(url.encode()).hexdigest()[:12]
    filename = f"{url_hash}{ext}"
    
    # Organize by file type
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
    subprocess.run(["git", "add"] + files, check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode != 0:
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "push"], check=True)
    else:
        print("No changes to commit.")

def should_download_asset(url):
    """Check if this asset URL should be downloaded."""
    try:
        parsed = urlparse(url)
        return parsed.netloc in ASSET_DOMAINS
    except:
        return False

def get_or_download_asset(url, asset_map):
    """Get local path for asset, downloading if needed.
    Returns: (local_path, is_new)"""
    
    # Check if we already have this asset
    if url in asset_map:
        return "/" + asset_map[url], False
    
    try:
        local = asset_local_path(url)
        
        # Download the asset
        ensure_dir(local)
        resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            with open(local, "wb") as f:
                f.write(resp.content)
            
            # Update mapping
            asset_map[url] = local
            return "/" + local, True
    except Exception as e:
        print(f"  Failed to download asset {url}: {e}")
    
    return None, False

def rewrite_html_for_local_assets(html_content, page_url, asset_map):
    """Replace asset URLs with local paths using the asset map."""
    soup = BeautifulSoup(html_content, "html.parser")
    new_assets = []
    
    # Handle <link> tags (CSS, favicon, etc.)
    for link in soup.find_all("link", href=True):
        asset_url = urljoin(page_url, link["href"])
        if should_download_asset(asset_url):
            local, is_new = get_or_download_asset(asset_url, asset_map)
            if local:
                link["href"] = local
                if is_new:
                    new_assets.append(asset_map[asset_url])
    
    # Handle <script> tags
    for script in soup.find_all("script", src=True):
        asset_url = urljoin(page_url, script["src"])
        if should_download_asset(asset_url):
            local, is_new = get_or_download_asset(asset_url, asset_map)
            if local:
                script["src"] = local
                if is_new:
                    new_assets.append(asset_map[asset_url])
    
    # Handle <img> tags
    for img in soup.find_all("img", src=True):
        # Don't rewrite data: URIs
        if img["src"].startswith("data:"):
            continue
        asset_url = urljoin(page_url, img["src"])
        if should_download_asset(asset_url):
            local, is_new = get_or_download_asset(asset_url, asset_map)
            if local:
                img["src"] = local
                if is_new:
                    new_assets.append(asset_map[asset_url])
    
    # Handle <source> tags for video/audio
    for source in soup.find_all("source", src=True):
        asset_url = urljoin(page_url, source["src"])
        if should_download_asset(asset_url):
            local, is_new = get_or_download_asset(asset_url, asset_map)
            if local:
                source["src"] = local
                if is_new:
                    new_assets.append(asset_map[asset_url])
    
    return str(soup), new_assets

# ------------------------------------------------------------
# Main crawl logic
# ------------------------------------------------------------
def main():
    downloaded = load_set(DOWNLOADED_FILE)
    errors = load_set(ERRORS_FILE)
    asset_map = load_asset_map()
    
    print(f"Loaded {len(asset_map)} cached assets")

    # Load or create frontier
    frontier = []
    if os.path.exists(FRONTIER_FILE):
        with open(FRONTIER_FILE) as f:
            frontier = [line.strip() for line in f if line.strip()]
    else:
        frontier.append(SEED_URL)
        with open(FRONTIER_FILE, "w") as f:
            f.write(SEED_URL + "\n")
        subprocess.run(["git", "add", FRONTIER_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Initialize frontier"], check=True)
        subprocess.run(["git", "push"], check=True)

    seen = downloaded | errors | set(frontier)
    counter = 0
    total_new_assets = 0

    for url in frontier[:]:
        url = clean_url(url.strip())
        if not url:
            continue

        if url in downloaded or url in errors:
            print(f"Already processed {url}, removing from frontier.")
            remove_line(FRONTIER_FILE, url)
            git_commit_push([FRONTIER_FILE], f"Remove stale {url} from frontier")
            continue

        if MAX_URLS > 0 and counter >= MAX_URLS:
            print(f"Reached max_urls_per_run = {MAX_URLS}, stopping.")
            break

        print(f"Processing {url}...")

        try:
            resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"  Timeout/connection error: {e}. Will retry later.")
            continue
        except Exception as e:
            print(f"  Unexpected error: {e}. Keeping in frontier.")
            continue

        status = resp.status_code

        if status == 200:
            # Only process HTML pages
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                print(f"  Skipping non-HTML content: {content_type}")
                remove_line(FRONTIER_FILE, url)
                seen.add(url)
                git_commit_push([FRONTIER_FILE], f"Skip non-HTML {url}")
                continue

            content = resp.text
            
            # Download assets and rewrite HTML
            print(f"  Processing assets...")
            rewritten_html, new_assets = rewrite_html_for_local_assets(content, url, asset_map)
            total_new_assets += len(new_assets)
            
            # Save the HTML page
            filepath = local_path(url)
            ensure_dir(filepath)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(rewritten_html)

            # Mark as downloaded
            append_line(DOWNLOADED_FILE, url)
            downloaded.add(url)
            remove_line(FRONTIER_FILE, url)
            seen.add(url)

            # Extract links for crawling
            soup = BeautifulSoup(content, "html.parser")
            for a in soup.find_all("a", href=True):
                abs_link = urljoin(url, a["href"])
                parsed = urlparse(abs_link)
                if parsed.netloc == BASE_DOMAIN:
                    cleaned = clean_url(abs_link)
                    # Skip files we don't want to crawl
                    skip_extensions = [".pdf", ".zip", ".png", ".jpg", ".jpeg", 
                                      ".gif", ".svg", ".css", ".js", ".ico", 
                                      ".woff", ".woff2", ".ttf", ".mp4", ".mp3"]
                    if not any(cleaned.lower().endswith(ext) for ext in skip_extensions):
                        if cleaned not in seen:
                            append_line(FRONTIER_FILE, cleaned)
                            seen.add(cleaned)

            # Commit everything
            all_files = [filepath, FRONTIER_FILE, DOWNLOADED_FILE]
            if new_assets:
                all_files += new_assets
                all_files.append(ASSET_MAP_FILE)
                save_asset_map(asset_map)
            
            git_commit_push(all_files, f"Add {url} [+{len(new_assets)} new assets]")
            counter += 1

        elif status == 429 or status >= 500:
            print(f"  Temporary error {status}. Keeping in frontier.")
            continue
        else:
            print(f"  Permanent error {status}. Recording and skipping.")
            append_line(ERRORS_FILE, url)
            errors.add(url)
            remove_line(FRONTIER_FILE, url)
            seen.add(url)
            git_commit_push([FRONTIER_FILE, ERRORS_FILE], f"Mark {url} as error {status}")
            counter += 1

    print(f"Run completed. Processed {counter} pages, downloaded {total_new_assets} new assets.")
    print(f"Total assets in cache: {len(asset_map)}")

if __name__ == "__main__":
    main()
