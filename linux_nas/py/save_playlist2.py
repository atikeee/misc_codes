#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Playlist Parser
Saves: title, url, duration to a CSV file.
Usage: python3 save_playlist.py "https://youtube.com/playlist?list=PLxxxx"
"""

import urllib.request
import json
import sys
import os
import re

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
API_KEY       = "AIzaSyAWQ0xPbbX_my_GtFC_QqZNdmGw3yTCc2E"
OUTPUT_FILE = "youtube_playlist.csv"
# ─────────────────────────────────────────────

CSV_HEADER = "title,url,duration\n"


def extract_playlist_id(url: str) -> str:
    if "list=" in url:
        for part in url.replace("?", "&").split("&"):
            if part.startswith("list="):
                return part.split("list=")[-1]
    return url.strip()


def clean(value: str) -> str:
    return value.replace(",", " ").replace("\n", " ").replace("\r", "").strip()


def parse_duration(iso: str) -> str:
    if not iso:
        return "N/A"
    hours   = re.search(r"(\d+)H", iso)
    minutes = re.search(r"(\d+)M", iso)
    seconds = re.search(r"(\d+)S", iso)
    h = int(hours.group(1))   if hours   else 0
    m = int(minutes.group(1)) if minutes else 0
    s = int(seconds.group(1)) if seconds else 0
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"


def fetch_api(url: str) -> dict:
    try:
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"❌ API error: {e}")
        sys.exit(1)


def fetch_durations(video_ids: list) -> dict:
    durations = {}
    for i in range(0, len(video_ids), 50):
        batch = ",".join(video_ids[i:i + 50])
        url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=contentDetails&id={batch}&key={API_KEY}"
        )
        for item in fetch_api(url).get("items", []):
            iso = item.get("contentDetails", {}).get("duration", "")
            durations[item.get("id", "")] = parse_duration(iso)
    return durations


def fetch_playlist_items(playlist_id: str) -> list:
    base = (
        f"https://www.googleapis.com/youtube/v3/playlistItems"
        f"?part=snippet&maxResults=50&playlistId={playlist_id}&key={API_KEY}"
    )
    items, next_token, page = [], None, 1
    while True:
        url = base + (f"&pageToken={next_token}" if next_token else "")
        print(f"  Fetching page {page}...", end=" ", flush=True)
        data = fetch_api(url)
        batch = data.get("items", [])
        items.extend(batch)
        print(f"{len(batch)} videos")
        next_token = data.get("nextPageToken")
        if not next_token:
            break
        page += 1
    return items


def main():
    if len(sys.argv) < 2:
        print("❌ No playlist URL provided.")
        print("   Usage: python3 save_playlist.py \"https://youtube.com/playlist?list=PLxxxx\"")
        sys.exit(1)

    playlist_id = extract_playlist_id(sys.argv[1])

    print("═" * 45)
    print("  YouTube Playlist Parser")
    print("═" * 45)
    print(f"\n✅ Playlist ID : {playlist_id}")
    print(f"📄 Output file : {OUTPUT_FILE}\n")

    print("Fetching playlist items...")
    items = fetch_playlist_items(playlist_id)

    if not items:
        print("⚠️  No videos found. Check the URL and API_KEY.")
        sys.exit(1)

    print(f"\nFetching durations for {len(items)} videos...")
    video_ids = [
        item.get("snippet", {}).get("resourceId", {}).get("videoId", "")
        for item in items
    ]
    durations = fetch_durations([v for v in video_ids if v])

    file_exists = os.path.isfile(OUTPUT_FILE)
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        if not file_exists:
            f.write(CSV_HEADER)
        for item in items:
            snippet  = item.get("snippet", {})
            video_id = snippet.get("resourceId", {}).get("videoId", "")
            title    = clean(snippet.get("title", "N/A"))
            url      = f"https://www.youtube.com/watch?v={video_id}"
            duration = durations.get(video_id, "N/A")
            f.write(f"{title},{url},{duration}\n")

    print(f"\n✅ Done! {len(items)} videos saved to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()