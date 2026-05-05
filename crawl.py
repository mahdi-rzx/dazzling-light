#!/usr/bin/env python3
"""
Incremental crawler for chem.libretexts.org.
- Resumable: tracks frontier, downloaded, and permanent errors in text files.
- Each successful download is saved under archive/ and immediately committed & pushed.
- Timeouts and connection errors leave the URL in the frontier for next run.
- Permanent HTTP errors (4xx except 429) are recorded and skipped forever.
- New links are added to the frontier, growing the crawl.
"""

import os
import subprocess
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse

# ------------------------------------------------------------
# Configure git identity FIRST (before any git commands)
# ------------------------------------------------------------
subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
OUTPUT_DIR = "archive"
FRONTIER_FILE = "frontier.txt"
DOWNLOADED_FILE = "downloaded.txt"   # successfully saved URLs
ERRORS_FILE = "errors.txt"          # permanently failed URLs
BASE_DOMAIN = "chem.libretexts.org"
SEED_URL = "https://chem.libretexts.org/"

TIMEOUT = float(os.environ.get("DOWNLOAD_TIMEOUT", 30))
MAX_URLS = int(os.environ.get("MAX_URLS_PER_RUN", 0))   # 0 = unlimited

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def clean_url(url):
    """Remove fragment and query string to avoid duplicates."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

def local_path(url):
    """Convert URL to a local file path under OUTPUT_DIR.
    - Strips off the domain.
    - If the path ends with '/' or has no dot in the last segment, treats it as a directory and saves as index.html.
    """
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
    """Remove exactly one line from a text file."""
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

# ------------------------------------------------------------
# Main crawl logic
# ------------------------------------------------------------
def main():
    # Load persistent state
    downloaded = load_set(DOWNLOADED_FILE)
    errors = load_set(ERRORS_FILE)

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

    # Combine everything we have already seen (success + errors + current frontier)
    seen = downloaded | errors | set(frontier)

    counter = 0
    # Process a snapshot of the current frontier (new links added during the run
    # will be processed on the next run).
    for url in frontier[:]:   # iterate over a copy
        url = clean_url(url.strip())
        if not url:
            continue

        # ---------- already handled in a previous run ----------
        if url in downloaded or url in errors:
            print(f"Already processed {url}, removing from frontier.")
            remove_line(FRONTIER_FILE, url)
            git_commit_push([FRONTIER_FILE], f"Remove stale {url} from frontier")
            continue

        if MAX_URLS > 0 and counter >= MAX_URLS:
            print(f"Reached max_urls_per_run = {MAX_URLS}, stopping.")
            break

        print(f"Processing {url}")

        # ---------- download with timeout ----------
        try:
            resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"Timeout/connection error for {url}: {e}. Will retry later.")
            continue   # stays in frontier
        except Exception as e:
            print(f"Unexpected error for {url}: {e}. Keeping in frontier.")
            continue

        status = resp.status_code

        # ---------- success ----------
        if status == 200:
            content = resp.text
            filepath = local_path(url)
            ensure_dir(filepath)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            # Mark as downloaded
            append_line(DOWNLOADED_FILE, url)
            downloaded.add(url)
            remove_line(FRONTIER_FILE, url)
            seen.add(url)

            # Extract links to expand the crawl
            soup = BeautifulSoup(content, "html.parser")
            for a in soup.find_all("a", href=True):
                abs_link = urljoin(url, a["href"])
                parsed = urlparse(abs_link)
                if parsed.netloc == BASE_DOMAIN:
                    cleaned = clean_url(abs_link)
                    if cleaned not in seen:
                        append_line(FRONTIER_FILE, cleaned)
                        seen.add(cleaned)

            # Commit new page + updated state files
            git_commit_push(
                [filepath, FRONTIER_FILE, DOWNLOADED_FILE],
                f"Add {url}"
            )
            counter += 1

        # ---------- temporary failures ----------
        elif status == 429 or status >= 500:
            print(f"Temporary error {status} for {url}. Keeping in frontier.")
            continue   # no removal, will retry later

        # ---------- permanent failures (4xx except 429) ----------
        else:
            print(f"Permanent error {status} for {url}. Recording and skipping.")
            append_line(ERRORS_FILE, url)
            errors.add(url)
            remove_line(FRONTIER_FILE, url)
            seen.add(url)
            git_commit_push(
                [FRONTIER_FILE, ERRORS_FILE],
                f"Mark {url} as error {status}"
            )
            counter += 1

    print("Run completed.")

if __name__ == "__main__":
    main()
