"""Compact resolved voice inputs and shared criterion identities.

This is a projection of a closed construction, not an alternative loop owner.
The full graph remains stored for freshness and source-aware checking. Candidate
rules and approved generated calibration retain their limited recorded authority.
"""
import hashlib
import json
from voice_resolution import PROFILE, LAYERS, rule_layers, validate_written_calibration


BASE_CRITERIA = (
    ('conceptual', 'Preserve the constructed claims and distinctions without introducing, collapsing or substituting concepts.'),
    ('epistemic', 'Preserve the declared provenance, epistemic status and qualifications of each claim without adding unsupported factual support.'),
    ('rhetorical', 'Realize the ordered intellectual acts directly, with their intended relations and sufficient context, without unnecessary announcements.'),
    ('linguistic', 'Apply the selected voice instructions within their recorded scope; express the acts clearly without unnecessary announcements or redundant qualifications.'),
)


def _copy(value):
    return json.loads(json.dumps(value))


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text')
    return value


def _ids(value, label):
    if (not isinstance(value, list) or not value or any(not isinstance(v, str) or not v for v in value)
            or len(set(value)) != len(value)):
        raise ValueError(label + ' must contain unique identities')
    return value


def _resolved(context):
    if context.get('execution_profile') != PROFILE:
        raise ValueError('Resolved voice execution profile required')
    acts = _ids(context.get('acts'), 'Current acts')
    nodes = context.get('nodes')
    if not isinstance(nodes, dict):
        raise ValueError('Closed construction nodes required')
    rules = {item['id']: item for item in context.get('voice_candidates', [])}
    exemplars = {item['id']: item for item in context.get('authentic_exemplars', [])}
    selected_rules, selected_exemplars, plans = {}, {}, []
    for act_id in acts:
        record = nodes.get(act_id, {})
        node = record.get('node', {})
        if node.get('kind') != 'act' or node.get('id') != act_id:
            raise ValueError('Current act is absent from the closed construction')
        payload = node['payload']
        _text(payload.get('purpose'), 'Act purpose')
        bindings = payload.get('voice_bindings')
        if not isinstance(bindings, list) or not bindings:
            raise ValueError('Every resolved act requires explicit voice bindings')
        for binding in bindings:
            if not isinstance(binding, dict):
                raise ValueError('Structured voice binding required')
            rule_id, layer = binding.get('rule_id'), binding.get('layer')
            rule = rules.get(rule_id)
            if rule is None or layer not in LAYERS:
                raise ValueError('Binding rule or layer is unavailable')
            rule_payload = rule['payload']
            if (binding.get('rule_key') != rule_payload.get('Rule ID')
                    or layer not in rule_layers(rule)):
                raise ValueError('Binding rule key or layer differs from its evidence')
            _text(binding.get('application'), 'Binding application')
            _text(binding.get('criterion'), 'Binding criterion')
            exemplar_ids = _ids(binding.get('exemplar_ids'), 'Binding exemplars')
            exemplar_keys = binding.get('exemplar_keys')
            if not isinstance(exemplar_keys, list) or len(exemplar_keys) != len(exemplar_ids):
                raise ValueError('Binding exemplar keys must match their identities')
            grounding = context.get('voice_evidence', {}).get(rule_id, {}).get('edges', [])
            for ident, key in zip(exemplar_ids, exemplar_keys):
                exemplar = exemplars.get(ident)
                if (exemplar is None or exemplar['node']['payload'].get('Exemplar ID') != key
                        or not any(rel == 'grounded_in' and target == ident for rel, target in grounding)):
                    raise ValueError('Binding exemplar is not authentic grounding for its rule')
                selected_exemplars[ident] = exemplar
            selected_rules[rule_id] = rule
        plans.append((act_id, record))
    return plans, selected_rules, selected_exemplars


def resolved_criteria(context):
    """The writer and checker use identical IDs and exact criterion wording."""
    plans, _, _ = _resolved(context)
    acts = [ident for ident, _ in plans]
    criteria = [
        {'id': 'base:' + layer, 'layer': layer, 'act_ids': list(acts),
         'rule_ids': [], 'exemplar_ids': [], 'criterion': criterion}
        for layer, criterion in BASE_CRITERIA
    ]
    for act_id, record in plans:
        for index, binding in enumerate(record['node']['payload']['voice_bindings']):
            criteria.append({
                'id': f'binding:{act_id}:{index}', 'layer': binding['layer'],
                'act_ids': [act_id], 'rule_ids': [binding['rule_id']],
                'exemplar_ids': list(binding['exemplar_ids']), 'criterion': binding['criterion'],
            })
    return criteria


def _repair(context):
    """Preserve exact repair evidence without recursively repeating source graphs."""
    prior = context.get('prior_draft')
    if not isinstance(prior, dict) or not isinstance(prior.get('sentences'), list):
        raise ValueError('Resolved repair requires its exact prior draft')
    details = prior.get('detail', {}).get('sentences', [])
    if len(details) != len(prior['sentences']):
        raise ValueError('Prior draft sentence-to-act mapping is incomplete')
    sentences = []
    for sentence, detail in zip(prior['sentences'], details):
        text = sentence['payload']['text']
        if text.strip() != detail.get('text', '').strip():
            raise ValueError('Prior draft differs from its recorded expression')
        sentences.append({'id': sentence['id'], 'text': text,
                          'acts': _ids(detail.get('acts'), 'Prior sentence acts')})
    result = {key: _copy(context[key]) for key in (
        'editing_attempt', 'previous_run', 'assessment', 'assessment_snapshot_sha256',
        'findings', 'affected_sentences', 'affected_acts', 'instruction', 'local_repair_policy') if key in context}
    result['prior_draft'] = {'plan': prior['plan'], 'text': prior['text'],
                            'text_sha256': prior['text_sha256'], 'sentences': sentences}
    return result


