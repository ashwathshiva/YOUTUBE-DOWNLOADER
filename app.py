from flask import Flask, request, render_template_string, send_file, Response, jsonify
import yt_dlp
import os
import tempfile
import threading
import time
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)
progress = {"text": "Ready", "percent": 0}

HTML = '''
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>YouTube Downloader</title>
<style>
    body {font-family: Arial; background:#000;color:#fff;text-align:center;padding:50px;}
    input[type=text]{width:80%;max-width:600px;padding:15px;font-size:18px;border-radius:10px;border:none;}
    button{padding:15px 40px;font-size:18px;margin:15px;border:none;border-radius:10px;cursor:pointer;}
    .mp4{background:#ff0000;}.mp3{background:#00c853;}
    .bar{height:50px;background:#333;border-radius:10px;overflow:hidden;margin:20px auto;width:80%;max-width:600px;}
    .fill{height:100%;width:0%;background:linear-gradient(90deg,#ff0000,#ffff00);text-align:center;line-height:50px;font-weight:bold;transition:0.4s;}
    .error {color: red; margin: 20px;}
</style></head><body>
<h1>YouTube Downloader</h1>
<form method="POST">
    <input type="text" name="url" placeholder="Paste YouTube link" required autofocus><br><br>
    <button class="mp4" name="action" value="mp4">MP4 (Video + Audio)</button>
    <button class="mp3" name="action" value="mp3">MP3 (Audio Only)</button>
</form>
<div class="bar"><div class="fill" id="fill">0%</div></div>
<div id="status">Ready</div>
<div id="error" class="error"></div>

<script>
    const es = new EventSource("/progress");
    es.onmessage = e => {
        if (e.data === "DONE") {
            document.getElementById("status").innerText = "100% Complete! Sending file...";
            document.getElementById("fill").style.width = "100%";
            document.getElementById("fill").innerText = "100%";
            es.close();
        } else if (e.data.startsWith("ERROR:")) {
            document.getElementById("error").innerText = e.data;
            es.close();
        } else {
            const d = JSON.parse(e.data);
            document.getElementById("status").innerText = d.text;
            document.getElementById("fill").style.width = d.percent + "%";
            document.getElementById("fill").innerText = d.percent + "%";
        }
    };
</script>
</body></html>
'''

def progress_hook(d):
    if d['status'] == 'downloading':
        try:
            p = int(float(d['_percent_str'].replace('%','').strip()))
        except:
            p = progress["percent"]
        progress["percent"] = p
        progress["text"] = f"Downloading... {p}% • {d.get('_speed_str','')} • ETA {d.get('_eta_str','')}"
    elif d['status'] == 'finished':
        progress["text"] = "Processing file (this can take a minute)..."
        progress["percent"] = 99

@app.route('/progress')
def stream():
    def gen():
        while progress["percent"] < 99:
            yield f"data: {{\"text\":\"{progress['text']}\",\"percent\":{progress['percent']}}}\n\n"
            time.sleep(0.5)
        yield "data: DONE\n\n"
    return Response(gen(), mimetype='text/event-stream')

@app.route('/', methods=['GET', 'POST'])
def index():
    global progress
    if request.method == 'POST':
        url = request.form['url'].strip()
        if not url.startswith('https://www.youtube.com/'):
            return "ERROR: Please enter a valid YouTube URL.", 400
        action = request.form.get('action', 'mp4')
        progress = {"text": "Starting...", "percent": 0}

        temp_dir = os.path.join(tempfile.gettempdir(), f"yt_{int(time.time()*1000)}")
        os.makedirs(temp_dir, exist_ok=True)

        def download():
            try:
                base_opts = {
                    'format': 'bestaudio/best' if action == 'mp3' else 'bestvideo+bestaudio/best',
                    'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                    'progress_hooks': [progress_hook],
                    'quiet': False,
                    'no_warnings': False,
                    'continuedl': True,
                    'retries': 10,
                }

                if action == 'mp3':
                    base_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]
                    base_opts['keepvideo'] = False
                else:
                    base_opts['merge_output_format'] = 'mp4'

                with yt_dlp.YoutubeDL(base_opts) as ydl:
                    ydl.download([url])
                progress["percent"] = 100
            except Exception as e:
                progress["text"] = f"ERROR: {str(e)}"
                progress["percent"] = 0
                yield f"data: ERROR: {str(e)}\n\n"

        threading.Thread(target=download, daemon=True).start()

        # Wait for file or error
        time.sleep(5)  # Give it time to start
        files = [f for f in os.listdir(temp_dir) if f.endswith(('.mp4', '.mp3')) and os.path.getsize(os.path.join(temp_dir, f)) > 100*1024]
        if files:
            final_file = os.path.join(temp_dir, files[0])
            resp = send_file(final_file, as_attachment=True)
            threading.Thread(target=lambda: [time.sleep(10), shutil.rmtree(temp_dir, ignore_errors=True)]).start()
            return resp
        else:
            return "ERROR: Download failed. Check URL or try again.", 500

    progress = {"text": "Ready", "percent": 0}
    return render_template_string(HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), threaded=True)
