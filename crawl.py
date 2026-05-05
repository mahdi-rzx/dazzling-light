#!/usr/bin/env python3
"""
Incremental crawler for chem.libretexts.org.
- Downloads HTML pages only
- Handles special characters in URLs
- download_timeout = total job time in seconds
"""

import os
import time
import subprocess
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote, urlunparse

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
BASE_DOMAIN = "chem.libretexts.org"
SEED_URL = "https://chem.libretexts.org/"

JOB_TIMEOUT = float(os.environ.get("DOWNLOAD_TIMEOUT", 300))
MAX_URLS = int(os.environ.get("MAX_URLS_PER_RUN", 0))
REQUEST_TIMEOUT = 30

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def clean_url(url):
    """Remove fragment and query string to avoid duplicates."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

def local_path(url):
    """Convert URL to local path: archive/chem.libretexts.org/..."""
    parsed = urlparse(url)
    path = unquote(parsed.path).strip("/")
    
    if not path:
        return os.path.join(OUTPUT_DIR, parsed.netloc, "index.html")
    
    if "." in path.split("/")[-1]:
        return os.path.join(OUTPUT_DIR, parsed.netloc, path)
    else:
        return os.path.join(OUTPUT_DIR, parsed.netloc, path, "index.html")

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
        print(f"  Git error (non-fatal): {e}")

def time_remaining(start_time, timeout):
    elapsed = time.time() - start_time
    remaining = timeout - elapsed
    if remaining <= 30:
        return 0, True
    return remaining, False

# ------------------------------------------------------------
# Main crawl logic
# ------------------------------------------------------------
def main():
    start_time = time.time()
    
    downloaded = load_set(DOWNLOADED_FILE)
    errors = load_set(ERRORS_FILE)
    
    print(f"Job timeout: {JOB_TIMEOUT}s ({JOB_TIMEOUT/60:.1f} min)")
    print(f"Max URLs: {'unlimited' if MAX_URLS == 0 else MAX_URLS}")
    print(f"Already downloaded: {len(downloaded)} pages")
    print()

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

            try:
                filepath = local_path(url)
                ensure_dir(filepath)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(resp.text)
            except Exception as e:
                print(f"  ⚠ Failed to save: {e}")
                continue

            append_line(DOWNLOADED_FILE, url)
            downloaded.add(url)
            remove_line(FRONTIER_FILE, url)
            seen.add(url)

            soup = BeautifulSoup(resp.text, "html.parser")
            new_links = 0
            for a in soup.find_all("a", href=True):
                abs_link = urljoin(url, a["href"])
                parsed = urlparse(abs_link)
                if parsed.netloc == BASE_DOMAIN:
                    cleaned = clean_url(abs_link)
                    skip_ext = [".pdf", ".zip", ".png", ".jpg", ".jpeg", 
                               ".gif", ".svg", ".css", ".js", ".ico"]
                    if not any(cleaned.lower().endswith(ext) for ext in skip_ext):
                        if cleaned not in seen:
                            append_line(FRONTIER_FILE, cleaned)
                            seen.add(cleaned)
                            new_links += 1
            
            if new_links:
                print(f"  🔗 {new_links} new links")

            git_commit_push([filepath, FRONTIER_FILE, DOWNLOADED_FILE], f"Add {url}")
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
