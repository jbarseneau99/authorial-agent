"""Exact prompt/data-flow diagram; regenerate from code, not raster editing."""
from pathlib import Path
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=Path('Authorial_Agent_Four_Layer_Procedure.png'))
args = parser.parse_args()
fig,ax=plt.subplots(figsize=(16,16),dpi=150)
ax.set_xlim(0,16); ax.set_ylim(0,16); ax.axis('off')
fig.patch.set_facecolor('white')
ink='#18324B'; border='#8DA0B6'; blue='#E8F0FC'; violet='#EEE8F8'; amber='#FFF0DD'; green='#E4F2E9'
def box(x,y,w,h,title,body,color,fs=12):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.10,rounding_size=0.12',lw=1.3,edgecolor=border,facecolor=color))
    ax.text(x+w/2,y+h-.17,title,ha='center',va='top',fontsize=fs+1,fontweight='bold',color=ink)
    ax.text(x+w/2,y+h/2-.18,body,ha='center',va='center',fontsize=fs,color=ink,linespacing=1.45)
def arrow(points,color='#55728E',style='-',label=None,at=None):
    for a,b in zip(points[:-2],points[1:-1]):
        ax.plot([a[0],b[0]],[a[1],b[1]],lw=1.65,color=color,linestyle=style)
    ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',mutation_scale=13,lw=1.65,color=color,linestyle=style))
    if label: ax.text(*at,label,ha='center',va='center',fontsize=10,color=color,bbox=dict(facecolor='white',edgecolor='none',pad=2))

ax.text(8,15.90,'FOUR LAYERS: RULES, EXEMPLARS AND LLM CALLS',ha='center',va='top',fontsize=22,fontweight='bold',color=ink)
ax.text(8,15.17,'Code builds each prompt, records the exact inputs and checks the returned output.',ha='center',fontsize=13,color='#526578')

box(.3,11.5,3.55,3.0,'VERSIONED VOICE CORPUS',
    'Conceptual rules\nEpistemic rules\nRhetorical rules\nLinguistic rules\n\nAuthentic exemplar passages\nwith original source lineage',blue,12)
box(.3,8.55,3.55,2.25,'SELECT AND FREEZE',
    'Applicable rule IDs\nExemplar IDs + exact passages\nSource references\nLedger version + hashes\n\nRetain candidate/approval status',green,11.5)
arrow([(2.08,11.4),(2.08,10.9)])

box(4.85,14.0,6.15,.65,'AUTHOR INTENT + SOURCE EVIDENCE','Bind the procedure, source, ledger and code versions.','#F3F6FA',11)
arrow([(7.93,13.9),(7.93,13.6)])

box(4.85,12.05,6.15,1.45,'1  CONSTRUCTION PROMPT',
    'Intent + source evidence\nConceptual and epistemic rules + exemplar passages\nRhetorical rules for intellectual-act purpose and order',blue,11.4)
box(11.65,12.05,3.85,1.45,'LLM RETURNS STRUCTURE',
    'Definitions and distinctions\nClaims and evidence links\nOrdered intellectual acts',blue,11.4)
arrow([(11.1,12.78),(11.55,12.78)],label='call',at=(11.33,13.06))
arrow([(13.57,11.95),(13.57,11.52),(7.93,11.52),(7.93,11.12)],label='structured output',at=(10.6,11.52))

box(4.85,9.55,6.15,1.45,'2  CONSTRUCTION REVIEW PROMPT',
    'Constructed argument + source evidence\nSame frozen conceptual / epistemic bindings\nRhetorical plan + its rules and exemplar passages',blue,11.4)
box(11.65,9.55,3.85,1.45,'LLM RETURNS FINDINGS',
    'Conceptual fidelity\nEvidence and reasoning\nIntellectual-act plan',blue,11.4)
arrow([(11.1,10.28),(11.55,10.28)],label='call',at=(11.33,10.56))
arrow([(13.57,9.45),(13.57,9.08),(7.93,9.08),(7.93,8.68)])
box(4.85,7.88,6.15,.68,'CODE GATE: CONSTRUCTION CLOSED',
    'Require current checks, exact revision and closure authority.',green,10.8)
arrow([(7.93,7.78),(7.93,7.35)])

box(4.85,5.78,6.15,1.45,'3  EXPRESSION PROMPT',
    'Closed argument + ordered intellectual acts\nSelected rhetorical and linguistic rules\nActual exemplar passages + definitions / qualifications',violet,11.4)
box(11.65,5.78,3.85,1.45,'LLM RETURNS PROSE',
    'Prose sentences\n+ sentence-to-act IDs\nOR a construction-reopen request',violet,11.3)
arrow([(11.1,6.51),(11.55,6.51)],label='call',at=(11.33,6.79))
arrow([(13.57,5.68),(13.57,5.23),(7.93,5.23),(7.93,4.82)],label='prose + act mapping',at=(10.6,5.23))

box(4.85,3.25,6.15,1.45,'4  FOUR-LAYER CHECKING PROMPT',
    'Returned prose + closed argument + sentence/act mapping\nSame selected rules and actual exemplar passages\nCheck conceptual, epistemic, rhetorical and linguistic fidelity',amber,11.2)
box(11.65,3.25,3.85,1.45,'LLM RETURNS FINDINGS',
    'Pass / fail / uncertain\nReasons + affected sentences\nCode selects the repair route',amber,11.4)
arrow([(11.1,3.98),(11.55,3.98)],label='call',at=(11.33,4.26))

# One voice-binding bus makes all four prompt inputs explicit.
bus='#50856F'
ax.plot([4.3,4.3],[3.98,12.78],color=bus,lw=1.8,linestyle='--')
arrow([(3.95,9.63),(4.3,9.63)],bus,style='--')
for y in (12.78,10.28,6.51,3.98):
    arrow([(4.3,y),(4.75,y)],bus,style='--')
ax.text(2.08,7.85,'Green dashed arrows =\nselected rules AND\nactual exemplar passages\nin the prompt.',ha='center',va='top',fontsize=12,color=bus,linespacing=1.45)
box(.3,3.25,3.55,2.65,'REPAIR INPUTS',
    'Previous exact draft\n+ exact check findings\n+ same frozen voice bindings\n\nExpression defect → edit\nReasoning defect → construct\nConceptual change → author',amber,10.8)

arrow([(13.57,3.15),(13.57,2.75),(7.93,2.75),(7.93,2.28)],label='all required checks pass',at=(10.6,2.75))
box(4.85,1.42,6.15,.73,'YOUR VALIDATION + VERSIONED RESULT',
    'Preserve the run. Record detector observations separately.',green,11)
box(11.65,.75,3.85,1.45,'FAIL OR UNCERTAIN',
    'Reopen the responsible loop.\nRepair receives the draft,\nfindings and frozen bindings.',amber,11)
arrow([(15.6,3.98),(15.87,3.98),(15.87,1.48),(15.6,1.48)],'#B87945')
ax.text(8,.27,'Target data flow. Current code coverage and remaining gaps are recorded separately; no live chapter has been run.',ha='center',va='center',fontsize=10,color='#526578')
fig.savefig(args.output,bbox_inches='tight',pad_inches=.2)
plt.close(fig)
