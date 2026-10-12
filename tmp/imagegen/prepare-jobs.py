import csv
import json
import re
from pathlib import Path

root = Path.cwd()
text = (root / 'docs/ASSET_REQUESTS.md').read_text(encoding='utf-8')
lines = text.splitlines()
mascot_text = (root / 'docs/MASCOT.md').read_text(encoding='utf-8')
standard = re.search(r'### Standard mascot prompt[^\n]*\n> (.*)', mascot_text).group(1)
meadow = 'assets/approved/world/scene_meadow_land.png'
official = 'brand/mascot/default/png/IMG_9937.png'
idle = 'assets/approved/mascot/mascot_idle.png'
happy = 'brand/feelings-expressions/png/face_happy.png'
sad = 'brand/feelings-expressions/png/face_sad.png'
aliases = {'MAP H': 'assets/approved/map/global_horizental.png', 'MAP V': 'assets/approved/map/global_vertical.png', 'OFFICIAL MASCOT': official, 'FACE: happy': happy, 'FACE: excited': 'brand/feelings-expressions/png/face_excited.png'}
scene_prompt = next(line[2:] for line in lines[1193:] if line.startswith('> Create an image. Opaque'))
object_prompt = next(line[2:] for line in lines[1128:] if line.startswith('> Create an image. Transparent background PNG'))
icon_prompt = next(line[2:] for line in lines[1156:] if line.startswith('> Create an image. Square 1:1, transparent background. I attached an approved game icon'))
face_prompt = next(line[2:] for line in lines[1183:] if line.startswith('> Create an image. Square 1:1'))
rows = list(csv.DictReader((root / 'tmp/imagegen/2-pdf-tracking.csv').open(encoding='utf-8-sig')))
jobs = []
seen = set()
for row in rows:
    name = row['asset_name']
    if name in seen:
        continue
    seen.add(name)
    i = int(row['prompt_file'].rsplit(':', 1)[1]) - 1
    line = lines[i]
    width = height = 1024
    transparent = True
    refs = []
    if line.startswith('### '):
        end = next((j for j in range(i+1, len(lines)) if lines[j].startswith('### ')), len(lines))
        block = lines[i+1:end]
        prompt = '\n'.join(re.sub(r'^\s*> ?', '', item) for item in block if item.lstrip().startswith('>'))
        size_line = next(item for item in block if item.startswith('- Size and ratio:'))
        size = re.search(r'(\d+)[x×](\d+)', size_line)
        if size:
            width, height = map(int, size.groups())
        background = next(item for item in block if item.startswith('- Background:'))
        transparent = 'transparent' in background
        ref_line = next(item for item in block if item.startswith('- Upload with the prompt:'))
        for token in re.findall(r'`([^`]+)`', ref_line):
            if token in aliases:
                refs.append(aliases[token])
            elif token.endswith('.png') and '/' in token:
                if token not in refs:
                    refs.append(token)
            else:
                candidates = list((root / 'assets/approved').rglob(token + '.png'))
                pending = {r['output_path'] for r in rows if r['asset_name'] == token}
                assert len(candidates) == 1 or len(pending) == 1, (name, token, candidates)
                refs.append(candidates[0].relative_to(root).as_posix() if candidates else pending.pop())
        if name.startswith('level_') and not name.endswith('_1'):
            refs.append('assets/approved/level/' + name.rsplit('_',1)[0] + '_1.png')
    else:
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if name.startswith('scene_'):
            width, height = (1536, 1024) if name.endswith('_land') else (1024, 1536)
            prompt = scene_prompt.replace('PLACE.', cells[-1] + '.')
            transparent = False
            refs = [meadow]
            if name.endswith('_port'):
                refs.append('assets/approved/world/' + name.replace('_port', '_land') + '.png')
                prompt += ' Recompose the attached matching landscape scene into portrait; preserve the room, objects, colours and lighting, with the same calm open centre.'
        elif name.startswith('face_'):
            prompt = face_prompt.replace('FEELING.', cells[-1] + '.')
            refs = [happy, sad]
        elif name in ['mascot_directing', 'mascot_holding_album', 'mascot_reading']:
            if name == 'mascot_reading':
                pose = 'holding an open storybook in front of its belly with both arm-flaps'
                face = 'happy, sparkly eyes looking up, small open smile'
                refs = [official, idle]
            else:
                pose, face = cells[-2:]
                refs = [official, idle]
            prompt = standard.replace('[POSE: e.g. waving with the right arm, leaning slightly forward]', '[POSE: ' + pose + ']').replace('[FACE: e.g. happy eyes and open smile on the screen face]', '[FACE: ' + face + ']')
            if name != 'mascot_directing':
                prompt = prompt.replace('no props, ', 'only the specified book or album as a prop, ')
        elif name in ['ui_story_wand', 'ui_sticker_album_open']:
            prompt = object_prompt.replace('THING.', cells[-1] + '.')
            refs = ['assets/approved/ui/dock_stories.png']
            if name == 'ui_sticker_album_open':
                width = 1536
                refs = ['assets/approved/ui/dock_collection.png']
                prompt = prompt.replace('85%', '95%')
        else:
            prompt = icon_prompt.replace('THING.', cells[-1] + '.')
            refs = ['assets/approved/ui/like_animals.png']
    assert prompt and refs, name
    prompt += f' Output exactly {width}x{height} pixels as a PNG at the highest available quality.'
    if transparent:
        prompt += ' Use genuine alpha transparency, never a drawn checkerboard or white background.'
    jobs.append(dict(asset_name=name, prompt=prompt, references=list(dict.fromkeys(refs)), output_path=row['output_path'], width=width, height=height, transparent_background=transparent))
assert len(jobs) == 74
output = root / 'tmp/imagegen/jobs.json'
assert not output.exists()
output.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding='utf-8')
print('Prepared', len(jobs), 'jobs from repository prompts.')
