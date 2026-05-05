#!/usr/bin/env python3
"""
Focused crawler for chem.libretexts.org
- Analytical, Organic, Inorganic, Physical/Theoretical, General Chemistry
- Downloads HTML pages + content images
- Resumable with per‑page commits
- Job‑level timeout, skips non‑HTML files
- Saves pages directly into chem.libretexts.org/ (no "archive" prefix)
"""

import os
import time
import subprocess
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote, urlunparse
from hashlib import md5

# ------------------------------------------------------------
# Git identity (must run before any git commands)
# ------------------------------------------------------------
subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
OUTPUT_DIR = "chem.libretexts.org"          # pages saved here directly
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
FRONTIER_FILE = "frontier.txt"
DOWNLOADED_FILE = "downloaded.txt"
ERRORS_FILE = "errors.txt"
IMAGE_MAP_FILE = "image_map.txt"            # URL → local filename

BASE_DOMAIN = "chem.libretexts.org"

# Corrected subject entry points (from the actual Bookshelves page)
SEED_URLS = [
    "https://chem.libretexts.org/Bookshelves/Analytical_Chemistry",
    "https://chem.libretexts.org/Bookshelves/Organic_Chemistry",
    "https://chem.libretexts.org/Bookshelves/Inorganic_Chemistry",
    "https://chem.libretexts.org/Bookshelves/Physical_and_Theoretical_Chemistry_Textbook_Maps",
    "https://chem.libretexts.org/Bookshelves/General_Chemistry",
]

# URL prefixes that are allowed (subpages of the seeds)
ALLOWED_PREFIXES = [url.rstrip("/") for url in SEED_URLS]

