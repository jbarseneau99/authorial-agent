"""Exact prompt/data flow and paragraph gates; regenerated from code."""
from pathlib import Path
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=Path('Authorial_Agent_Four_Layer_Procedure.png'))
args = parser.parse_args()
fig, ax = plt.subplots(figsize=(17, 20.5), dpi=150)
ax.set_xlim(0, 17); ax.set_ylim(0, 20.5); ax.axis('off')
fig.patch.set_facecolor('white')
ink = '#18324B'; border = '#8DA0B6'; blue = '#E8F0FC'
violet = '#EEE8F8'; amber = '#FFF0DD'; green = '#E4F2E9'

def box(x, y, w, h, title, body, color, fs=12):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.10,rounding_size=0.12',
                               lw=1.3, edgecolor=border, facecolor=color))
    ax.text(x+w/2, y+h-.17, title, ha='center', va='top', fontsize=fs+1,
            fontweight='bold', color=ink)
    ax.text(x+w/2, y+h/2-.18, body, ha='center', va='center', fontsize=fs,
            color=ink, linespacing=1.45)

def arrow(points, color='#55728E', style='-', label=None, at=None):
    for a, b in zip(points[:-2], points[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], lw=1.65, color=color, linestyle=style)
    ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle='-|>', mutation_scale=13,
                                lw=1.65, color=color, linestyle=style))
    if label:
        ax.text(*at, label, ha='center', va='center', fontsize=10.5, color=color,
                bbox=dict(facecolor='white', edgecolor='none', pad=2))

ax.text(8.5, 20.35, 'FOUR LAYERS — ONE CHECKED PARAGRAPH AT A TIME',
        ha='center', va='top', fontsize=22, fontweight='bold', color=ink)
ax.text(8.5, 19.62, 'The same Execution coordinator runs every loop. Code records exact prompts, outputs and versions.',
        ha='center', fontsize=12.8, color='#526578')

box(.3, 15.9, 3.55, 3.0, 'VERSIONED VOICE CORPUS',
    'Conceptual rules\nEpistemic rules\nRhetorical rules\nLinguistic rules\n\nAuthentic exemplar passages\nwith original source lineage', blue, 12)
box(.3, 12.95, 3.55, 2.25, 'SELECT AND FREEZE',
    'Selected rule IDs\nExemplar IDs + exact passages\nSource references\nLedger version + hashes\n\nRetain candidate / approval status', green, 11.5)
arrow([(2.08, 15.8), (2.08, 15.3)])

box(4.85, 18.05, 6.15, .8, 'AUTHOR INTENT + SOURCE EVIDENCE',
    'Bind procedure, code, ledger, sources and paragraph grouping.', '#F3F6FA', 10.8)
arrow([(7.93, 17.95), (7.93, 17.55)])

box(4.85, 15.95, 6.15, 1.5, '1  CONSTRUCTION PROMPT',
    'Intent + source evidence\nConceptual and epistemic rules + exemplar passages\nRhetorical rules for intellectual-act purpose and order', blue, 11.4)
box(11.65, 15.95, 3.85, 1.5, 'LLM RETURNS STRUCTURE',
    'Claims: text, origin, evidence IDs\nOrdered intellectual acts:\npurpose + claim IDs', blue, 11.2)
arrow([(11.1, 16.7), (11.55, 16.7)], label='call', at=(11.33, 17.0))
arrow([(13.57, 15.85), (13.57, 15.4), (7.93, 15.4), (7.93, 15.02)],
      label='exact structured output', at=(10.6, 15.4))

box(4.85, 13.4, 6.15, 1.5, '2  CONSTRUCTION REVIEW PROMPT',
    'Constructed argument + source evidence\nSame frozen conceptual / epistemic bindings\nRhetorical plan + its rules and exemplar passages', blue, 11.4)
box(11.65, 13.4, 3.85, 1.5, 'LLM RETURNS FINDINGS',
    'Conceptual fidelity\nEvidence and reasoning\nIntellectual-act plan', blue, 11.4)
arrow([(11.1, 14.15), (11.55, 14.15)], label='call', at=(11.33, 14.45))
arrow([(13.57, 13.3), (13.57, 12.98), (7.93, 12.98), (7.93, 12.7)])
box(4.85, 11.85, 6.15, .72, 'CODE GATE: CONSTRUCTION CLOSED',
    'Require current checks, exact revision and closure authority.', green, 10.8)
arrow([(7.93, 11.75), (7.93, 11.22)])

box(4.85, 9.6, 6.15, 1.5, '3  EXPRESSION PROMPT — ONE PARAGRAPH',
    'Closed argument + current paragraph’s ordered acts\nRhetorical and linguistic rules + actual exemplar passages\nDefinitions, qualifications + prior checked paragraphs', violet, 11.2)
