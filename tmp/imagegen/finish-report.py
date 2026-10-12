import csv
import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
folder = root / 'tmp/imagegen'
jobs = json.loads((folder / 'jobs.json').read_text(encoding='utf-8'))
log = [json.loads(line) for line in (folder / 'generation-log.jsonl').read_text(encoding='utf-8-sig').splitlines()]
corrections = json.loads((folder / 'generation-corrections.json').read_text(encoding='utf-8'))
verified = json.loads((folder / 'final-verification.json').read_text(encoding='utf-8-sig'))
by_name = {entry['asset_name']: entry for entry in log}
assert len(log) == len(by_name) == len(jobs) == len(verified) == 74
for entry in log:
    assert (root / entry['output_path']).is_file()
    assert hashlib.sha256((root / entry['output_path']).read_bytes()).hexdigest() == entry['sha256']
    for reference in entry['references']:
        assert (root / reference).is_file(), reference
    if entry['asset_name'] in corrections:
        entry.update(corrections[entry['asset_name']])
    if entry['asset_name'] in ['mascot_speaking_closed', 'mascot_speaking_open']:
        entry['accepted_exception'] = 'Small pixel differences outside the mouth relative to mascot_speaking_half; user explicitly chose to keep generated frames and flag differences.'
        entry['pixel_check'] = corrections['mouth_frame_exception'][entry['asset_name'].rsplit('_', 1)[1]]
(folder / 'generation-log.jsonl').write_text('\n'.join(json.dumps(entry, ensure_ascii=False) for entry in log) + '\n', encoding='utf-8')

tracker = folder / '2-pdf-tracking.csv'
with tracker.open(encoding='utf-8-sig', newline='') as stream:
    reader = csv.DictReader(stream)
    fields = reader.fieldnames
    rows = list(reader)
assert len(rows) == 80 and len({row['asset_name'] for row in rows}) == 74
assert all(row['output_exists'] == 'True' and row['status'].startswith('generated') for row in rows)
for row in rows:
    if row['asset_name'] in ['mascot_speaking_closed', 'mascot_speaking_open']:
        row['status'] = 'generated; PNG verified; retained with user-accepted pixel differences'
        row['issue'] = by_name[row['asset_name']]['accepted_exception']
    row['reference_specified'] = '; '.join(next(job['references'] for job in jobs if job['asset_name'] == row['asset_name']))