def compact_writer_context(context):
    plans, rules, exemplars = _resolved(context)
    nodes = context['nodes']
    intent = nodes.get(context.get('intent'), {}).get('node', {})
    if intent.get('kind') != 'intent':
        raise ValueError('Closed author intent required')
    claims, references, intellectual_plan = {}, {}, []
    for act_id, record in plans:
        claim_ids = [target for relation, target in record['edges'] if relation == 'asserts']
        if not claim_ids:
            raise ValueError('Resolved act must preserve its constructed claims')
        for claim_id in claim_ids:
            claim_record = nodes.get(claim_id, {})
            node = claim_record.get('node', {})
            if node.get('kind') != 'claim':
                raise ValueError('Missing constructed claim')
            evidence = [target for relation, target in claim_record['edges'] if relation == 'supports']
            claims[claim_id] = {'id': claim_id, 'text': node['payload']['text'],
                                'origin': node['payload']['origin'],
                                'verified': node['payload'].get('verified', False), 'evidence_refs': evidence}
            for ident in evidence:
                source = nodes.get(ident, {}).get('node', {})
                if source.get('kind') != 'evidence':
                    raise ValueError('Claim evidence reference is unavailable')
                payload = source['payload']
                body = _text(payload.get('text'), 'Source evidence text')
                references[ident] = {'id': ident, 'revision': source['revision'],
                                     'origin': payload.get('origin'), 'source': payload.get('source'),
                                     'text_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
                                     'text_visibility': 'withheld_from_expression'}
        bindings = record['node']['payload']['voice_bindings']
        intellectual_plan.append({'id': act_id, 'purpose': record['node']['payload']['purpose'],
                                  'claim_ids': claim_ids, 'voice_bindings': _copy(bindings),
                                  'criterion_ids': [f'binding:{act_id}:{i}' for i in range(len(bindings))]})
    voice_rules = [
        {'id': ident, 'key': rule['payload']['Rule ID'], 'layer': rule['payload']['Layer'],
         'candidate_rule': rule['payload']['Candidate rule'], 'authority': rule['authority'],
         'status': rule['payload'].get('Status'), 'applicability': rule['payload'].get('Applicability'),
         'review_note': rule['payload'].get('Review note'), 'activation': rule['payload'].get('activation')}
        for ident, rule in sorted(rules.items())
    ]
    voice_exemplars, sources = [], {}
    for ident, exemplar in sorted(exemplars.items()):
        node, source_ids = exemplar['node'], []
        payload = node['payload']
        for source in exemplar['sources']:
            transcript = _text(source['payload'].get('User transcript (segments joined)'), 'Voice transcript')
            if payload.get('Exact excerpt') not in transcript:
                raise ValueError('Selected exemplar differs from its authentic transcript')
            source_ids.append(source['id'])
            sources[source['id']] = {'id': source['id'], 'source_key': source['payload'].get('Source ID'),
                                     'transcript': transcript}
        voice_exemplars.append({'id': ident, 'key': payload['Exemplar ID'], 'source_ids': source_ids,
                                'excerpt': payload['Exact excerpt'], 'layer': payload.get('Layer'),
                                'intellectual_act': payload.get('Intellectual act'),
                                'exemplar_type': payload['Exemplar type'],
                                'written_validation': payload.get('Written validation'),
                                'authority': exemplar['authority']})
    packet = {
        'execution_profile': PROFILE, 'intent': _text(intent['payload'].get('text'), 'Author intent'),
        'acts': list(context['acts']), 'intellectual_plan': intellectual_plan,
        'claims': list(claims.values()), 'source_references': list(references.values()),
        'voice_rules': voice_rules, 'voice_exemplars': voice_exemplars,
        'source_contexts': [sources[key] for key in sorted(sources)],
        'written_calibration': validate_written_calibration(context.get('written_calibration', [])),
        'criteria': resolved_criteria(context), 'prior_paragraphs': _copy(context.get('prior_paragraphs', [])),
        'subject_source_policy': 'references_only; source prose is available only to the independent checker',
        'instruction': ('Realize this ordered intellectual plan using its per-act voice applications and '
                        'criteria. Preserve claim content and epistemic boundaries. Candidate rules retain '
                        'their recorded scope; approved generated calibration is passage-level evidence, '
                        'not a general rule or subject evidence. Return sentences with act IDs in order, '
                        'or request reopening for a construction defect.'),
    }
    if 'paragraph' in context:
        packet['paragraph'] = _copy(context['paragraph'])
        packet['instruction'] += ' Return exactly one paragraph without paragraph separators; prior paragraphs are continuity context.'
    if 'repair' in context:
        packet['repair'] = _repair(context['repair'])
    return packet
