# Thulla.com

Private online card rooms for friends. Includes Famous Thulla, Bluff, Daketi, and Gandu Pataa.

## Run locally

```powershell
python server.py
```

Then open the URL printed by the server, usually:

```text
http://localhost:8000
```

If port `8000` is busy, the local server automatically tries the next free port.

## Deploy on Render

1. Create a GitHub repository, for example `thulla-game`.
2. Upload all files from this folder:
   - `index.html`
   - `styles.css`
   - `game.js`
   - `server.py`
   - `requirements.txt`
   - `render.yaml`
   - `.gitignore`
   - `README.md`
3. Open Render.
4. Choose `New > Web Service`.
5. Connect your GitHub account.
6. Select your `thulla-game` repository.
7. Use these settings:

```text
Runtime: Python
Build Command: pip install -r requirements.txt
Start Command: python server.py
```

Render will provide a public URL like:

```text
https://thulla-game.onrender.com
```

Use that URL in WebIntoApp if you want to convert it into an Android APK.

## Notes

Rooms are stored in server memory. If the Render service restarts or sleeps, active rooms disappear. That is okay for a first version, but a future production version should use a database or Redis.
