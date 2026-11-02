"""Adds scripted guest members to a published round, for live demos.

Run from FSD with the integration stack up, after the organiser publishes and copies the invite link:
    python3 integration/seed_demo_members.py '<invite link>' [--members 3]

Each member joins through the invite and submits a full response. The members disagree on purpose,
so the result shows a real trade-off. Requirements get the most permissive answer, so a member never
rules out every option. Written answers never mention prices, amounts or must-haves: those are read as requirements, and an\nunclear amount leaves the run waiting for clarification, which the app cannot resolve on screen yet.
Rerunning adds new members; it never edits earlier ones.
"""
import argparse
import re
import sys
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from test_http_lifecycle import PLANNING, PARTICIPATION, call

PERSONAS = [
    {'name': 'Priya', 'text': 'Somewhere relaxed where we can actually talk.'},
    {'name': 'Marcus', 'text': 'I like lively places with a bit of buzz.'},
    {'name': 'Wei Ling', 'text': 'Somewhere cosy would be nice.'},
    {'name': 'Daniel', 'text': 'Somewhere with good food and a nice atmosphere.'},
    {'name': 'Aisha', 'text': 'I prefer quieter places.'},
]
OPEN_LABELS = re.compile(r'\b(no preference|any|anything|none|no restrictions?|flexible|either|no)\b', re.I)


def invite_parts(link):
    fields = parse_qs(urlparse(link).fragment or urlparse(link).query)
    try:
        return fields['round'][0], fields['invite'][0]
    except KeyError:
        sys.exit('That is not an invite link. It should contain "round=" and "invite=".')


def choice_id(choice):
    return choice if isinstance(choice, str) else choice['choice_id']


def choice_label(choice):
    return choice if isinstance(choice, str) else choice.get('label', choice['choice_id'])


def facts_for(snapshot, criterion):
    return [f for o in snapshot['options'] for f in o.get('facts') or [] if f.get('criterion') == criterion]


def numbers(facts):
    found = []
    for fact in facts:
        try:
            found.append(float(fact['value']))
        except (TypeError, ValueError):
            pass
    return found


def matches(choice, facts):
    wanted = {choice_id(choice).lower(), choice_label(choice).lower()}
    values = [v for f in facts for v in (f['value'] if isinstance(f['value'], list) else [f['value']])]
    return sum(str(v).lower() in wanted for v in values)


def permissive_choice(q, snapshot):
    choices = q.get('choices') or []
    if not choices:
        return None
    open_choice = next((c for c in choices if OPEN_LABELS.search(choice_label(c))), None)
    if open_choice is not None:
        return choice_id(open_choice)
    facts = facts_for(snapshot, q.get('criterion'))
    priced = [(float(n[0]), c) for c in choices if (n := re.findall(r'\d+(?:\.\d+)?', choice_label(c)))]
    if numbers(facts) and priced:
        # A numeric limit such as a budget: the highest one rules out the fewest options.
        return choice_id(max(priced, key=lambda pair: pair[0])[1])
    # Otherwise the choice most options meet, so the requirement removes as little as possible.
    return choice_id(max(choices, key=lambda c: matches(c, facts)))


def ratings(snapshot, index):
    # Each member puts a different option first, so no option is everyone's favourite.
    options = [o['option_id'] for o in snapshot['options']]
    count = len(options)
    order = options[index % count:] + options[:index % count]
    scale = [4, 3, 2, 1, 1] if index % 2 == 0 else [4, 2, 2, 1, 0]
    return {option: scale[min(rank, len(scale) - 1)] for rank, option in enumerate(order)}


