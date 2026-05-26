import json
import sys
import re
import urllib.request
import urllib.error
from typing import List, Dict, Tuple

def extract_playlist_id(url: str) -> str:
    patterns = [
        r'spotify\.com/playlist/([a-zA-Z0-9]+)',
        r'spotify:playlist:([a-zA-Z0-9]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    raise ValueError(f"Invalid Spotify playlist URL: {url}")


def fetch_playlist_data(playlist_id: str, bearer_token: str, client_token: str) -> Dict:
    url = "https://api-partner.spotify.com/pathfinder/v2/query"
    
    headers = {
        "accept": "application/json",
        "accept-language": "en",
        "app-platform": "WebPlayer",
        "authorization": f"Bearer {bearer_token}",
        "client-token": client_token,
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://open.spotify.com",
        "referer": "https://open.spotify.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    all_items = []
    offset = 0
    batch_size = 50
    
    while True:
        payload = {
            "variables": {
                "uri": f"spotify:playlist:{playlist_id}",
                "offset": offset,
                "limit": batch_size,
                "includeEpisodeContentRatingsV2": False
            },
            "operationName": "fetchPlaylistContents",
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "a65e12194ed5fc443a1cdebed5fabe33ca5b07b987185d63c72483867ad13cb4" #hopefully this is not volatile
                }
            }
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                response_data = json.loads(response.read().decode('utf-8'))
                items = response_data["data"]["playlistV2"]["content"]["items"]
                all_items.extend(items)
                
                if len(items) < batch_size:
                    break
                offset += batch_size
        except urllib.error.HTTPError as e:
            error_msg = e.read().decode('utf-8') if e.fp else str(e)
            if e.code == 401:
                raise Exception("Authentication failed - Invalid or expired tokens. Please get fresh tokens")
            elif e.code == 400:
                raise Exception(f"Bad request (400) - Check playlist ID. Are your tokens valid? Response: {error_msg}")
            else:
                raise Exception(f"API Error ({e.code}): {error_msg}")
    
    return {
        "data": {
            "playlistV2": {
                "content": {
                    "items": all_items
                }
            }
        }
    }


def _get_nested_value(data: Dict, path: List[str]) -> str:
    node = data
    for key in path:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return ""
    return node if isinstance(node, str) else ""


def extract_tracks(json_data: Dict) -> List[Dict]:
    tracks = []
    
    try:
        items = json_data["data"]["playlistV2"]["content"]["items"]
    except KeyError:
        raise Exception("Invalid playlist data - Could not find tracks. Make sure the playlist is accessible.")
    
    for item in items:
        try:
            track_info = item["itemV2"]["data"]
            uid = item["uid"]
            
            artists = track_info["artists"]["items"]
            primary_artist = artists[0]["profile"]["name"] if artists else "Unknown"
            featured = ", ".join([a["profile"]["name"] for a in artists[1:]]) if len(artists) > 1 else ""
            artist_display = f"{primary_artist} (feat. {featured})" if featured else primary_artist

            album_name = _get_nested_value(track_info, ["albumOfTrack", "name"])
            if not album_name:
                album_name = _get_nested_value(track_info, ["album", "name"])
            if not album_name:
                album_name = _get_nested_value(track_info, ["track", "album", "name"])
            if not album_name:
                album_name = _get_nested_value(track_info, ["track", "albumOfTrack", "name"])
            if not album_name:
                album_name = "Unknown Album"
            
            track = {
                "uid": uid,
                "name": track_info["name"],
                "artist": primary_artist,
                "artist_display": artist_display,
                "album": album_name,
                "uri": track_info["uri"]
            }
            tracks.append(track)
        except (KeyError, IndexError):
            continue
    
    if not tracks:
        raise Exception("No tracks found in playlist")
    
    return tracks


def sort_tracks(tracks: List[Dict]) -> List[Dict]:
    return sorted(
        tracks,
        key=lambda x: (x["artist"].lower(), x["album"].lower(), x["name"].lower())
    )


def build_move_steps(sorted_tracks: List[Dict], original_tracks: List[Dict]) -> List[Dict]:
    current_order = [track["uid"] for track in original_tracks]
    steps = []

    for index, track in enumerate(sorted_tracks):
        uid = track["uid"]
        if index < len(current_order) and current_order[index] == uid:
            continue

        if index == 0:
            move_type = "BEFORE_UID" #for the first song
            from_uid = current_order[0] if current_order else None
        else:
            move_type = "AFTER_UID"
            from_uid = sorted_tracks[index - 1]["uid"]

        steps.append({
            "track": track,
            "move_type": move_type,
            "from_uid": from_uid
        })

        if uid in current_order:
            current_order.remove(uid)
        current_order.insert(index, uid)

    return steps


def print_comparison(original: List[Dict], sorted_list: List[Dict]):
    print("\n" + "="*100)
    print("CURRENT PLAYLIST ORDER")
    print("="*140)
    print(f"{'#':>3}  {'Artist':40} | {'Album':35} | {'Track'}")
    print("="*140)
    for i, track in enumerate(original, 1):
        print(f"{i:3d}. {track['artist_display']:40} | {track['album'][:35]:35} | {track['name']}")
    
    print("\n" + "="*140)
    print("SORTED BY ARTIST, ALBUM, TRACK")
    print("="*140)
    print(f"{'#':>3}  {'Artist':40} | {'Album':35} | {'Track'}")
    print("="*140)
    for i, track in enumerate(sorted_list, 1):
        print(f"{i:3d}. {track['artist_display']:40} | {track['album'][:35]:35} | {track['name']}")
    
    print("\n" + "="*100)
    print("CHANGES NEEDED")
    print("="*100)
    
    moved = []
    for i, new_track in enumerate(sorted_list):
        old_pos = next(j for j, t in enumerate(original) if t["uid"] == new_track["uid"])
        if old_pos != i:
            moved.append((old_pos + 1, i + 1, new_track))
    
    if not moved:
        print("No changes needed, playlist is already sorted!")
    else:
        for old_pos, new_pos, track in moved:
            direction = "DOWN" if new_pos > old_pos else "UP"
            print(f"{direction:4} | Position {old_pos} -> {new_pos}: {track['artist_display']} - {track['name']}")


def generate_move_payload(playlist_id: str, uid: str, move_type: str, from_uid: str = None) -> Dict: #easier to do this in a ps script than python
    if move_type == "START":
        new_position = {"moveType": "START"}
    elif move_type == "BEFORE_UID":
        new_position = {"moveType": "BEFORE_UID", "fromUid": from_uid}
    else:
        new_position = {"moveType": "AFTER_UID", "fromUid": from_uid}
    
    return {
        "variables": {
            "playlistUri": f"spotify:playlist:{playlist_id}",
            "uids": [uid],
            "newPosition": new_position
        },
        "operationName": "moveItemsInPlaylist",
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "47b2a1234b17748d332dd0431534f22450e9ecbb3d5ddcdacbd83368636a0990"
            }
        }
    }


