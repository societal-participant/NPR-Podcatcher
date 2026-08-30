#!/usr/bin/env python3

import json
import os
import socket
import sqlite3
import subprocess
import time


BASE_DIR = "/home/pi/npr"
DB_FILE = os.path.join(BASE_DIR, "npr.db")
SOCKET_FILE = os.path.join(BASE_DIR, "player.sock")


class NPRPlayer:

    def __init__(self):
        self.process = None
        self.current_episode = None

    def database(self):
        return sqlite3.connect(DB_FILE)

    def get_episode(self, episode_id):
        db = self.database()

        row = db.execute("""
            SELECT
                id,
                show_name,
                title,
                filename,
                played,
                position
            FROM episodes
            WHERE id = ?
        """, (episode_id,)).fetchone()

        db.close()

        return row

    def get_next_unplayed(self):
        db = self.database()

        row = db.execute("""
            SELECT
                id,
                show_name,
                title,
                filename,
                played,
                position
            FROM episodes
            WHERE downloaded = 1
              AND played = 0
            ORDER BY id ASC
            LIMIT 1
        """).fetchone()

        db.close()

        return row

    def save_position(self, episode_id, position):
        db = self.database()

        db.execute("""
            UPDATE episodes
            SET position = ?
            WHERE id = ?
        """, (position, episode_id))

        db.commit()
        db.close()

    def mark_played(self, episode_id):
        db = self.database()

        db.execute("""
            UPDATE episodes
            SET played = 1,
                position = 0
            WHERE id = ?
        """, (episode_id,))

        db.commit()
        db.close()

    def stop(self):
        if self.process:
            self.process.terminate()

            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()

            self.process = None

    def play(self, episode_id):
        episode = self.get_episode(episode_id)

        if not episode:
            print("Episode not found.")
            return

        episode_id, show, title, filename, played, position = episode

        if not os.path.exists(filename):
            print("Audio file does not exist:")
            print(filename)
            return

        self.stop()

        print()
        print("========================================")
        print(f"SHOW:     {show}")
        print(f"EPISODE:  {title}")
        print(f"RESUME:   {position:.1f} seconds")
        print("========================================")
        print()

        self.current_episode = episode_id

        command = [
            "mpv",
            "--no-video",
            "--really-quiet",
            "--audio-device=alsa/hw:MAX98357A",
            f"--start={position}",
            filename
        ]

        self.process = subprocess.Popen(command)

        while self.process.poll() is None:
            time.sleep(1)

        self.process = None

        self.mark_played(episode_id)

        print()
        print("Episode finished.")
        print()

    def play_next(self):
        episode = self.get_next_unplayed()

        if not episode:
            print("No unplayed episodes.")
            return

        self.play(episode[0])

    def list_episodes(self):
        db = self.database()

        rows = db.execute("""
            SELECT
                id,
                show_name,
                title,
                played,
                position
            FROM episodes
            WHERE downloaded = 1
            ORDER BY id DESC
        """).fetchall()

        db.close()

        if not rows:
            print("No episodes.")
            return

        print()
        print("NPR LIBRARY")
        print("=" * 70)

        for row in rows:
            episode_id, show, title, played, position = row

            if played:
                status = "PLAYED"
            elif position > 0:
                status = f"RESUME {int(position)}s"
            else:
                status = "NEW"

            print(f"[{episode_id}] {status:12} {show}: {title}")

        print()


def main():
    player = NPRPlayer()

    print()
    print("NPR PLAYER")
    print("===========")
    print()
    print("Commands:")
    print("  list")
    print("  play <id>")
    print("  next")
    print("  quit")
    print()

    while True:

        try:
            command = input("npr> ").strip()

        except (KeyboardInterrupt, EOFError):
            print()
            break

        if command == "list":
            player.list_episodes()

        elif command.startswith("play "):
            try:
                episode_id = int(command.split()[1])
                player.play(episode_id)
            except (ValueError, IndexError):
                print("Usage: play <episode id>")

        elif command == "next":
            player.play_next()

        elif command in ("quit", "exit"):
            player.stop()
            break

        elif command:
            print("Unknown command.")


if __name__ == "__main__":
    main()