def answer(q, snapshot, index):
    fmt = q.get('answer_format')
    hard = q.get('role') == 'hard'
    choices = q.get('choices') or []
    if fmt == 'option_rating':
        return ratings(snapshot, index)
    if fmt == 'date_poll':
        days = sorted(d for d in map(choice_id, choices) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', d))
        return {day: 'maybe' if (index + n) % 3 == 2 else 'yes' for n, day in enumerate(days)} or None
    if fmt == 'date_intervals':
        start = date.today() + timedelta(days=7)
        return [{'start_date': start.isoformat(), 'end_date': (start + timedelta(days=14)).isoformat()}]
    if fmt == 'choice':
        if hard:
            return permissive_choice(q, snapshot)
        return choice_id(choices[index % len(choices)]) if choices else None
    if fmt == 'multi_choice':
        if hard:
            picked = permissive_choice(q, snapshot)
            return [picked] if picked else None
        if not choices:
            return None
        return sorted({choice_id(choices[index % len(choices)]), choice_id(choices[(index + 2) % len(choices)])})
    if fmt == 'boolean':
        facts = facts_for(snapshot, q.get('criterion'))
        if hard:
            # Either answer to a yes/no requirement can rule options out, so leave it blank when allowed.
            if not q.get('required'):
                return None
            yes = sum(str(f['value']).lower() == 'true' for f in facts)
            return yes >= len(facts) - yes
        return index % 2 == 0
    if fmt == 'number':
        values = numbers(facts_for(snapshot, q.get('criterion')))
        if hard:
            # A limit every option meets, so no member rules anything out on their own.
            return round(max(values) * 1.2) if values else 1000
        if not values:
            return None
        low, high = min(values), max(values)
        return round(low + (high - low) * [0.25, 0.75, 0.5, 0.1, 0.9][index % 5])
    if fmt in (None, '', 'text'):
        return None if hard else PERSONAS[index % len(PERSONAS)]['text']
    return None


def weighable(q):
    return (q.get('role') or 'soft') == 'soft' and q.get('criterion') not in (None, 'preferences', 'context')


def importances(snapshot, index):
    # Raising every answer would cancel out, so each member stresses one question and some play down another.
    ids = [q['question_id'] for q in snapshot['questions'] if weighable(q)]
    if not ids:
        return {}
    marks = {ids[index % len(ids)]: 'high'}
    if index % 2 and len(ids) > 1:
        marks[ids[(index + 1) % len(ids)]] = 'low'
    return marks


def describe(value, snapshot):
    titles = {o['option_id']: o['title'] for o in snapshot['options']}
    if isinstance(value, dict):
        return ', '.join(f'{titles.get(k, k)} {v}' for k, v in value.items())
    return str(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('link', help='the invite link the organiser copied')
    parser.add_argument('--members', type=int, default=3, choices=range(1, len(PERSONAS) + 1), metavar='1-5')
    args = parser.parse_args()
    round_id, invite = invite_parts(args.link)

    for index in range(args.members):
        persona = PERSONAS[index]
        user = call(PLANNING, 'POST', '/v1/users', {'username': f"demo-{persona['name'].lower().replace(' ', '-')}-{uuid4().hex[:6]}"}, status=201)
        token = user['session_token']
        call(PLANNING, 'POST', f'/v1/invites/{invite}/join', {'user_id': user['id'], 'display_name': persona['name']}, token)
        snapshot = call(PLANNING, 'GET', f'/v1/rounds/{round_id}/form', token=token)
        answers, marks = [], importances(snapshot, index)
        print(f"\n{persona['name']}")
        for q in snapshot['questions']:
            value = answer(q, snapshot, index)
            if value is None:
                if q.get('required'):
                    sys.exit(f"  Cannot answer required question '{q['label']}' ({q.get('answer_format')}). Answer it by hand instead.")
                print(f"  skip  {q['label']}")
                continue
            row = {'question_id': q['question_id'], 'value': value}
            if q['question_id'] in marks:
                row['importance'] = marks[q['question_id']]
            answers.append(row)
            weight = f" [{row['importance']}]" if 'importance' in row else ''
            print(f"  {q['label']}: {describe(value, snapshot)}{weight}")
        path = f'/rounds/{round_id}/my-response'
        saved = call(PARTICIPATION, 'PUT', path, {
            'expectedRevision': 0, 'acknowledgedOptionRevision': snapshot['option_revision'],
            'availability': [], 'budget': {'kind': 'UNANSWERED'}, 'activityAnswers': [], 'privateNote': None,
            'answers': answers}, token)
        call(PARTICIPATION, 'POST', path + '/submit', {'expectedRevision': saved['revision']}, token)
        print('  submitted')


if __name__ == '__main__':
    main()
