#!/usr/bin/env python3

import json
import os
import socket
import sqlite3
import subprocess
import threading
import time

DB = "/home/pi/npr/npr.db"

SOCKET = "/tmp/npr-mpv.sock"

current_episode_id = None

position_thread_running = False

def send_mpv(command):

    if not os.path.exists(SOCKET):

        return None

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    try:

        sock.connect(SOCKET)

        message = {

            "command": command

        }

        sock.sendall(

            (json.dumps(message) + "\n").encode()

        )

        sock.settimeout(1)

        try:

            response = sock.recv(4096)

            if response:

                return json.loads(response.decode())

        except socket.timeout:

            return None

    except Exception:

        return None

    finally:

        sock.close()

def start_mpv():

    # First, see if an existing mpv is already usable.

    if os.path.exists(SOCKET):

        try:

            sock = socket.socket(

                socket.AF_UNIX,

                socket.SOCK_STREAM

            )

            sock.connect(SOCKET)

            sock.close()

            print("Connected to existing mpv.")

            return True

        except OSError:

            try:

                os.remove(SOCKET)

            except OSError:

                pass

    # Remove any stale socket before starting mpv.

    try:

        os.remove(SOCKET)

    except OSError:

        pass

    print("Starting mpv...")

    process = subprocess.Popen(

        [

            "mpv",

            "--idle=yes",

            "--no-video",

            "--really-quiet",

            "--audio-device=alsa/plughw:MAX98357A",

            "--volume=100",

            "--af=lavfi=[acompressor=threshold=0.12:ratio=3:attack=20:release=250:makeup=2,alimiter=limit=0.99]",

            f"--input-ipc-server={SOCKET}",

        ],

        stdin=subprocess.DEVNULL,

        stdout=subprocess.DEVNULL,

        stderr=subprocess.PIPE,

        text=True,

    )

    # Wait for mpv to create a working IPC socket.

    for _ in range(100):

        if process.poll() is not None:

            error = process.stderr.read().strip()

            print()

            print("ERROR: mpv exited before the IPC socket started.")

            if error:

                print("mpv:", error)

            return False

        try:

            sock = socket.socket(

                socket.AF_UNIX,

                socket.SOCK_STREAM

            )

            sock.settimeout(0.5)

            sock.connect(SOCKET)

            sock.close()

            print("Connected to mpv.")

            return True

        except OSError:

            time.sleep(0.1)

    print("ERROR: mpv IPC socket did not start.")

    # If mpv is still running, terminate it cleanly.

    if process.poll() is None:

        process.terminate()

    return False

def get_episode(ep_id):

    conn = sqlite3.connect(DB)

    row = conn.execute(

        """

        SELECT id, show_name, title, played, position, filename

        FROM episodes

        WHERE id = ?

        """,

        (ep_id,),

    ).fetchone()

    conn.close()

    return row

def save_position(ep_id, position, played=False):

    conn = sqlite3.connect(DB)

    if played:

        conn.execute(

            """

            UPDATE episodes

            SET played = 1,

                position = 0

            WHERE id = ?

            """,

            (ep_id,),

        )

    else:

        conn.execute(

            """

            UPDATE episodes

            SET position = ?

            WHERE id = ?

            """,

            (position, ep_id),

        )

    conn.commit()

    conn.close()

def get_position():

    result = send_mpv(

        [

            "get_property",

            "time-pos",

        ]

    )

    if not result:

        return None

    if result.get("error") != "success":

        return None

    return result.get("data")

def get_duration():

    result = send_mpv(

        [

            "get_property",

            "duration",

        ]

    )

    if not result:

        return None

    if result.get("error") != "success":

        return None

    return result.get("data")