def save_shell_script(playlist_id: str, sorted_tracks: List[Dict], bearer_token: str, client_token: str, original_tracks: List[Dict], filename: str = "move_tracks.sh"):
    move_steps = build_move_steps(sorted_tracks, original_tracks)

    with open(filename, "w", encoding="utf-8") as f:
        # headers
        f.write("#!/bin/bash\n\n")
        f.write("# SpotifyPlaylistReorder\n")
        f.write("# https://github.com/ilovecats4606/SpotifyPlaylistReorder\n")
        f.write(f'AUTHORIZATION="{bearer_token}"\n')
        f.write(f'CLIENT_TOKEN="{client_token}"\n')
        f.write('BASE_URI="https://api-partner.spotify.com/pathfinder/v2/query"\n\n')
        
        f.write('sleep 0.5\n\n')

        for index, step in enumerate(move_steps):
            track = step["track"]
            move_type = step["move_type"]
            from_uid = step["from_uid"]
            payload = generate_move_payload(playlist_id, track["uid"], move_type, from_uid)
            artist_display = track["artist_display"]
            album_name = track.get("album", "Unknown Album")
            track_name = track["name"]
            payload_json = json.dumps(payload, ensure_ascii=False)

            f.write(f"\n# Move {index+1}: {artist_display} - {album_name} - {track_name}\n")
            
            status = f"Moving track {index+1}/{len(move_steps)}: {artist_display} | {album_name} | {track_name}"
            status = status.replace('"', '\\"') # prevents punctuation errors in bash
            f.write(f'echo "{status}"\n')
            
            escaped_payload = payload_json.replace('"', '\\"')
            f.write(f'PAYLOAD="{escaped_payload}"\n\n')
            
            f.write('if response=$(curl -s -X POST "$BASE_URI" \\\n')
            f.write('    -H "accept: application/json" \\\n')
            f.write('    -H "authorization: Bearer $AUTHORIZATION" \\\n')
            f.write('    -H "client-token: $CLIENT_TOKEN" \\\n')
            f.write('    -H "content-type: application/json;charset=UTF-8" \\\n')
            f.write('    -H "origin: https://open.spotify.com" \\\n')
            f.write('    -d "$PAYLOAD"); then\n')
            
            # Green ansi text on success (\033[0;32m)
            f.write('    printf "\\033[0;32m[OK] Track moved successfully\\033[0m\\n"\n')
            f.write('else\n')
            # Red ansi text on failure (\033[0;31m)
            f.write('    printf "\\033[0;31m[ERROR] Failed to execute curl\\033[0m\\n"\n')
            f.write('fi\n\n')
            
            # Delay between to prevent rate limiting
            f.write('sleep 0.5\n')

    print(f"Bash script saved to: {filename}")


