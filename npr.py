#!/usr/bin/env python3

import json
import os
import re
import sqlite3
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
            added_at TEXT NOT NULL
        )
    """)

    conn.commit()
    return conn


def safe_filename(text):
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:180]


def download_episode(url, filename, timeout):
    temp_filename = filename + ".part"

    print("      Downloading...")

    try:
        with requests.get(
            url,
            stream=True,
            timeout=timeout,
            headers={"User-Agent": "NPR-Pi/1.0"}
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
                                    flush=True
                                )
                                last_percent = percent

            if total:
                print()

        os.replace(temp_filename, filename)
        return True

    except Exception as e:
        print(f"\n      ERROR: {e}")

        if os.path.exists(temp_filename):
            os.remove(temp_filename)

        return False


def update_show(conn, show_id, show, settings):
    print()
    print("=" * 60)
    print(show["name"])
    print("=" * 60)
    print("      Checking feed...")

    feed = feedparser.parse(show["feed"])

    if not feed.entries:
        print("      ERROR: No episodes found.")
        return

    limit = settings.get("initial_downloads", 3)

    # Examine the newest few episodes.
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
            "SELECT id, downloaded, filename FROM episodes WHERE guid = ?",
            (guid,)
        ).fetchone()

        if existing:
            ep_id, downloaded, filepath = existing

            # Already played — never redownload.
            played = conn.execute(
                "SELECT played FROM episodes WHERE id = ?",
                (ep_id,)
            ).fetchone()[0]

            if played:
                continue

            # Already downloaded — nothing to do.
            if downloaded and os.path.exists(filepath):
                continue

            # Episode is in the database but wasn't successfully downloaded.
            print()
            print(f"      RETRY: {episode.title}")
            audio_url = episode.enclosures[0].href if episode.enclosures else None

            if not audio_url:
                print("      No audio URL available.")
                continue

            success = download_episode(
                audio_url,
                filepath,
                settings.get("download_timeout", 300)
            )

            if success:
                conn.execute(
                    "UPDATE episodes SET downloaded = 1 WHERE id = ?",
                    (ep_id,)
                )
                conn.commit()

                downloaded_count += 1
                retry_count += 1

                print(f"      SAVED: {filepath}")

            continue

        if not episode.enclosures:
            print(f"      No audio: {episode.title}")
            continue

        audio_url = episode.enclosures[0].href
        title = episode.get("title", "Untitled episode")
        published = episode.get("published", "")

        filename = safe_filename(title) + ".mp3"
        filepath = os.path.join(show_directory, filename)

        print()
        print(f"      NEW: {title}")

        success = download_episode(
            audio_url,
            filepath,
            settings.get("download_timeout", 300)
        )

        now = datetime.now().isoformat(timespec="seconds")

        conn.execute("""
            INSERT INTO episodes (
                show_id,
                show_name,
                guid,
                title,
                published,
                audio_url,
                filename,
                downloaded,
                added_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            show_id,
            show["name"],
            guid,
            title,
            published,
            audio_url,
            filepath,
            1 if success else 0,
            now
        ))

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

    for show_id, show in config["shows"].items():

        if not show.get("enabled", False):
            continue

        update_show(
            conn,
            show_id,
            show,
            config["settings"]
        )

    print()
    print("========================================")
    print("             UPDATE COMPLETE")
    print("========================================")
    print()

    conn.close()


if __name__ == "__main__":
    main()
