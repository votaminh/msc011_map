#!/usr/bin/env python3
"""Cut every country, smallest first, with WORKERS cuts at once; one pusher sends each finished country to GitHub, then deletes it.
usage: python3 tools/world.py [--workers 6] [--skip VNM,...]    log: /tmp/maptest/world.log, state: /tmp/maptest/world_state.json
Stops pushing at the first push error (the pieces stay on disk until then) and writes the error to the log."""
import json, os, subprocess, sys, threading, queue, time, shutil
from concurrent.futures import ThreadPoolExecutor
from shapely.geometry import shape
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = '/tmp/maptest'; LOG = f'{TMP}/world.log'; STATE = f'{TMP}/world_state.json'
PLANET = 'https://build.protomaps.com/20261112.pmtiles'
opt = lambda n, d: sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
workers = int(opt('--workers', 6)); skip = set(opt('--skip', 'VNM').split(','))
env = dict(os.environ, PATH=TMP + ':' + os.environ['PATH'])
log_lock = threading.Lock(); push_q = queue.Queue(); stop = threading.Event()
state = json.load(open(STATE)) if os.path.exists(STATE) else {}
def log(m):
    with log_lock:
        open(LOG, 'a').write(time.strftime('%H:%M:%S ') + m + '\n')
def save():
    with log_lock: json.dump(state, open(STATE, 'w'), indent=1)

def cut(iso):
    if stop.is_set(): return
    out = f'{TMP}/w/{iso.lower()}'; shutil.rmtree(out, ignore_errors=True); t = time.time()
    r = subprocess.run(['python3', f'{REPO}/tools/cut_country.py', iso, PLANET, out, '--countries', f'{TMP}/countries.geojson'], capture_output=True, text=True, env=env)
    if r.returncode or not os.path.exists(f'{out}/{iso.lower()}.json'):
        state[iso] = 'cut-failed'; save(); log(f'{iso} CUT FAILED {r.stdout[-200:]} {r.stderr[-200:]}'); shutil.rmtree(out, ignore_errors=True); return
    mb = sum(os.path.getsize(f'{out}/{f}') for f in os.listdir(out) if f.endswith('.pmtiles')) // 10**6
    log(f'{iso} cut {mb} MB in {time.time() - t:.0f}s'); push_q.put((iso, out, mb))

def pusher():
    while True:
        item = push_q.get()
        if item is None: return
        iso, out, mb = item
        if stop.is_set(): continue
        dest = f'{REPO}/tiles/{iso.lower()}'; os.makedirs(dest, exist_ok=True)
        for f in os.listdir(out):
            if f.endswith('.pmtiles') or f.endswith('.json'): shutil.move(f'{out}/{f}', f'{dest}/{f}')
        t = time.time(); sh = lambda *a: subprocess.run(a, cwd=REPO, capture_output=True, text=True)
        sh('git', 'add', f'tiles/{iso.lower()}'); c = sh('git', 'commit', '-q', '-m', f'tiles: {iso}')
        p = sh('git', 'push', '-q')
        if p.returncode:
            state[iso] = 'push-failed'; save(); log(f'{iso} PUSH FAILED, stopping: {p.stderr[-400:]}'); stop.set(); continue
        shutil.rmtree(dest, ignore_errors=True); shutil.rmtree(out, ignore_errors=True)
        state[iso] = f'done {mb} MB'; save(); log(f'{iso} pushed {mb} MB in {time.time() - t:.0f}s')

d = json.load(open(f'{TMP}/countries.geojson'))
order = sorted(((shape(f['geometry']).area, f['properties']['ISO3166-1-Alpha-3']) for f in d['features'] if f['properties']['ISO3166-1-Alpha-3'] not in skip and state.get(f['properties']['ISO3166-1-Alpha-3'], '').startswith('done') is False), key=lambda x: x[0])
todo = [iso for _, iso in order if iso != '-99']
log(f'start: {len(todo)} countries, {workers} workers')
th = threading.Thread(target=pusher); th.start()
with ThreadPoolExecutor(workers) as ex: list(ex.map(cut, todo))
push_q.put(None); th.join()
log('finished' if not stop.is_set() else 'stopped on error')