def save_powershell_script(playlist_id: str, sorted_tracks: List[Dict], bearer_token: str, client_token: str, original_tracks: List[Dict], filename: str = "move_tracks.ps1"):
    move_steps = build_move_steps(sorted_tracks, original_tracks)

    with open(filename, "w", encoding="utf-8") as f:
        f.write("# SpotifyPlaylistReorder\n")
        f.write("# https://github.com/ilovecats4606/SpotifyPlaylistReorder\n")
        f.write(f'$authorization = "{bearer_token}"\n')
        f.write(f'$clientToken = "{client_token}"\n')
        f.write('$baseUri = "https://api-partner.spotify.com/pathfinder/v2/query"\n\n')
        f.write('$headers = @{\n')
        f.write('    "accept" = "application/json"\n')
        f.write('    "authorization" = "Bearer $authorization"\n')
        f.write('    "client-token" = $clientToken\n')
        f.write('    "content-type" = "application/json;charset=UTF-8"\n')
        f.write('    "origin" = "https://open.spotify.com"\n')
        f.write('}\n\n')
        f.write('Start-Sleep -Milliseconds 500\n\n')

        for index, step in enumerate(move_steps):
            track = step["track"]
            move_type = step["move_type"]
            from_uid = step["from_uid"]
            payload = generate_move_payload(playlist_id, track["uid"], move_type, from_uid)
            artist_display = track["artist_display"]
            album_name = track.get("album", "Unknown Album")
            track_name = track["name"]
            payload_json = json.dumps(payload, ensure_ascii=False)

            f.write(f"\n# Move {index+1}: {artist_display} - {album_name} - {track_name}\n")
            status = f"Moving track {index+1}/{len(move_steps)}: {artist_display} | {album_name} | {track_name}"
            status = status.replace('"', '`"') #incase the track name has quotes
            f.write(f'Write-Host "{status}"\n')
            escaped = payload_json.replace('"', '`"')
            f.write(f'$payload = "{escaped}"\n\n')
            f.write('try {\n')
            f.write('    $response = Invoke-RestMethod -Uri $baseUri `\n')
            f.write('        -Method POST `\n')
            f.write('        -Headers $headers `\n')
            f.write('        -Body $payload\n')
            f.write('    Write-Host "[OK] Track moved successfully" -ForegroundColor Green\n')
            f.write('}\n')
            f.write('catch {\n')
            f.write('    Write-Host "[ERROR] Failed: $($_.Exception.Message)" -ForegroundColor Red\n')
            f.write('}\n\n')
            f.write('Start-Sleep -Milliseconds 500\n')

    print(f"PowerShell script saved to: {filename}")


