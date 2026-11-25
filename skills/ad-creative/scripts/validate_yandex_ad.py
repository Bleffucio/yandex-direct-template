"""Offline preflight for the user's 7/3/8 Yandex Direct copy package."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

NARROW = frozenset('!,.;:"')
EMOJI = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]')
LINEBREAKS = frozenset('\n\r\v\f\u0085\u2028\u2029')


def longest_word(value):
    words = re.findall(r"\w+(?:[-'’]\w+)*", value, re.UNICODE)
    return max((len(word) for word in words), default=0)


def validate(data):
    errors, warnings, counts = [], [], {}
    if not isinstance(data, dict):
        return {'ok': False, 'errors': ['Package must be a JSON object'], 'counts': {}}

    def strings(key, expected=None):
        values = data.get(key)
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            errors.append(f'{key}: expected a list of nonempty strings')
            return []
        if expected is not None and len(values) != expected:
            errors.append(f'{key}: expected {expected}, got {len(values)}')
        if len({v.strip().casefold() for v in values}) != len(values):
            errors.append(f'{key}: duplicate items')
        for i, value in enumerate(values, 1):
            if any(c in LINEBREAKS for c in value):
                errors.append(f'{key}[{i}]: line breaks are not allowed')
        return values

    def check_url(value, label):
        if not isinstance(value, str):
            errors.append(f'{label}: missing URL')
            return
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or any(c.isspace() for c in value):
            errors.append(f'{label}: expected an absolute HTTP(S) URL')

    check_url(data.get('landing_url'), 'landing_url')
    for key in ('group', 'service'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            errors.append(f'{key}: missing text')

    headlines = strings('headlines', 7)
    texts = strings('texts', 3)
    counts['headlines'] = []
    for i, value in enumerate(headlines, 1):
        longest = longest_word(value)
        counts['headlines'].append({'total': len(value), 'longest_token': longest})
        if len(value) > 56 or longest > 22:
            errors.append(f'headlines[{i}]: exceeds 56 total or 22 per word')
    counts['texts'] = []
    for i, value in enumerate(texts, 1):
        narrow = sum(c in NARROW for c in value)
        ordinary = len(value) - narrow
        longest = longest_word(value)
        counts['texts'].append({'total': len(value), 'ordinary': ordinary, 'narrow': narrow, 'longest_token': longest})
        if ordinary > 81 or narrow > 15 or longest > 23:
            errors.append(f'texts[{i}]: exceeds 81 ordinary, 15 narrow or 23 per word')

    links = data.get('sitelinks')
    if not isinstance(links, list):
        errors.append('sitelinks: expected a list')
        links = []
    if len(links) != 8:
        errors.append(f'sitelinks: expected 8, got {len(links)}')
    counts['sitelinks'] = []
    seen_titles, seen_descriptions = set(), set()
    for i, link in enumerate(links, 1):
        if not isinstance(link, dict):
            errors.append(f'sitelinks[{i}]: expected an object')
            continue
        count = {'priority': i, 'core_usp': i <= 4}
        for key, limit, seen in [('title', 30, seen_titles), ('description', 60, seen_descriptions)]:
            value = link.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f'sitelinks[{i}].{key}: missing text')
                continue
            count[key] = len(value)
            if len(value) > limit:
                errors.append(f'sitelinks[{i}].{key}: exceeds {limit}')
            if any(c in value for c in '!?[]') or any(c in LINEBREAKS for c in value) or EMOJI.search(value):
                errors.append(f'sitelinks[{i}].{key}: forbidden symbol, emoji or line break')
            normalized = value.strip().casefold()
            if normalized in seen:
                errors.append(f'sitelinks[{i}].{key}: duplicate text')
            seen.add(normalized)
        check_url(link.get('url'), f'sitelinks[{i}].url')
        counts['sitelinks'].append(count)

    pool = strings('callouts_pool')
    if not pool:
        errors.append('callouts_pool: must contain at least one item')
    if len(pool) > 50:
        errors.append('callouts_pool: exceeds 50 items')
    if sum(len(v) for v in pool) < 200:
        warnings.append('callouts_pool: below recommended 200 characters; do not invent benefits to fill it')
    for key, limit in [('callouts_pool', 300), ('callouts_desktop', 132), ('callouts_mobile', 76)]:
        if key != 'callouts_pool' and key not in data:
            continue
        values = pool if key == 'callouts_pool' else strings(key)
        if not values:
            errors.append(f'{key}: must contain at least one item')
        total = sum(len(v) for v in values)
        counts[key] = {'total': total, 'lengths': [len(v) for v in values]}
        if total > limit:
            errors.append(f'{key}: total exceeds {limit}')
        for i, value in enumerate(values, 1):
            if len(value) > 25:
                errors.append(f'{key}[{i}]: exceeds 25')
            if key != 'callouts_pool' and value not in pool:
                errors.append(f'{key}[{i}]: not in callouts_pool')
    return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'counts': counts,
            'manual_checks': ['group mask/service in every headline', 'confirmed benefits and sources',
                              'all 21 headline/text combinations', 'first four sitelinks contain core USPs', 'landing and sitelink contents',
                              'real URL availability and platform moderation']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    try:
        report = validate(json.loads(args.package.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, TypeError) as exc:
        report = {'ok': False, 'errors': [str(exc)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
