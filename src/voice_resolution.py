"""Resolve declared voice choices without activating rules or inventing evidence.

Construction owns the operation. These helpers project provider inputs and
validate the choices a construction provider returns against the frozen corpus.
"""
import copy
import hashlib
import re


PROFILE = 'resolved-voice-v1'
LAYERS = {'conceptual', 'epistemic', 'rhetorical', 'linguistic'}


def validate_written_calibration(value):
    """A passage approval is distinct from authentic speech or a corpus rule."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError('Written calibration must be a list of approved passage records')
    required = {'id', 'source_path', 'sha256', 'text', 'authority', 'scope', 'author_judgment'}
    seen = set()
    for item in value:
        if (not isinstance(item, dict) or not required <= set(item)
                or set(item) - required - {'note'}
                or any(not isinstance(item[key], str) or not item[key].strip() for key in required)
                or ('note' in item and not isinstance(item['note'], str))):
            raise ValueError('Complete written calibration provenance and author judgment required')
        if (item['id'] in seen or item['authority'] != 'generated_author_approved_passage'
                or item['scope'] != 'passage_only'
                or hashlib.sha256(item['text'].encode('utf-8')).hexdigest() != item['sha256']):
            raise ValueError('Calibration must identify an exact author-approved generated passage')
        seen.add(item['id'])
    return copy.deepcopy(value)


def rule_layers(rule):
    value = rule['payload'].get('Layer', '')
    if not isinstance(value, str):
        raise ValueError('A resolved voice rule requires declared layers')
    layers = {part.strip().lower() for part in re.split(r'[;,/|]', value) if part.strip()}
    if not layers or not layers <= LAYERS:
        raise ValueError('A resolved voice rule requires recognized layers')
    return layers


def _catalog(voice):
    rules, exemplars = {}, {}
    for item in voice['voice_candidates']:
        key = item['payload'].get('Rule ID')
        if not isinstance(key, str) or not key.strip() or key in rules:
            raise ValueError('Unique rule keys required for voice resolution')
        rule_layers(item)
        rules[key] = item
    for item in voice['authentic_exemplars']:
        key = item['node']['payload'].get('Exemplar ID')
        if not isinstance(key, str) or not key.strip() or key in exemplars:
            raise ValueError('Unique authentic exemplar keys required for voice resolution')
        exemplars[key] = item
    return rules, exemplars


def resolve_voice_bindings(acts, voice):
    """Return acts with human keys and verified graph identities on each binding.