with tracker.open('w', encoding='utf-8', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

manifest_path = root / 'assets/manifest.json'
original_text = manifest_path.read_text(encoding='utf-8')
manifest = json.loads(original_text)
old_entries = json.loads(json.dumps(manifest['assets']))
existing_files = {entry['file'] for entry in old_entries}
existing_ids = {entry['id'] for entry in old_entries}
assert len(old_entries) == 68
backup = folder / 'manifest-before.json'
assert not backup.exists()
backup.write_text(original_text, encoding='utf-8')
for entry in log:
    name = entry['asset_name']
    file = entry['output_path']
    if file.startswith('brand/'):
        asset_id, kind = 'brand.' + name, 'brand-feeling'
    elif name.startswith('mascot_'):
        asset_id, kind = 'mascot.' + name[len('mascot_'):], 'mascot-pose'
    else:
        category = file.split('/')[2]
        asset_id, kind = category + '.' + name, category
    assert file not in existing_files and asset_id not in existing_ids
    record = dict(id=asset_id, file=file, kind=kind, prompt=entry['prompt'], tool=entry['tool'], date=entry['date'], chat_link=None, approved=True, reviewed_by='codex', references=entry['references'], checks=['visually reviewed against repository prompt and references', 'PNG decoded successfully; exact requested dimensions verified', 'true alpha transparency verified' if entry['transparent_background'] else 'opaque full-scene PNG'], sha256=entry['sha256'])
    if 'source_dimensions' in entry and entry['source_dimensions'] != entry['dimensions']:
        record['size_normalization'] = entry['source_dimensions'] + ' to ' + entry['dimensions'] + '; proportional resampling preserving alpha, no redrawing'
    if 'edit_prompt' in entry:
        record['edit_prompt'] = entry['edit_prompt']
        record['edit_reference'] = entry['edit_reference']
        record['checks'].append('unrequested exterior rays removed through image-generation edit')
    if 'accepted_exception' in entry:
        record['accepted_exception'] = entry['accepted_exception']
        record['pixel_check'] = entry['pixel_check']
    manifest['assets'].append(record)
assert manifest['assets'][:68] == old_entries
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

report = [
    '# Asset generation report: 2.pdf', '',
    'Date: 2026-10-12. Source document: `C:/Users/Menyar/Downloads/2.pdf` (both pages read).', '',
    'All 80 asset-name occurrences were accounted for, representing 74 distinct output files. Six repeated names resolve to the same repository-specified files. The explanatory mention of the existing `mascot_feel_excited` is not a new request.', '',
    '- Successfully generated, saved and file-verified: **74**.',
    '- Requested outputs already present before generation: **0**.',
    '- Pending, skipped or failed outputs: **0**.',
    '- Retained with an explicit user-accepted exception: **2 mouth frames** (included in the 74 saved outputs).',
    '- Verified transparent PNGs: **58**. Verified opaque scene/map PNGs: **16**.',
    '- Destinations: **70 files in `assets/approved/`**, **4 feeling faces in `brand/feelings-expressions/png/`**, as confirmed by the user.', '',
    'Generation used the built-in OpenAI image tool after the user explicitly changed the original API/SDK requirement. Actual local reference files were supplied to each call. Highest available quality was requested; the tool does not expose a selectable API model or quality parameter.', '',
    'Square images returned at a larger square size were proportionally resampled to 1024x1024 with alpha preserved. Scene and map outputs use the specified 1536x1024 or 1024x1536 dimensions. This was image sizing, not code-drawn artwork.', '',
    'Every file was visually reviewed and decoded as PNG. Dimensions, existence, SHA-256 and alpha transparency were checked after saving. Existing output files were never overwritten: every destination was initially absent and the save routine used exclusive creation. Existing manifest entries were preserved and 74 new records were appended. No application code or public delivery build was changed.', '',
    '## Accepted exceptions', '',
    'The closed and open speaking frames were made through mouth-only image edits using the actual saved half-open base. They look aligned, but pixel sampling found differences outside the mouth. The user chose: **"Keep the generated frames and flag the pixel differences"**. Exact unchanged body pixels are therefore not claimed.', '',
    '| Frame | Samples outside mouth | Samples with summed RGBA difference >24 | Mean absolute channel error (0–255) |',
    '|---|---:|---:|---:|',
    '| mascot_speaking_closed | 8,052 | 515 | 3.952 |',
    '| mascot_speaking_open | 8,045 | 904 | 3.928 |', '',
    'The first proud-face draft added amber rays outside the face. A targeted image edit removed them before saving the final output. The initial draft was never placed at the requested destination.', '',
    '## Per-entry results', '',
    'Paths below are relative to `C:/Users/Menyar/projects/new_feelio/new_feelio`. Identifiers preserve document section and asset occurrence, including repeated names. Full prompts and actual input references are recorded in `generation-log.jsonl`; dimensions and hashes are in `final-verification.json`.', '',
    '| Document identifier | Asset name | Prompt source | Reference images used | Status | Output path | Notes |',
    '|---|---|---|---|---|---|---|'
]
for row in rows:
    values = [row['identifier'], row['asset_name'], row['prompt_file'], row['reference_used'], row['status'], row['output_path'], row['issue'] or 'None']
    report.append('| ' + ' | '.join(value.replace('|', '\\|').replace('\n', ' ') for value in values) + ' |')
report += ['', 'All document occurrences have been processed. All 74 saved files were verified in their specified destinations; the two accepted mouth-frame exceptions are recorded above. No outstanding input questions remain.', '']
report_path = folder / '2-pdf-completion-report.md'
assert not report_path.exists()
report_path.write_text('\n'.join(report), encoding='utf-8')
modified = subprocess.check_output(['git', 'diff', '--name-only'], text=True).splitlines()
assert modified == ['assets/manifest.json'], modified
final_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
assert final_manifest['assets'][:68] == old_entries and len(final_manifest['assets']) == 142
print('74 outputs verified; 80 occurrences accounted for; 68 original manifest records preserved; 74 added.')
print('Report:', report_path)