box(11.65, 9.6, 3.85, 1.5, 'LLM RETURNS ONE PARAGRAPH',
    'Sentences + sentence-to-act IDs\nOR a construction-reopen request\nCode rejects extra paragraphs', violet, 11.0)
arrow([(11.1, 10.35), (11.55, 10.35)], label='call', at=(11.33, 10.65))
arrow([(13.57, 9.5), (13.57, 9.05), (7.93, 9.05), (7.93, 8.72)],
      label='exact paragraph + act mapping', at=(10.6, 9.05))

box(4.85, 7.1, 6.15, 1.5, '4  FOUR-LAYER CHECKING PROMPT',
    'Paragraph + closed argument + sentence / act mapping\nSame selected rules and actual exemplar passages\nConceptual, epistemic, rhetorical and linguistic fidelity', amber, 11.1)
box(11.65, 7.1, 3.85, 1.5, 'LLM RETURNS FINDINGS',
    'Pass / fail / uncertain\nReasons + affected sentences\nCode selects the repair route', amber, 11.3)
arrow([(11.1, 7.85), (11.55, 7.85)], label='call', at=(11.33, 8.15))
arrow([(13.57, 7.0), (13.57, 6.55), (7.93, 6.55), (7.93, 6.17)],
      label='all four layers pass', at=(10.6, 6.55))

# The same selected rule/exemplar evidence reaches all four prompts.
bus = '#50856F'
ax.plot([4.3, 4.3], [7.85, 16.7], color=bus, lw=1.8, linestyle='--')
arrow([(3.95, 14.08), (4.3, 14.08)], bus, style='--')
for y in (16.7, 14.15, 10.35, 7.85):
    arrow([(4.3, y), (4.75, y)], bus, style='--')
ax.text(2.08, 12.3, 'Green dashed arrows =\nselected rules AND\nactual exemplar passages\nin every prompt.', ha='center', va='top', fontsize=12,
        color=bus, linespacing=1.45)
box(.3, 7.1, 3.55, 3.0, 'FOUR-LAYER REPAIR',
    'Previous exact paragraph\n+ exact check findings\n+ same frozen voice bindings\n\nExpression defect → edit\nReasoning defect → construct\nConceptual change → author', amber, 10.8)

box(4.85, 4.6, 6.15, 1.45, 'PANGRAM GATE — THIS PARAGRAPH ONLY',
    'Submit exact checked text + preserve its hash\nPoll the same task; record the complete result\nA detector result is separate from authorial validation', green, 11.1)
box(11.65, 4.6, 3.85, 1.45, 'DETECTOR RESULT',
    'Passed: progression permitted\nPending / flagged / error /\nunscorable: PAUSE', amber, 11.4)
arrow([(11.1, 5.32), (11.55, 5.32)], label='API', at=(11.33, 5.62))
# A passing scan returns to the SAME expression loop for the next paragraph.
arrow([(15.6, 5.65), (16.3, 5.65), (16.3, 11.48), (7.93, 11.48), (7.93, 11.22)],
      '#8165A7', label='Current pass + more paragraphs → next paragraph', at=(12.6, 11.48))
arrow([(13.57, 4.5), (13.57, 4.02), (7.93, 4.02), (7.93, 3.62)],
      label='all paragraphs passed', at=(10.6, 4.02))

box(.3, 3.95, 3.55, 2.35, 'CODE CONTROLS PROGRESSION',
    'Check detector setup before writing.\nA pending scan starts no new prose.\nA flag starts no automatic rewrite.\nChanged text invalidates its checks.\nKeep each attempt and result.', '#F3F6FA', 10.5)
box(4.85, 2.5, 6.15, 1.0, 'ASSEMBLE THE CHECKED PARAGRAPHS',
    'Preserve their exact text and order.\nSeparate whole-chapter semantic review remains PENDING.', blue, 10.9)
arrow([(7.93, 2.4), (7.93, 2.08)])
box(4.85, .95, 6.15, 1.0, 'YOUR VALIDATION + VERSIONED RESULT',
    'Recheck every paragraph and scan before author approval.\nPreserve procedure, ledger, prompts, outputs and observations.', green, 10.7)
box(11.65, 1.0, 3.85, 1.45, 'ONE EXECUTION COORDINATOR',
    'One owning file per loop.\nNo second scheduler.\nNo silent procedure changes.', '#F3F6FA', 11.3)
ax.text(8.5, .30, 'Diagram of the coded flow. Fixture verification is distinct from a live manuscript run and from your voice judgment.',
        ha='center', va='center', fontsize=10.4, color='#526578')
args.output.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(args.output, bbox_inches='tight', pad_inches=.2)
plt.close(fig)