Provider input: rule_id=R-key and exemplar_ids=E-keys. Stored binding:
rule_id=graph ID, rule_key=R-key, exemplar_ids=graph IDs,
exemplar_keys=E-keys, layer, application, criterion.
"""
    rules, exemplars = _catalog(voice)
    resolved = copy.deepcopy(acts)
    required = {'rule_id', 'exemplar_ids', 'layer', 'application', 'criterion'}
    for act in resolved:
        bindings = act.get('voice_bindings')
        if not isinstance(bindings, list) or not bindings:
            raise ValueError('Each resolved act requires explicit voice bindings')
        output = []
        for binding in bindings:
            if not isinstance(binding, dict) or set(binding) != required:
                raise ValueError('A voice binding requires rule, exemplars, layer, application and criterion')
            key, chosen, layer = binding['rule_id'], binding['exemplar_ids'], binding['layer']
            if (not isinstance(key, str) or key not in rules or not isinstance(layer, str)
                    or layer not in rule_layers(rules[key])):
                raise ValueError('Voice binding must use a known rule in its declared layer')
            if (not isinstance(chosen, list) or not chosen
                    or any(not isinstance(item, str) or item not in exemplars for item in chosen)
                    or len(set(chosen)) != len(chosen)):
                raise ValueError('Voice binding requires unique authentic exemplar keys')
            if any(not isinstance(binding[field], str) or not binding[field].strip()
                   for field in ('application', 'criterion')):
                raise ValueError('Voice application and check criterion must be explicit')
            rule = rules[key]
            grounding = {target for relation, target in voice['voice_evidence'][rule['id']]['edges']
                         if relation == 'grounded_in'}
            ids = [exemplars[item]['id'] for item in chosen]
            if not set(ids) <= grounding:
                raise ValueError('Selected exemplars must ground the selected rule')
            output.append({'rule_id': rule['id'], 'rule_key': key,
                           'exemplar_ids': ids, 'exemplar_keys': list(chosen),
                           'layer': layer, 'application': binding['application'],
                           'criterion': binding['criterion']})
        act['voice_bindings'] = output
    return resolved


def validate_resolved_bindings(acts, voice):
    """Revalidate frozen identities when the construction snapshot is read."""
    external = copy.deepcopy(acts)
    for act in external:
        bindings = act.get('voice_bindings')
        if not isinstance(bindings, list) or not bindings:
            raise ValueError('Resolved acts require frozen voice bindings')
        translated = []
        for binding in bindings:
            if not isinstance(binding, dict):
                raise ValueError('Malformed frozen voice binding')
            translated.append({'rule_id': binding.get('rule_key'),
                               'exemplar_ids': binding.get('exemplar_keys'),
                               'layer': binding.get('layer'),
                               'application': binding.get('application'),
                               'criterion': binding.get('criterion')})
        act['voice_bindings'] = translated
    if resolve_voice_bindings(external, voice) != acts:
        raise ValueError('Frozen voice binding identities differ from their corpus grounding')


def compact_voice_catalog(voice, bindings=None):
    """Each catalog rule, excerpt, source transcript and result appears once."""
    rules, exemplars = _catalog(voice)
    selected_rules = None if bindings is None else {item['rule_id'] for item in bindings}
    selected_exemplars = None if bindings is None else {
        ident for item in bindings for ident in item['exemplar_ids']}
    rule_records, exemplar_records, sources, other = [], [], {}, {}
    authentic_ids = {item['id'] for item in exemplars.values()}
    for key, item in sorted(rules.items()):
        if selected_rules is not None and item['id'] not in selected_rules:
            continue
        grounded = [target for relation, target in voice['voice_evidence'][item['id']]['edges']
                    if relation == 'grounded_in']
        rule_records.append({'id': item['id'], 'rule_id': key,
                             'payload': copy.deepcopy(item['payload']),
                             'authority': item['authority'], 'grounding_ids': grounded,
                             'exemplar_ids': sorted(exemplar_key for exemplar_key, exemplar in exemplars.items()
                                                    if exemplar['id'] in grounded)})
        for ident in grounded:
            if ident not in authentic_ids:
                other[ident] = copy.deepcopy(voice['voice_evidence'][ident]['node'])
    for key, item in sorted(exemplars.items()):
        if selected_exemplars is not None and item['id'] not in selected_exemplars:
            continue
        exemplar_records.append({'id': item['id'], 'exemplar_id': key,
                                 'payload': copy.deepcopy(item['node']['payload']),
                                 'authority': item['authority'],
                                 'source_ids': [source['id'] for source in item['sources']]})
        for source in item['sources']:
            sources[source['id']] = copy.deepcopy(source)
    return {'rules': rule_records, 'exemplars': exemplar_records,
            'sources': [sources[key] for key in sorted(sources)],
            'grounding_records': [other[key] for key in sorted(other)]}


def construction_packet(context):
    evidence = copy.deepcopy(context['evidence'])
    evidence['intent'] = {'origin': 'author_input', 'reference': 'top-level intent'}
    return {'execution_profile': PROFILE, 'intent': context['intent'], 'evidence': evidence,
            'voice_catalog': compact_voice_catalog(context),
            'written_calibration': copy.deepcopy(context.get('written_calibration', [])),
            'instruction': context['instruction']}


def construction_review_packet(snapshot):
    nodes = snapshot['nodes']
    acts, claim_ids = [], set()
    for ident in snapshot['acts']:
        record = nodes[ident]
        claims = [target for relation, target in record['edges'] if relation == 'asserts']
        claim_ids.update(claims)
        acts.append({'id': ident, **copy.deepcopy(record['node']['payload']), 'claim_ids': claims})
    claims, evidence_ids = [], set()
    for ident in sorted(claim_ids):
        record = nodes[ident]
        evidence = [target for relation, target in record['edges'] if relation == 'supports']
        evidence_ids.update(evidence)
        claims.append({'id': ident, **copy.deepcopy(record['node']['payload']), 'evidence_ids': evidence})
    evidence = []
    for ident in sorted(evidence_ids):
        node = copy.deepcopy(nodes[ident]['node'])
        if node['payload'].get('origin') == 'author_input':
            node['payload'] = {'origin': 'author_input', 'reference': 'top-level intent'}
        evidence.append(node)
    return {'execution_profile': PROFILE, 'plan': snapshot['plan'],
            'intent': nodes[snapshot['intent']]['node']['payload']['text'],
            'acts': acts, 'claims': claims, 'evidence': evidence,
            'voice_catalog': compact_voice_catalog(snapshot),
            'written_calibration': copy.deepcopy(snapshot.get('written_calibration', [])),
            'instruction': ('Review the construction and each act-specific voice choice against the '
                            'full available catalog, including material omissions and criteria that '
                            'only repeat subject content. '
                            'Check whether its application and criterion fit the act and '
                            'the cited rule and authentic exemplar. Preserve candidate rule '
                            'status and distinguish passage approval from corpus validation.')}