def save_json_requests(playlist_id: str, sorted_tracks: List[Dict], original_tracks: List[Dict], filename: str = "move_payloads.json"):
    move_steps = build_move_steps(sorted_tracks, original_tracks)
    requests = []
    
    for index, step in enumerate(move_steps):
        track = step["track"]
        payload = generate_move_payload(playlist_id, track["uid"], step["move_type"], step["from_uid"])
        
        requests.append({
            "order": index + 1,
            "track": track["artist_display"] + " - " + track["name"],
            "payload": payload
        })
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(requests, f, indent=2, ensure_ascii=False)
    
    print(f"JSON payloads saved to: {filename}")


def prompt_for_tokens() -> Tuple[str, str]:
    print("\n" + "="*100)
    print("Authentication is required to continue")
    print("="*100)
    print("\nTo get your authentication tokens, follow these steps:")
    print("1. Open Spotify Web Player: https://open.spotify.com. Log in if you haven't already, any Chromium based browser will work best.")
    print("2. Open DevTools (F12)")
    print("3. Go to the Network tab")
    print("4. In the filter, type \"query\". If nothing pops up, try playing a song or refresh page to generate some network activity.")
    print("5. Click on it and go to 'Request Headers' section")
    print("6. Copy these header values:")
    print("   - 'authorization' (extract the part AFTER 'Bearer ')")
    print("   - 'client-token' (full value)")
    print("\nNOTE: Tokens expire! You'll need fresh ones each time.")
    print("="*100 + "\n")
    
    bearer_token = input("Enter Bearer Token: ").strip()
    if not bearer_token:
        raise Exception("Bearer token is required")
    
    client_token = input("Enter Client Token: ").strip()
    if not client_token:
        raise Exception("Client token is required")
    
    print(bearer_token, client_token)
    
    return bearer_token, client_token


def main():
    if len(sys.argv) < 2:
        print("\nSpotifyPlaylistReorder")
        print("="*100)
        print("\nThis tool will reorder your Spotify playlist alphabetically by artist, album, track title.")
        print("\nUsage:")
        print("  python SpotifyPlaylistReorder.py 'https://open.spotify.com/playlist/PLAYLIST_ID'")
        print("\nExamples:")
        print("  python SpotifyPlaylistReorder.py 'https://open.spotify.com/playlist/xxxxxx....'")
        print("  python SpotifyPlaylistReorder.py 'spotify:playlist:xxxxxx....'")
        print("="*100 + "\n")
        sys.exit(1)
    
    playlist_url = sys.argv[1]
    
    try:
        playlist_id = extract_playlist_id(playlist_url)
        print(f"\nPlaylist ID: {playlist_id}")
        
        bearer_token, client_token = prompt_for_tokens()
        
        print("\nFetching playlist data...")
        json_data = fetch_playlist_data(playlist_id, bearer_token, client_token)
        
        print("Extracting tracks...")
        original_tracks = extract_tracks(json_data)
        print(f"Found {len(original_tracks)} tracks")
        
        sorted_tracks = sort_tracks(original_tracks)
        
        print_comparison(original_tracks, sorted_tracks)
        
        print("\n" + "="*100)
        # check platform
        if sys.platform == "win32":
            save_powershell_script(playlist_id, sorted_tracks, bearer_token, client_token, original_tracks)
        else:
            save_shell_script(playlist_id, sorted_tracks, bearer_token, client_token, original_tracks)
        save_json_requests(playlist_id, sorted_tracks, original_tracks)
        print("="*100)
        
        response = input("\nDo you want to execute the reordering now? (yes/no): ").strip().lower()
        if response in ["yes", "y"]:
            import subprocess
            print("\nStarting playlist reordering...")
            print("(You may be prompted to allow script execution)\n")
            if sys.platform == "win32":
                result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", "move_tracks.ps1"],
                    cwd="."
                )
            else:
                result = subprocess.run(["bash", "move_tracks.sh"], cwd=".")
            if result.returncode == 0:
                print("\nPlaylist reordering complete!")
            else:
                print("\nPlaylist reordering had some issues. Check the output above.")
        else:
            print("\nTo run the script later, execute:")
            if sys.platform == "win32":
                print("  Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process")
                print("  .\\move_tracks.ps1")
            else:
                print("  bash move_tracks.sh")
    
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
