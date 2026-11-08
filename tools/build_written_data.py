#!/usr/bin/env python3
"""Embed the written-exam questions into src/index.html.

Sources (both must list the same topics and questions in the same order):
  src/Irasbeli_kidolgozva.md   full answers ("Kidolgozás" tab), alternate wordings, correction notes
  src/Irasbeli_roviden.md      concise answers ("Röviden" tab)

Format: "## " topic, "### " question, "*Így is kérdezhetik:* ..." alternate wording,
"> " correction note, "- " / "1. " list items, any other line a paragraph; **bold** is kept.
After changing the text, run this, then tools/generate_written_audio.py to update the voice.
"""
import json
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / 'src'
TAG = '<script id="written" type="application/json">'


def parse(path):
    topics, question = [], None
    for line in path.read_text(encoding='utf8').splitlines():
        s = line.strip()
        if not s or s.startswith('# '):
            continue
        if s.startswith('## '):
            topics.append({'name': s[3:], 'q': []})
            question = None
        elif s.startswith('### '):
            question = {'q': s[4:], 'alt': [], 'note': '', 'blocks': []}
            topics[-1]['q'].append(question)
        elif question is None:
            continue
        elif s.startswith('*Így is kérdezhetik:* '):
            question['alt'].append(s.split(':* ', 1)[1])
        elif s.startswith('> '):
            question['note'] = s[2:]
        elif m := re.match(r'(- |\d+\. )(.*)', s):
            kind = 'ul' if m[1] == '- ' else 'ol'
            blocks = question['blocks']
            if not (blocks and blocks[-1]['t'] == kind):
                blocks.append({'t': kind, 'items': []})
            blocks[-1]['items'].append(m[2])
        else:
            question['blocks'].append({'t': 'p', 'text': s})
    return topics


def main():
    full = parse(SRC / 'Irasbeli_kidolgozva.md')
    short = parse(SRC / 'Irasbeli_roviden.md')
    assert [t['name'] for t in full] == [t['name'] for t in short], 'the two files list different topics'
    for ft, st in zip(full, short):
        assert [q['q'] for q in ft['q']] == [q['q'] for q in st['q']], f'questions differ in topic {ft["name"]!r}'
        for fq, sq in zip(ft['q'], st['q']):
            fq['short'] = sq['blocks']
    data = json.dumps(full, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')

    path = SRC / 'index.html'
    html = path.read_text(encoding='utf8')
    assert TAG in html, 'written data block not found in index.html'
    html = re.sub(re.escape(TAG) + r'.*?</script>', lambda _: TAG + data + '</script>', html, flags=re.S)
    with open(path, 'w', encoding='utf8', newline='') as f:
        f.write(html)
    print(f'{len(full)} topics, {sum(len(t["q"]) for t in full)} questions embedded')


if __name__ == '__main__':
    main()
