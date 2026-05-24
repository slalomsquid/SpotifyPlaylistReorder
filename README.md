# SpotifyPlaylistReorder

A small Python script that sorts a Spotify playlist alphabetically by artist, then by album, then by track title, and generates/apply the required API move requests.

When you make a playlist public on Spotify, you can't sort by Album/Artist etc.. and make it update for people who view your playlist. People see it in Custom order which is by date added, from latest to oldest. You are able to rearrange it manually through dragging, so I reverse engineered the webrequests.

We:
- Take your Spotify playlist URL or URI
- Prompt you for short-lived Spotify API tokens (Bearer + client token)
- Fetch the entire playlist
- Sort tracks by artist -> album -> track name
- Generate a PowerShell script (`move_tracks.ps1`) and a JSON payload file (`move_payloads.json`)
- And ask to execute the PowerShell script to apply reordering

> [!CAUTION]
> Use this at your own risk, I am not responsible for any accounts being banned.

## Requirements
- Python
- Windows to run the generated PowerShell script (the script uses PowerShell to call Spotify's partner API)

## Files
- `SpotifyPlaylistReorder.py` — main CLI tool (interactive)

Upon sucessfully running the Python script, 2 files will be generated:
- `move_tracks.ps1`: PowerShell script that executes reorder requests
- `move_payloads.json`: JSON of GraphQL payloads

## Installation
Clone the repo (or copy files) and run with your local Python:

```bash
python SpotifyPlaylistReorder.py "https://open.spotify.com/playlist/<PLAYLIST_ID>"
```

## Usage
1. Run the CLI with a playlist URL or Spotify URI:

```bash
python SpotifyPlaylistReorder.py "https://open.spotify.com/playlist/xxxxxx...."
```

2. The script will prompt you for two tokens:
   - **Bearer token** — from the `authorization` header (copy the part after `Bearer `)
   - **Client token** — from the `client-token` header

How to get tokens (DevTools):
- Open https://open.spotify.com
- Open DevTools (F12) -> Network -> filter `query`
- Select the latest request. If nothing appears try scrolling in a playlist or refresh the site.
- Copy `authorization` (after `Bearer `) and `client-token`

3. Script fetches all playlist tracks (requests in batches of 50) and prints a before/after comparison
4. It writes `move_tracks.ps1` and `move_payloads.json`.
5. You can choose to execute the PowerShell script immediately.

## Sorting rules
Tracks are ordered by:
1. Primary artist (first artist in the track's `artists.items` array)
2. Album name (alphabetical)
3. Track title (alphabetical)

Tracks with multiple artists are attributed to the first listed artist (e.g. `Bob Smith` for `Bob Smith (feat. Jane Smith)` or `Bob Smith, Jane Smith`).

## PowerShell behavior
- We use `Invoke-RestMethod` to call Spotify's partner API
- The script skips redundant moves and uses `BEFORE_UID` / `AFTER_UID` when appropriate to match Spotify's expected move semantics.

## Safety & Troubleshooting
- Tokens expire quickly, always get fresh tokens before running.
- Do NOT share your tokens. Treat them like passwords. I tried using `getpass` in Python but in some terminals the long nature of the tokens would be trimmed and would not parse properly, so be careful with plaintext tokens.
- If the first move fails with a 400, it is usually due to token mismatch or an outdated playlist snapshot, re-run with fresh tokens. I have attempted to fix this with `BEFORE_UID`.
- If the PowerShell execution policy blocks the script, run in PowerShell:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
.\move_tracks.ps1
```

## Contributing
Fixes, suggestions and pull requests welcome. Please keep token handling secure and avoid committing sensitive values.