# Job‑level timeout (seconds)
JOB_TIMEOUT = float(os.environ.get("DOWNLOAD_TIMEOUT", 300))
# Max URLs per run (0 = unlimited)
MAX_URLS = int(os.environ.get("MAX_URLS_PER_RUN", 0))
# Per‑request timeout
REQUEST_TIMEOUT = 30

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def clean_url(url):
    """Remove fragment and query string."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

def local_path(url):
    """Convert page URL → local file path inside OUTPUT_DIR."""
    parsed = urlparse(url)
    path = unquote(parsed.path).strip("/")
    if not path:
        return os.path.join(OUTPUT_DIR, "index.html")
    if "." in path.split("/")[-1]:
        return os.path.join(OUTPUT_DIR, path)
    else:
        return os.path.join(OUTPUT_DIR, path, "index.html")

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
    try:
        subprocess.run(["git", "add"] + files, check=True, timeout=30)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff.returncode != 0:
            subprocess.run(["git", "commit", "-m", message], check=True, timeout=30)
            subprocess.run(["git", "push"], check=True, timeout=60)
    except subprocess.TimeoutExpired:
        print("  Git timeout, continuing...")
    except Exception as e:
        print(f"  Git error (non‑fatal): {e}")

def time_remaining(start_time, timeout):
    elapsed = time.time() - start_time
    remaining = timeout - elapsed
    if remaining <= 30:
        return 0, True
    return remaining, False

def is_allowed_url(url):
    """Only crawl URLs that are under one of ALLOWED_PREFIXES."""
    for prefix in ALLOWED_PREFIXES:
        if url.startswith(prefix):
            return True
    return False

# ------------------------------------------------------------
# Image downloading
# ------------------------------------------------------------
def load_image_map():
    """Return dict {original_url: local_filename} and set of downloaded hashes."""
    imap = {}
    if os.path.exists(IMAGE_MAP_FILE):
        with open(IMAGE_MAP_FILE, "r") as f:
            for line in f:
                if " -> " in line:
                    url, local = line.strip().split(" -> ", 1)
                    imap[url] = local
    return imap

def save_image_map(imap):
    with open(IMAGE_MAP_FILE, "w") as f:
        for url, local in sorted(imap.items()):
            f.write(f"{url} -> {local}\n")

def get_image_filename(url):
    """Unique hash‑based filename in IMAGES_DIR."""
    ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
    h = md5(url.encode()).hexdigest()[:12]
    return os.path.join(IMAGES_DIR, f"{h}{ext}")

def download_and_rewrite_images(html, page_url, image_map):
    """
    Find images inside the main content area,
    download them, and rewrite src to local paths.
    Returns (modified_html, list_of_new_local_files)
    """
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".mt-content-container")  # main content div
    if not content:
        return html, []   # no content container, skip

    new_files = []
    for img in content.find_all("img", src=True):
        src = img["src"]
        if src.startswith("data:"):
            continue
        abs_url = urljoin(page_url, src)
        parsed = urlparse(abs_url)
        # Only download images from our own domain
        if parsed.netloc != BASE_DOMAIN:
            continue  # skip external hotlinked images

        if abs_url in image_map:
            local_path = image_map[abs_url]
        else:
            local_path = get_image_filename(abs_url)
            try:
                ensure_dir(local_path)
                r = requests.get(abs_url, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    with open(local_path, "wb") as f:
                        f.write(r.content)
                    image_map[abs_url] = local_path
                    new_files.append(local_path)
                else:
                    continue
            except Exception as e:
                print(f"  ⚠ Image download failed: {abs_url} ({e})")
                continue

        # Rewrite src relative to OUTPUT_DIR root
        relative = os.path.relpath(local_path, OUTPUT_DIR)
        img["src"] = relative

    return str(soup), new_files

# ------------------------------------------------------------
# Main crawl
# ------------------------------------------------------------
def main():
    start_time = time.time()

    downloaded = load_set(DOWNLOADED_FILE)
    errors = load_set(ERRORS_FILE)
    image_map = load_image_map()

    print(f"Job timeout: {JOB_TIMEOUT}s ({JOB_TIMEOUT/60:.1f} min)")
    print(f"Max URLs: {'unlimited' if MAX_URLS == 0 else MAX_URLS}")
    print(f"Already downloaded: {len(downloaded)} pages")
    print(f"Images cached: {len(image_map)}\n")

    # Load or create frontier
    frontier = []
    if os.path.exists(FRONTIER_FILE):
        with open(FRONTIER_FILE) as f:
            frontier = [line.strip() for line in f if line.strip()]
        print(f"Frontier: {len(frontier)} URLs waiting")
    else:
        frontier = SEED_URLS.copy()
        with open(FRONTIER_FILE, "w") as f:
            for url in frontier:
                f.write(url + "\n")
        subprocess.run(["git", "add", FRONTIER_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Initialize frontier with 5 chemistry subjects"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Seeded frontier with 5 subject roots")

    seen = downloaded | errors | set(frontier)
    counter = 0

    for url in frontier[:]:
        remaining, should_stop = time_remaining(start_time, JOB_TIMEOUT)
        if should_stop:
            print(f"\n⏰ Time's up! ({JOB_TIMEOUT}s)")
            print(f"   Processed: {counter} pages this run")
            break

        if MAX_URLS > 0 and counter >= MAX_URLS:
            print(f"\n📊 Reached max URLs limit ({MAX_URLS})")
            break

        url = clean_url(url.strip())
        if not url:
            continue

        # Enforce subject boundaries
        if not is_allowed_url(url):
            print(f"⊘ Out of scope: {url}")
            remove_line(FRONTIER_FILE, url)
            seen.add(url)
            git_commit_push([FRONTIER_FILE], f"Remove out‑of‑scope {url}")
            continue

        if url in downloaded or url in errors:
            remove_line(FRONTIER_FILE, url)
            git_commit_push([FRONTIER_FILE], f"Skip {url}")
            continue

        print(f"[{counter+1}] {url} (⏳ {remaining:.0f}s)")

        try:
            resp = requests.get(url, timeout=min(REQUEST_TIMEOUT, remaining), allow_redirects=True)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"  ⚠ {e}")
            continue
        except Exception as e:
            print(f"  ⚠ {e}")
            continue

        remaining, should_stop = time_remaining(start_time, JOB_TIMEOUT)
        if should_stop:
            print(f"  ⏰ Stopping after download")
            break

        status = resp.status_code

        if status == 200:
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                remove_line(FRONTIER_FILE, url)
                seen.add(url)
                git_commit_push([FRONTIER_FILE], f"Skip non-HTML {url}")
                continue

            # Process images and rewrite HTML
            try:
                html, new_images = download_and_rewrite_images(resp.text, url, image_map)
                if new_images:
                    print(f"  🖼 {len(new_images)} new images downloaded")
            except Exception as e:
                print(f"  ⚠ Image processing error: {e}")
                html = resp.text
                new_images = []

            # Save page
            filepath = local_path(url)
            ensure_dir(filepath)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)

            # Update state
            append_line(DOWNLOADED_FILE, url)
            downloaded.add(url)
            remove_line(FRONTIER_FILE, url)
            seen.add(url)

            # Extract new links (only within allowed subjects)
            soup = BeautifulSoup(resp.text, "html.parser")
            new_links = 0
            for a in soup.find_all("a", href=True):
                abs_link = urljoin(url, a["href"])
                parsed = urlparse(abs_link)
                if parsed.netloc != BASE_DOMAIN:
                    continue
                cleaned = clean_url(abs_link)
                if not is_allowed_url(cleaned):
                    continue
                # Skip obviously non‑HTML files
                skip_ext = [".pdf", ".zip", ".png", ".jpg", ".jpeg",
                           ".gif", ".svg", ".css", ".js", ".ico",
                           ".woff", ".woff2", ".ttf", ".mp4", ".mp3"]
                if any(cleaned.lower().endswith(ext) for ext in skip_ext):
                    continue
                if cleaned not in seen:
                    append_line(FRONTIER_FILE, cleaned)
                    seen.add(cleaned)
                    new_links += 1

            if new_links:
                print(f"  🔗 {new_links} new links")

            # Commit everything
            all_files = [filepath, FRONTIER_FILE, DOWNLOADED_FILE]
            if new_images:
                all_files.extend(new_images)
                all_files.append(IMAGE_MAP_FILE)
                save_image_map(image_map)
            git_commit_push(all_files, f"Add {url}")
            counter += 1

        elif status == 429 or status >= 500:
            print(f"  ⚠ {status}, will retry")
            continue
        else:
            print(f"  ⊘ Error {status}")
            append_line(ERRORS_FILE, url)
            errors.add(url)
            remove_line(FRONTIER_FILE, url)
            seen.add(url)
            git_commit_push([FRONTIER_FILE, ERRORS_FILE], f"Error {status}: {url}")
            counter += 1

    elapsed = time.time() - start_time
    remaining_f = len(load_set(FRONTIER_FILE))

    print(f"\n{'='*40}")
    print(f"✅ Done! {elapsed:.0f}s | {counter} pages | {len(downloaded)} total | {remaining_f} left")
    print(f"{'='*40}")

if __name__ == "__main__":
    main()
