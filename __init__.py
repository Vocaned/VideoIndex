from flask import Flask, render_template, safe_join, send_from_directory, abort, request, make_response, Markup, url_for
import os
import stat
from datetime import datetime
import markdown
import mimetypes


app = Flask(__name__, static_url_path='/files/static')
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.jinja_env.globals['safe_join'] = safe_join

FILES = os.environ.get('FILEPATH', 'files')
DATA = os.environ.get('DATAPATH', 'data')
VIDEOEXTS = ['.webm', '.mp4', '.mkv', '.avi', '.mov', '.flv']
ALLOWED = ['.srt', '.vtt', '.md', '.nfo', '.txt']
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
    data = ['#EXTM3U', request.host_url.rstrip('/') + url_for(request.endpoint) + "/" + path.rstrip('/')]

    resp = make_response('\n'.join(data))
    resp.mimetype = 'video/x-mpegurl'
    resp.headers.add('Content-Disposition', 'filename=video.m3u8')
    return resp

def nfo_renderer(path):
    with open(path, 'r', encoding='cp437', errors='ignore') as f:
        body = ''
        for line in f.readlines():
            body += line.rstrip() + '\n'

        return render_template("nfo.html", body=body)

def md_renderer(path):
    with open(path, 'r', encoding='utf-8') as f:
        return render_template("content.html", body=Markup(markdown.markdown(f.read(), extensions=["fenced_code"])))

def txt_renderer(path):
    with open(path, 'r', encoding='utf-8') as f:
        return render_template("content.html", body=Markup("<pre>") + f.read() + Markup("</pre>"))

@app.route("/files")
@app.route("/files/<path:path>")
def index(path=""):
    path = '{0}/'.format(path.strip("/")) if path else ""
    filepath = safe_join(FILES, path)

    if filepath.endswith('/play'):
        filepath = filepath[:-5]
        if not os.path.isfile(filepath):
            abort(404)
        return render_template('player.html', mime=mimetypes.guess_type(filepath)[0], file=url_for(request.endpoint, **request.view_args).split('/play')[0])
    if filepath.endswith('/m3u8'):
        filepath = filepath[:-5]
        path = path[:-5]
        if not os.path.isfile(filepath):
            abort(404)
        return send_m3u8(path)

    if not os.path.exists(filepath):
        abort(404)

    if os.path.isfile(filepath):
        # Pass .nfo and .md files to this app, rest should be served by nginx for better playback performance
        ext = os.path.splitext(filepath)[1]
        if ext == '.nfo':
            return nfo_renderer(filepath)
        elif ext == '.md':
            return md_renderer(filepath)
        elif ext == '.txt':
            return txt_renderer(filepath)

        if os.environ.get("FLASK_RUN_FROM_CLI"): # Serve files in dev environment
            return send_from_directory(FILES, path)
        abort(500)

    readme = None
    files = [File(safe_join(FILES, path, p)) for p in os.listdir(filepath)]
    for f in files:
        if f.name.lower() == 'readme.md':
            with open(os.path.join(filepath, f.name), 'r', encoding='utf-8') as tmp:
                readme = Markup(markdown.markdown(tmp.read(), extensions=["fenced_code"]))
            files.remove(f)
        if HIDE_NONVIDEO and f.ext.lower() not in VIDEOEXTS and f.ext.lower() not in ALLOWED and not f.isdir:
            files.remove(f)
    files.sort(key=lambda f: (not f.isdir, f.name))
    files.sort(key=lambda f: (f.ext in ('.nfo', '.md', '.txt')), reverse=True) # Put .nfo, .md and .txt files at the top of the list

    synccode = request.cookies.get('sync')
    seen = []
    if synccode:
        if os.path.isfile(safe_join(DATA, synccode + '.dat')):
            with open(safe_join(DATA, synccode + '.dat'), 'r', encoding='utf-8') as f:
                seen += [s.strip() for s in f.readlines()]

    return render_template("index.html", base_url=url_for(request.endpoint), url=url_for(request.endpoint, **request.view_args), path=path, files=files, syncing=synccode, seen=seen, readme=readme, VIDEOEXTS=VIDEOEXTS)

@app.route('/files/sync', methods=['POST'])
def sync():
    # TODO: rate limit?
    # TODO: Only process instructions like add/delete instead of pushing the whole list every time?
    synccode = request.cookies.get('sync')
    if not synccode:
        abort(401, 'Tried to sync without a valid sync cookie.')

    data = request.data.decode('utf-8')
    if len(data) > 1000000: # 1 megabyte of text is quite a lot, but could be increased in future if this becomes a problem
        abort(413, 'Data received is too large.')

    with open(safe_join(DATA, synccode + '.dat'), 'w', encoding='utf-8') as f:
        for fn in data.split(';'):
            if os.path.isfile(safe_join(FILES, fn.lstrip('/'+FILES+'/'))):
                f.write(fn+'\n')

    return '', 200
