#!/usr/bin/env python3

import hashlib
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime

import feedparser
import requests

BASE_DIR = os.path.expanduser("~/npr")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DB_FILE = os.path.join(BASE_DIR, "npr.db")


def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def init_database():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id TEXT NOT NULL,
            show_name TEXT NOT NULL,
            guid TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            published TEXT,
            audio_url TEXT NOT NULL,
            filename TEXT,
            downloaded INTEGER DEFAULT 0,
            played INTEGER DEFAULT 0,
            position REAL DEFAULT 0,
            duration REAL,
            added_at TEXT NOT NULL
        )
    """)

    # Upgrade databases created by older versions without losing existing data.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(episodes)")}
    if "duration" not in columns:
        conn.execute("ALTER TABLE episodes ADD COLUMN duration REAL")
        conn.commit()

    return conn


def safe_filename(text):
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:180]


def make_filename(title, guid):
    """Make a readable filename with a stable suffix to avoid title collisions."""
    base = safe_filename(title) or "Untitled episode"
    suffix = hashlib.sha1(str(guid).encode("utf-8")).hexdigest()[:8]
    return f"{base[:170].rstrip()} [{suffix}].mp3"


def get_audio_duration(filename):
    """Return duration in seconds, or None if ffprobe cannot read it."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filename,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return float(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def download_episode(url, filename, timeout):
    temp_filename = filename + ".part"
    print("      Downloading...")

    try:
        with requests.get(
            url,
            stream=True,
            timeout=timeout,
            headers={"User-Agent": "NPR-Pi/1.0"},
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            last_percent = -1

            with open(temp_filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=262144):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total:
                            percent = int(downloaded * 100 / total)
                            if percent != last_percent:
                                print(
                                    f"\r      Progress: {percent}% "
                                    f"({downloaded // 1048576} / "
                                    f"{total // 1048576} MB)",
                                    end="",
                                    flush=True,
                                )
                                last_percent = percent

            if total:
                print()

        os.replace(temp_filename, filename)
        return True

    except Exception as e:
        print(f"\n      ERROR: {e}")
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except OSError:
                pass
        return False


def fetch_feed(feed_url, timeout):
    """Fetch an RSS feed with an explicit timeout, then parse it."""
    response = requests.get(
        feed_url,
        timeout=timeout,
        headers={"User-Agent": "NPR-Pi/1.0"},
    )
    response.raise_for_status()
    return feedparser.parse(response.content)


def update_show(conn, show_id, show, settings):
    print()
    print("=" * 60)
    print(show["name"])
    print("=" * 60)
    print("      Checking feed...")

    try:
        feed = fetch_feed(
            show["feed"],
            settings.get("download_timeout", 300),
        )
    except requests.RequestException as e:
        print(f"      ERROR: Could not fetch feed: {e}")
        return

    if not feed.entries:
        print("      ERROR: No episodes found.")
        return

    limit = settings.get("initial_downloads", 3)
    episodes = feed.entries[:limit]
    audio_directory = settings["audio_directory"]
    show_directory = os.path.join(audio_directory, show_id)
    os.makedirs(show_directory, exist_ok=True)

    new_count = 0
    downloaded_count = 0
    retry_count = 0

    for episode in episodes:
        guid = episode.get("id") or episode.get("guid")
        if not guid:
            print("      Skipping episode with no GUID.")
            continue

        existing = conn.execute(
            """
            SELECT id, downloaded, filename, played, duration
            FROM episodes
            WHERE guid = ?
            """,
            (guid,),
        ).fetchone()

        if existing:
            ep_id, downloaded, filepath, played, duration = existing

            # A played episode stays in the database but is never redownloaded.
            if played:
                continue

            # Already downloaded and still present.
            if downloaded and filepath and os.path.exists(filepath):
                continue

            print()
            print(f"      RETRY: {episode.get('title', 'Untitled episode')}")
            audio_url = episode.enclosures[0].href if episode.enclosures else None
            if not audio_url:
                print("      No audio URL available.")
                continue

            success = download_episode(
                audio_url,
                filepath,
                settings.get("download_timeout", 300),
            )

            if success:
                duration = get_audio_duration(filepath)
                conn.execute(
                    """
                    UPDATE episodes
                    SET downloaded = 1, duration = ?
                    WHERE id = ?
                    """,
                    (duration, ep_id),
                )
                conn.commit()
                downloaded_count += 1
                retry_count += 1
                print(f"      SAVED: {filepath}")
            continue

        if not episode.enclosures:
            print(f"      No audio: {episode.get('title', 'Untitled episode')}")
            continue

        audio_url = episode.enclosures[0].href
        title = episode.get("title", "Untitled episode")
        published = episode.get("published", "")
        filename = make_filename(title, guid)
        filepath = os.path.join(show_directory, filename)

        print()
        print(f"      NEW: {title}")

        success = download_episode(
            audio_url,
            filepath,
            settings.get("download_timeout", 300),
        )
        duration = get_audio_duration(filepath) if success else None
        now = datetime.now().isoformat(timespec="seconds")

        conn.execute(
            """
            INSERT INTO episodes (
                show_id,
                show_name,
                guid,
                title,
                published,
                audio_url,
                filename,
                downloaded,
                duration,
                added_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                show["name"],
                guid,
                title,
                published,
                audio_url,
                filepath,
                1 if success else 0,
                duration,
                now,
            ),
        )
        conn.commit()
        new_count += 1

        if success:
            downloaded_count += 1
            print(f"      SAVED: {filepath}")

    print()
    print(
        f"      {new_count} new episode(s), "
        f"{retry_count} retried, "
        f"{downloaded_count} downloaded."
    )


def main():
    config = load_config()
    conn = init_database()

    print()
    print("========================================")
    print("        NPR PI LIBRARY UPDATER")
    print("========================================")

    try:
        for show_id, show in config["shows"].items():
            if not show.get("enabled", False):
                continue
            if not show.get("feed"):
                print(f"Skipping {show.get('name', show_id)}: no feed configured.")
                continue

            update_show(conn, show_id, show, config["settings"])

        print()
        print("========================================")
        print("             UPDATE COMPLETE")
        print("========================================")
        print()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