def position_monitor():
    global position_thread_running
    global current_episode_id

    while position_thread_running:
        ep_id = current_episode_id
        if ep_id is not None:
            position = get_position()
            duration = get_duration()

            # Playback may change while MPV is being queried. Never save
            # one episode's position against a different episode.
            if ep_id != current_episode_id:
                time.sleep(0.1)
                continue

            if position is not None:
                if duration and position >= duration - 5:
                    save_position(ep_id, 0, played=True)
                else:
                    save_position(ep_id, position)

        time.sleep(5)

def start_position_monitor():

    global position_thread_running

    position_thread_running = True

    thread = threading.Thread(

        target=position_monitor,

        daemon=True,

    )

    thread.start()

def stop_position_monitor():

    global position_thread_running

    position_thread_running = False

def list_episodes():

    conn = sqlite3.connect(DB)

    rows = conn.execute(

        """

        SELECT id, show_name, title, played, position, duration

        FROM episodes

        WHERE downloaded = 1

        ORDER BY id DESC

        """

    ).fetchall()

    conn.close()

    print()

    print("NPR LIBRARY")

    print("=" * 70)

    for ep_id, show, title, played, position, duration in rows:

        if duration:

            minutes = int(duration // 60)

            seconds = int(duration % 60)

            length = f"{minutes}:{seconds:02d}"

        else:

            length = "--:--"

        if played:

            status = "PLAYED"

        elif position and position > 0:

            pos_minutes = int(position // 60)

            pos_seconds = int(position % 60)

            status = f"{pos_minutes}:{pos_seconds:02d}"

        else:

            status = "NEW"

        print(

            f"[{ep_id}] {status:8} "

            f"[{length:>5}] "

            f"{show}: {title}"

        )

    print()

def play(ep_id):

    global current_episode_id

    episode = get_episode(ep_id)

    if not episode:

        print("Episode not found.")

        return

    (

        _,

        show,

        title,

        played,

        position,

        filename,

    ) = episode

    if not os.path.exists(filename):

        print("Audio file not found:")

        print(filename)

        return

    current_episode_id = ep_id

    print()

    print("Playing:")

    print(show)

    print(title)

    if position and not played:

        minutes = int(position // 60)

        seconds = int(position % 60)

        print(

            f"Resuming at {minutes}:{seconds:02d}"

        )

    print()

    result = send_mpv(

        [

            "loadfile",

            filename,

            "replace",

        ]

    )

    print("mpv:", result)

    if (

        position

        and not played

        and result

        and result.get("error") == "success"

    ):

        time.sleep(0.5)

        send_mpv(

            [

                "set_property",

                "time-pos",

                position,

            ]

        )

def cleanup_played():

    conn = sqlite3.connect(DB)

    rows = conn.execute("""

        SELECT id, show_name, title, filename

        FROM episodes

        WHERE played = 1

          AND downloaded = 1

    """).fetchall()

    if not rows:

        print()

        print("No played tracks to delete.")

        print()

        conn.close()

        return

    deleted = 0

    print()

    for ep_id, show_name, title, filename in rows:
        if ep_id == current_episode_id:
            print(f"  Skipping currently playing: {show_name}: {title}")
            continue

        try:

            if os.path.exists(filename):

                os.remove(filename)

            conn.execute("""

                UPDATE episodes

                SET downloaded = 0

                WHERE id = ?

            """, (ep_id,))

            print(f"  Deleted: {show_name}: {title}")

            deleted += 1

        except Exception as e:

            print(f"  ERROR: {title}: {e}")

    conn.commit()

    conn.close()

    print()

    print(f"Deleted {deleted} played track(s).")

    print("Played status remains saved in the database.")

    print()

def status():

    position = get_position()

    duration = get_duration()

    paused = send_mpv(

        [

            "get_property",

            "pause",

        ]

    )

    print()

    print("Position:", position)

    print("Duration:", duration)

    if position is not None and duration:

        remaining = duration - position

        print(

            "Remaining:",

            int(remaining // 60),

            ":",

            f"{int(remaining % 60):02d}",

            sep="",

        )

    print("Paused:", paused)

    print()

def stop():

    global current_episode_id

    if current_episode_id is not None:

        position = get_position()

        if position is not None:

            save_position(

                current_episode_id,

                position,

            )

    send_mpv(["stop"])

    current_episode_id = None

def delete_episode(ep_id):

    conn = sqlite3.connect(DB)

    row = conn.execute(

        """

        SELECT id, title, played, filename

        FROM episodes

        WHERE id = ?

        """,

        (ep_id,)

    ).fetchone()

    if not row:

        print(f"No episode found with ID {ep_id}.")

        conn.close()

        return

    episode_id, title, played, filename = row

    if episode_id == current_episode_id:
        print("Cannot delete the episode that is currently playing. Stop it first.")
        conn.close()
        return

    if played:

        print("Cannot delete this episode because it is marked PLAYED.")

        conn.close()

        return

    print()

    print(f"Deleting: {title}")

    if filename and os.path.exists(filename):

        try:

            os.remove(filename)

            print(f"Deleted file: {filename}")

        except Exception as e:

            print(f"ERROR deleting file: {e}")

            conn.close()

            return

    else:

        print("Audio file not found.")

    conn.execute(

        "DELETE FROM episodes WHERE id = ?",

        (episode_id,)

    )

    conn.commit()

    conn.close()

    print("Episode removed from database.")

def main():

    global current_episode_id

    if not start_mpv():

        return

    start_position_monitor()

    print()

    print("========================================")

    print("           NPR PLAYER")

    print("========================================")

    print()

    print("Commands:")

    print("  list")

    print("  play <id>")

    print("  delete <id>")

    print("  pause")

    print("  resume")

    print("  toggle")

    print("  stop")

    print("  status")

    print("  cleanup")

    print("  forward")

    print("  back")

    print("  louder")

    print("  quieter")

    print("  quit")

    print()

    try:

        while True:

            try:

                command = input("npr> ").strip()

            except (KeyboardInterrupt, EOFError):

                print()

                if current_episode_id is not None:

                    position = get_position()

                    if position is not None:

                        save_position(

                            current_episode_id,

                            position,

                        )

                send_mpv(["quit"])

                break

            if command == "list":

                list_episodes()

            elif command.startswith("play "):

                try:

                    ep_id = int(

                        command.split()[1]

                    )

                    play(ep_id)

                except (

                    ValueError,

                    IndexError,

                ):

                    print("Usage: play <id>")

            elif command == "pause":

                send_mpv(

                    [

                        "set_property",

                        "pause",

                        True,

                    ]

                )

            elif command == "resume":

                send_mpv(

                    [

                        "set_property",

                        "pause",

                        False,

                    ]

                )

            elif command == "toggle":

                send_mpv(

                    [

                        "cycle",

                        "pause",

                    ]

                )

            elif command == "stop":

                stop()

            elif command == "status":

                status()

            elif command.startswith("delete "):

                try:

                    ep_id = int(command.split()[1])

                    delete_episode(ep_id)

                except (ValueError, IndexError):

                    print("Usage: delete <id>")

            elif command == "cleanup":

                cleanup_played()

            elif command == "forward":

                send_mpv(

                    [

                        "seek",

                        30,

                        "relative",

                    ]

                )

            elif command == "back":

                send_mpv(

                    [

                        "seek",

                        -15,

                        "relative",

                    ]

                )

            elif command == "louder":

                send_mpv(

                    [

                        "add",

                        "volume",

                        5,

                    ]

                )

            elif command == "quieter":

                send_mpv(

                    [

                        "add",

                        "volume",

                        -5,

                    ]

                )

            elif command in (

                "quit",

                "exit",

            ):

                if current_episode_id is not None:

                    position = get_position()

                    if position is not None:

                        save_position(

                            current_episode_id,

                            position,

                        )

                send_mpv(["quit"])

                break

            elif command:

                print("Unknown command.")

    finally:

        stop_position_monitor()

if __name__ == "__main__":

    main()
