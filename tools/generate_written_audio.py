#!/usr/bin/env python3
"""Generate the recorded voice for the written-exam questions (requires: pip install edge-tts).

Reads the question data embedded in src/index.html and writes, for each topic:
  src/hangok/wNN.mp3         the concatenated audio, served by the app
  src/hangok/reszek/*.mp3    one cached part per paragraph, named by the SHA-1 of its text
  src/hangok/manifest.json   and timings.js entries for wNN

Unchanged paragraphs are reused, so rerunning after a text edit only synthesizes what changed.
The segment order must match the .rd elements that renderWritten() creates in index.html.
Usage: python3 tools/generate_written_audio.py
"""
import asyncio
import hashlib
import json
import re
from pathlib import Path

import edge_tts

SRC = Path(__file__).resolve().parent.parent / 'src'
AUDIO = SRC / 'hangok'
PARTS = AUDIO / 'reszek'
VOICE = 'hu-HU-NoemiNeural'
BYTES_PER_SECOND = 6000  # the service's constant 48 kbit/s mono MP3
WORKERS = 4
RETRIES = 5

# Same substitutions as the app's speakable() ABBR list, so both voices say the same thing.
ABBR = [
    (r'\bpl\.', 'például'), (r'\bkb\.', 'körülbelül'), (r'\bstb\.', 'és így tovább'), (r'\bvs\.', 'kontra'),
    (r'\bNkt\.', 'köznevelési törvény'), (r'\bGyvt\.', 'gyermekvédelmi törvény'),
    (r'\bBtk\.', 'Büntető Törvénykönyv'), (r'\bbv\.', 'büntetés-végrehajtási'),
    (r'(\d)\s?cm\b', r'\1 centiméter'), (r'(\d)\s?kg\b', r'\1 kilogramm'), (r'→', ', majd '),
    (r'(\d+)–(\d+)', r'\1-\2'), (r'\s–\s', ', '), (r'[„”"]', ''),
]
# Legal citations and symbols that only appear in the written material.
CITATIONS = [
    (r'§ \((\d+)\)', r'paragrafus \1. bekezdés'),
    (r'§ ([a-z])\)', r'paragrafus \1 pont'),
    (r'§ (\d+)\.', r'paragrafus \1. pont'),
    (r'§', 'paragrafus'),
    (r'(\d+)\s?%', r'\1 százalék'),
]


def speakable(text):
    text = text.replace('**', '')
    for pattern, repl in CITATIONS + ABBR:
        text = re.sub(pattern, repl, text)
    return text


def part_id(text):
    return hashlib.sha1(text.encode('utf8')).hexdigest()[:12]


def topic_segments(topic):
    """Spoken text of each reading segment, in the DOM order of renderWritten()."""
    segments = [topic['name'] + '.']
    for question in topic['q']:
        segments.append(question['q'])
        for block in question['blocks']:
            segments.extend([block['text']] if block['t'] == 'p' else block['items'])
    return [speakable(s) for s in segments]


async def synthesize(text, path):
    """Write text to path via a temporary file, so an interrupted run leaves no partial part."""
    tmp = path.with_suffix('.tmp')
    for attempt in range(RETRIES):
        try:
            await edge_tts.Communicate(text, VOICE).save(str(tmp))
            if tmp.stat().st_size == 0:
                raise RuntimeError('empty audio')
            tmp.replace(path)
            return
        except Exception as err:
            if attempt == RETRIES - 1:
                raise RuntimeError(f'{text[:60]!r}: {err}') from err
            await asyncio.sleep(2 ** attempt)


async def synthesize_missing(texts):
    missing = [t for t in dict.fromkeys(texts) if not (PARTS / f'{part_id(t)}.mp3').exists()]
    print(f'{len(set(texts))} parts, {len(missing)} to synthesize', flush=True)
    queue = asyncio.Queue()
    for text in missing:
        queue.put_nowait(text)

    async def worker():
        while not queue.empty():
            text = queue.get_nowait()
            await synthesize(text, PARTS / f'{part_id(text)}.mp3')
            done = len(missing) - queue.qsize()
            if done % 25 == 0:
                print(f'  {done}/{len(missing)}', flush=True)

    await asyncio.gather(*(worker() for _ in range(WORKERS)))


def main():
    html = (SRC / 'index.html').read_text(encoding='utf8')
    data = re.search(r'<script id="written" type="application/json">(.*?)</script>', html, re.S).group(1)
    topics = json.loads(data.replace('<\\/', '</'))
    by_key = {f'w{i + 1:02d}': topic_segments(t) for i, t in enumerate(topics)}

    asyncio.run(synthesize_missing([s for segments in by_key.values() for s in segments]))

    manifest = json.loads((AUDIO / 'manifest.json').read_text(encoding='utf8'))
    timings_path = AUDIO / 'timings.js'
    timings = json.loads(timings_path.read_text(encoding='utf8').split('=', 1)[1].rstrip().rstrip(';'))
    for key, segments in by_key.items():
        audio, spans, position = bytearray(), [], 0
        for text in segments:
            pid = part_id(text)
            chunk = (PARTS / f'{pid}.mp3').read_bytes()
            audio += chunk
            end = position + len(chunk)
            spans.append([round(position / BYTES_PER_SECOND, 3), round(end / BYTES_PER_SECOND, 3)])
            position = end
            manifest['texts'][pid] = text
        (AUDIO / f'{key}.mp3').write_bytes(audio)
        manifest['files'][key] = [part_id(s) for s in segments]
        timings[key] = spans
        print(f'{key}: {len(segments)} segments, {spans[-1][1] / 60:.1f} min, {len(audio) / 1e6:.1f} MB', flush=True)

    (AUDIO / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=0), encoding='utf8')
    timings_path.write_text('window.AUDIO_TIMINGS=' + json.dumps(timings, separators=(',', ':')) + ';', encoding='utf8')


if __name__ == '__main__':
    main()
