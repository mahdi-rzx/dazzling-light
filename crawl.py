#!/usr/bin/env python3
"""
Focused crawler for chem.libretexts.org
- Analytical, Organic, Inorganic, Physical/Theoretical, General Chemistry
- Downloads HTML pages only (no images)
- Resumable with per‑page commits
- Job‑level timeout, skips non‑HTML files
- Saves pages directly into chem.libretexts.org/
- Handles redirects and file/directory conflicts
"""

import os
import time
import subprocess
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote, urlunparse

# ------------------------------------------------------------
# Git identity (must run before any git commands)
# ------------------------------------------------------------
subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
OUTPUT_DIR = "chem.libretexts.org"
FRONTIER_FILE = "frontier.txt"
DOWNLOADED_FILE = "downloaded.txt"
ERRORS_FILE = "errors.txt"

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
    
    parts = path.split("/")
    last_part = parts[-1]
    
    if "." in last_part:
        # Has extension → file
        return os.path.join(OUTPUT_DIR, path)
    else:
        # No extension → directory → save as index.html inside it
        return os.path.join(OUTPUT_DIR, path, "index.html")

def ensure_dir(filepath):
    """Create directory, handling case where parent is a file."""
    parent_dir = os.path.dirname(filepath)
    
    # If parent exists as a file (not directory), convert it
    if os.path.isfile(parent_dir):
        print(f"  🔧 Converting file to directory: {parent_dir}")
        temp_path = parent_dir + ".temp"
        os.rename(parent_dir, temp_path)
        os.makedirs(parent_dir, exist_ok=True)
        os.rename(temp_path, os.path.join(parent_dir, "index.html"))
        # Add the moved file to git
        subprocess.run(["git", "add", os.path.join(parent_dir, "index.html")], check=False)
        return
    
    os.makedirs(parent_dir, exist_ok=True)

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
    """Returns (remaining_seconds, should_stop).
    Only stops when less than REQUEST_TIMEOUT seconds remain."""
    elapsed = time.time() - start_time
    remaining = timeout - elapsed
    # FIXED: Only stop when we can't complete another request
    if remaining <= REQUEST_TIMEOUT:
        return max(0, remaining), True
    return remaining, False

def is_allowed_url(url):
    """Only crawl URLs that are under one of ALLOWED_PREFIXES."""
    for prefix in ALLOWED_PREFIXES:
        if url.startswith(prefix):
            return True
    return False

def add_to_downloaded(url, downloaded_set):
    """Smart add to downloaded set, handling redirect equivalents."""
    downloaded_set.add(url)
    append_line(DOWNLOADED_FILE, url)

# ------------------------------------------------------------
# Main crawl
# ------------------------------------------------------------
def main():
    start_time = time.time()

    downloaded = load_set(DOWNLOADED_FILE)
    errors = load_set(ERRORS_FILE)

    print(f"Job timeout: {JOB_TIMEOUT}s ({JOB_TIMEOUT/60:.1f} min)")
    print(f"Max URLs: {'unlimited' if MAX_URLS == 0 else MAX_URLS}")
    print(f"Already downloaded: {len(downloaded)} pages\n")

    # Load or create frontier
    frontier = []
    if os.path.exists(FRONTIER_FILE):
        with open(FRONTIER_FILE) as f:
            frontier = [line.strip() for line in f if line.strip()]
        # Clean out-of-scope URLs
        new_frontier = [u for u in frontier if is_allowed_url(clean_url(u))]
        if len(new_frontier) < len(frontier):
            print(f"🧹 Removing {len(frontier) - len(new_frontier)} out‑of‑scope URLs from frontier")
            with open(FRONTIER_FILE, "w") as f:
                for u in new_frontier:
                    f.write(u + "\n")
            git_commit_push([FRONTIER_FILE], "Purge out‑of‑scope URLs")
            frontier = new_frontier
        print(f"Frontier: {len(frontier)} URLs waiting")
    else:
        frontier = SEED_URLS.copy()
        with open(FRONTIER_FILE, "w") as f:
            for url in frontier:
                f.write(url + "\n")
        git_commit_push([FRONTIER_FILE], "Initialize frontier with 5 chemistry subjects")
        print("Seeded frontier with 5 subject roots")

    seen = downloaded | errors | set(frontier)
    counter = 0

    # FIXED: Create a list copy to iterate, since we modify frontier during iteration
    frontier_list = frontier[:]
    
    for url in frontier_list:
        # FIXED: Check timeout BEFORE attempting download
        remaining, should_stop = time_remaining(start_time, JOB_TIMEOUT)
        if should_stop:
            print(f"\n⏰ Time nearly up! ({JOB_TIMEOUT}s job timeout, {remaining:.0f}s remaining)")
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
            resp = requests.get(url, timeout=min(REQUEST_TIMEOUT, max(1, remaining)), allow_redirects=True)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"  ⚠ {e}")
            continue
        except Exception as e:
            print(f"  ⚠ {e}")
            continue

        status = resp.status_code
        final_url = clean_url(resp.url)  # URL after redirects

        if status == 200:
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                remove_line(FRONTIER_FILE, url)
                seen.add(url)
                git_commit_push([FRONTIER_FILE], f"Skip non-HTML {url}")
                continue

            # Save using the FINAL URL (after redirects)
            filepath = local_path(final_url)
            
            # If redirected, mark original URL as downloaded too
            if final_url != url:
                add_to_downloaded(url, downloaded)
                remove_line(FRONTIER_FILE, url)
                seen.add(url)
                if final_url in downloaded:
                    print(f"  ↪ Redirects to already-downloaded {final_url}")
                    git_commit_push([FRONTIER_FILE, DOWNLOADED_FILE], f"Redirect {url} -> {final_url}")
                    continue

            try:
                ensure_dir(filepath)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(resp.text)
            except Exception as e:
                print(f"  ❌ Save error: {e}")
                continue

            # Mark final URL as downloaded
            add_to_downloaded(final_url, downloaded)
            remove_line(FRONTIER_FILE, final_url)
            seen.add(final_url)

            # Extract new links from the ORIGINAL response
            soup = BeautifulSoup(resp.text, "html.parser")
            new_links = 0
            for a in soup.find_all("a", href=True):
                abs_link = urljoin(final_url, a["href"])
                parsed = urlparse(abs_link)
                if parsed.netloc != BASE_DOMAIN:
                    continue
                cleaned = clean_url(abs_link)
                if not is_allowed_url(cleaned):
                    continue
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

            # Commit
            commit_files = [filepath, FRONTIER_FILE, DOWNLOADED_FILE]
            git_commit_push(commit_files, f"Add {final_url}")
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
