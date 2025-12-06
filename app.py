from flask import Flask, request, render_template_string, send_file, Response
import yt_dlp
import os
import tempfile
import threading
import time
import shutil

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
</style></head><body>
<h1>YouTube Downloader</h1>
<form method="POST">
    <input type="text" name="url" placeholder="Paste YouTube link" required autofocus><br><br>
    <button class="mp4" name="action" value="mp4">MP4 (Video + Audio)</button>
    <button class="mp3" name="action" value="mp3">MP3 (Audio Only)</button>
</form>
<div class="bar"><div class="fill" id="fill">0%</div></div>
<div id="status">Ready</div>

<script>
    const es = new EventSource("/progress");
    es.onmessage = e => {
        if (e.data === "DONE") {
            document.getElementById("status").innerText = "100% Complete! Sending file...";
            document.getElementById("fill").style.width = "100%";
            document.getElementById("fill").innerText = "100%";
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
    global progress
    if d['status'] == 'downloading':
        try:
            percent_str = d.get('_percent_str', '0%').replace('%', '').strip()
            p = int(float(percent_str))
            progress["percent"] = p
            speed = d.get('_speed_str', '??')
            eta = d.get('_eta_str', '??')
            progress["text"] = f"Downloading... {p}% • {speed} • ETA {eta}"
        except:
            pass
    elif d['status'] == 'finished':
        progress["text"] = "Finalizing file..."
        progress["percent"] = 99

@app.route('/progress')
def stream():
    def gen():
        last = -1
        while progress["percent"] < 99:
            if progress["percent"] != last:      # only send when changed
                yield f"data: {{\"text\":\"{progress['text']}\",\"percent\":{progress['percent']}}}\n\n"
                last = progress["percent"]
            time.sleep(0.5)
        yield "data: DONE\n\n"
    return Response(gen(), mimetype='text/event-stream')

@app.route('/', methods=['GET', 'POST'])
def index():
    global progress
    if request.method == 'POST':
        url = request.form['url'].strip()
        action = request.form.get('action', 'mp4')
        progress = {"text": "Preparing...", "percent": 0}

        temp_dir = os.path.join(tempfile.gettempdir(), f"yt_{int(time.time()*1000)}")
        os.makedirs(temp_dir, exist_ok=True)

        def download():
            # THE MAGIC SETTINGS THAT FIX EVERYTHING
            base_opts = {
                'format': 'bestaudio/best' if action == 'mp3' else 'bestvideo+bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title)s.f%(format_id)s.%(ext)s'),
                'merge_output_format': 'mp4' if action == 'mp4' else None,
                'postprocessors': [],
                'progress_hooks': [progress_hook],
                'quiet': False,
                'no_warnings': False,
                'continuedl': True,
                'retries': 999,
                'fragment_retries': 999,
                'ffmpeg_location': os.path.dirname(__file__),
            }

            if action == 'mp3':
                base_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
                base_opts['keepvideo'] = False

            with yt_dlp.YoutubeDL(base_opts) as ydl:
                ydl.download([url])

        threading.Thread(target=download, daemon=True).start()

        # Wait for the FINAL file (mp3 or mp4) — this is the key!
        target_ext = '.mp3' if action == 'mp3' else '.mp4'
        while True:
            done_files = [f for f in os.listdir(temp_dir) if f.endswith(target_ext)]
            if done_files:
                final_file = os.path.join(temp_dir, done_files[0])
                # Extra safety: wait until file stops growing
                size1 = os.path.getsize(final_file)
                time.sleep(3)
                size2 = os.path.getsize(final_file)
                if size1 == size2 and size2 > 500*1024:  # stopped growing + >500KB
                    break
            time.sleep(1)

        resp = send_file(final_file, as_attachment=True)
        threading.Thread(target=lambda: [time.sleep(20), shutil.rmtree(temp_dir, ignore_errors=True)]).start()
        return resp

    progress = {"text": "Ready", "percent": 0}
    return render_template_string(HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)