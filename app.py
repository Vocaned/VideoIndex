from flask import Flask, render_template, safe_join, send_from_directory, abort, request, make_response
import os
import stat
from datetime import datetime


app = Flask(__name__)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

FILES = 'files'
VIDEOEXTS = ['.webm', '.mp4', '.mkv', '.avi', '.mov', '.flv']
ALLOWED = ['.srt', '.vtt']
HIDE_NONVIDEO = True

class File:
    def __init__(self, path):
        self.name = os.path.split(path)[1]
        self.stat = os.stat(path)
        self.ext = os.path.splitext(path)[1]

        self.size = bytes2human(self.stat.st_size)
        self.isdir = stat.S_ISDIR(self.stat.st_mode)
        self.lastmodified = datetime.fromtimestamp(self.stat.st_atime).strftime("%d-%b-%Y %H:%M")

def bytes2human(n: int) -> str:
    # http://code.activestate.com/recipes/578019
    symbols = ('KiB', 'MiB', 'GiB', 'TiB', 'PiB')
    prefix = {}
    for i, s in enumerate(symbols):
        prefix[s] = 1 << (i + 1) * 10
    for s in reversed(symbols):
        if n >= prefix[s]:
            value = float(n) / prefix[s]
            return '{0:.1f}{1}'.format(value, s)
    return '{0}B'.format(n)

def send_m3u8(path):
    data = ['#EXTM3U', request.host_url + path.rstrip('/')]

    resp = make_response('\n'.join(data))
    resp.mimetype = 'video/x-mpegurl'
    resp.headers.add('Content-Disposition', 'filename=video.m3u8')
    return resp

@app.route("/")
@app.route("/<path:path>")
def index(path=""):
    path = '{0}/'.format(path.strip("/")) if path else ""
    filepath = safe_join(FILES, path)

    if filepath.endswith('/play'):
        filepath = filepath[:-5]
        if not os.path.isfile(filepath):
            abort(404)
        return render_template('player.html', file=filepath)
    if filepath.endswith('/m3u8'):
        filepath = filepath[:-5]
        path = path[:-5]
        if not os.path.isfile(filepath):
            abort(404)
        return send_m3u8(path)

    if not os.path.exists(filepath):
        abort(404)

    if os.path.isfile(filepath):
        if HIDE_NONVIDEO and os.path.splitext(filepath)[1].lower() not in VIDEOEXTS and os.path.splitext(filepath)[1].lower() not in ALLOWED:
            abort(404)
        return send_from_directory(FILES, path, as_attachment=True)

    files = [File(safe_join(FILES, path, p)) for p in os.listdir(filepath)]
    for f in files:
        if HIDE_NONVIDEO and f.ext.lower() not in VIDEOEXTS and f.ext.lower() not in ALLOWED and not f.isdir:
            files.remove(f)
    files.sort(key=lambda f: (not f.isdir, f.name))

    return render_template("index.html", path=path, files=files, VIDEOEXTS=VIDEOEXTS)