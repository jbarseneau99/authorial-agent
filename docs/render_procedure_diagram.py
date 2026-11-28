"""Render the implemented flow, separate corpora and verified API connections.

Documentation only; see system-diagram-v0.4.md for evidence and limitations.
"""
from pathlib import Path
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK='#173247'; MUTED='#536879'; LINE='#7990A1'
BLUE='#EAF2FB'; BE='#547DA5'; GREEN='#EAF5EE'; GE='#428069'
VIOLET='#F1EDFA'; VE='#8269A2'; AMBER='#FFF4E4'; AE='#B48440'; LIGHT='#F6F8FA'


def render(output, svg=None):
    plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none'})
    fig,ax=plt.subplots(figsize=(20,26.5),dpi=150)
    fig.patch.set_facecolor('white'); ax.set_position([0,0,1,1])
    ax.set_xlim(0,20); ax.set_ylim(0,26.5); ax.axis('off')
    def text(x,y,value,size=12,weight='normal',color=INK,ha='center',va='center',**kw):
        return ax.text(x,y,value,fontsize=size,fontweight=weight,color=color,ha=ha,va=va,linespacing=1.4,**kw)
    def box(x,y,w,h,title,body,fill=LIGHT,edge=LINE,ts=13.5,bs=11.5,footer=None):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.055,rounding_size=.10',lw=1.25,edgecolor=edge,facecolor=fill,zorder=3))
        text(x+w/2,y+h-.18,title,ts,'bold',va='top',zorder=4)
        text(x+w/2,y+h/2-(.04 if footer else .12),body,bs,zorder=4)
        if footer: text(x+w/2,y+.14,footer,9.1,color=MUTED,va='bottom',zorder=4)
    def arrow(points,color=LINE,dashed=False,double=False,label=None,at=None,size=10.5):
        style=(0,(4,3)) if dashed else '-'
        for a,b in zip(points[:-2],points[1:-1]): ax.plot([a[0],b[0]],[a[1],b[1]],color=color,lw=1.5,linestyle=style,zorder=2)
        ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='<|-|>' if double else '-|>',mutation_scale=13,lw=1.5,color=color,linestyle=style,zorder=2))
        if label: text(*at,label,size,color=color,zorder=5,bbox={'facecolor':'white','edgecolor':'none','pad':2.5})
    def boundary(x,y,w,h,title,fill=LIGHT,edge='#CAD5DE',dashed=False):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.06,rounding_size=.13',lw=1.15,edgecolor=edge,facecolor=fill,linestyle=(0,(5,4)) if dashed else '-',zorder=0))
        text(x+.22,y+h-.22,title,13.5,'bold',ha='left',va='top')

    text(.65,25.95,'AUTHORIAL AGENT',27,'bold',ha='left')
    text(.65,25.35,'Construct the intellectual work. Express and check one paragraph at a time.',15,color=MUTED,ha='left')
    text(19.35,25.91,'SYSTEM DIAGRAM  /  v0.4',11,'bold',MUTED,ha='right')
    text(19.35,25.49,'Connections checked 27 Nov 2026 (Toronto)',10.8,color=MUTED,ha='right')
    box(.65,23.55,9.05,1.15,'OPENAI CONNECTION VERIFIED','GPT-6.2 Astra calls have generated and checked live paragraphs.\nWriting quality is evaluated separately for each recorded run.',GREEN,GE,13.5,11.8)
    box(10.3,23.55,9.05,1.15,'PANGRAM CONNECTION VERIFIED','Pangram 4.1 has returned recorded live scan results.\nEach new paragraph reaches scanning after its four-layer checks pass.',GREEN,GE,13.5,11.8)
    text(10,23.08,'Rules and actual exemplars shape intellectual construction and written expression.\nService access, writing checks, detector observations and your approval remain separate evidence.',11.8,'bold',GE)

    boundary(.6,18.25,18.8,4.4,'VOICE PREPARATION  /  ORIGINAL EVIDENCE IS RETAINED')
    box(.95,20.62,3.95,1.17,'RAW AUTHOR INPUT','Interview answers and transcripts\nOriginal speech / writing records',BLUE,BE,12.6,11)
    box(.95,18.94,3.95,1.16,'SOURCE CORPUS','Exact original wording + source IDs\nVersions and provenance preserved',BLUE,BE,12.6,11)
    arrow([(2.925,20.56),(2.925,20.17)])
    box(5.6,19.49,3.85,1.62,'PREPARE + IMPORT LEDGER','Curated source / excerpt / rule links\nImport the frozen workbook into a graph\nImport does not approve candidate rules',BLUE,BE,12.4,10.7,'ingest.py  •  original records remain linked')
    arrow([(4.97,19.52),(5.28,19.52),(5.28,20.3),(5.53,20.3)])
    box(10.15,20.69,3.85,1.1,'RULE CORPUS','Conceptual  •  Epistemic\nRhetorical  •  Linguistic',BLUE,BE,12.6,11)
    box(10.15,18.96,3.85,1.16,'EXEMPLAR CORPUS','Exact passages + source lineage\nCandidate / validation status retained',VIOLET,VE,12.6,10.9)
    arrow([(9.52,20.3),(9.82,20.3),(9.82,21.24),(10.08,21.24)])
    arrow([(9.52,20.3),(9.82,20.3),(9.82,19.54),(10.08,19.54)])
    box(14.75,19.41,4.25,1.84,'RESOLVE EXAMPLES PER ACT','Applicable rules + exact example text\nWhat structure to model in this act\nOriginal source context + provenance\nApproved written example kept separate',GREEN,GE,12.5,11.1,'voice_resolution.py + voice_expression.py')
    arrow([(14.07,21.24),(14.4,21.24),(14.4,20.79),(14.68,20.79)],GE)
    arrow([(14.07,19.54),(14.4,19.54),(14.4,19.91),(14.68,19.91)],GE)
    text(10,18.52,'Review sees the full bound catalog; expression receives selected worked examples. Candidate rules retain their recorded status.',10.7,color=MUTED)

    arrow([(16.88,19.34),(16.88,17.99),(4.92,17.99),(4.92,9.05)],GE,True)
    for y in (15.65,13.77,10.45,9.05): arrow([(4.92,y),(5.53,y)],GE,True)
    text(2.64,17.43,'GREEN DASHED INPUTS',11.4,'bold',GE)
    text(2.64,16.77,'Rules + source-linked passages\nreach construction, review,\nexpression and checking.',11.5,color=GE)
    box(5.6,16.97,8.75,.83,'AUTHOR INTENT + SUBJECT EVIDENCE','Bind procedure, code, ledger, source revisions, providers and prompt templates.',LIGHT,LINE,12.9,10.9)
    arrow([(9.975,16.90),(9.975,16.33)])
    box(5.6,15.04,8.75,1.22,'1  CONSTRUCTION PROMPT','Conceptual + epistemic rules, with their actual exemplars,\nshape concepts, distinctions, relationships and warranted claims.',BLUE,BE,14,11.5,'faculty.py  •  form the argument; plan rhetorical purposes and order')
    arrow([(9.975,14.97),(9.975,14.45)])
    box(5.6,13.16,8.75,1.22,'2  CONSTRUCTION REVIEW PROMPT','Check how the conceptual + epistemic examples shaped the encoded work.\nReview meaning, evidence, voice bindings, omissions and criteria.',BLUE,BE,14,11.2,'faculty.py  •  binding-only defect → scoped repair + fresh review')
    arrow([(9.975,13.09),(9.975,12.65)])
    box(5.6,11.87,8.75,.72,'AUTHOR CLOSES THIS CONSTRUCTION','Current passing review + unchanged structure + explicit closure authority.',GREEN,GE,13.2,11.1)
    arrow([(9.975,11.8),(9.975,11.12)])
    boundary(5.24,4.94,9.47,6.61,'PARAGRAPH LOOP','#FBFAFD',VE,True)
    box(5.6,9.88,8.75,1.14,'3  EXPRESSION PROMPT','Rhetorical + linguistic rules, with actual exemplars for each act.\nWrite prose structured like them, preserving the closed construction.',VIOLET,VE,14,11.1,'expression.py  •  one paragraph; map sentences to acts')
    arrow([(9.975,9.81),(9.975,9.44)])
    box(5.6,8.25,8.75,1.14,'4  FOUR-LAYER CHECKING PROMPT','Exact paragraph + closed meaning + the same worked examples.\nConceptual  •  Epistemic  •  Rhetorical  •  Linguistic criteria',AMBER,AE,14,11.7,'checking.py  •  diagnosed defect + targets + repair criterion')
    arrow([(9.975,8.18),(9.975,7.73)],label='all four layers pass',at=(11.45,7.96),size=10.6)
    box(5.6,6.48,8.75,1.18,'5  PANGRAM CHECK OF THIS PARAGRAPH','Submit the exact checked text; preserve its hash, task and result.\nAt least 50 words; shorter text pauses as unscorable.',GREEN,GE,13.8,11.7,'pangram_check.py  •  poll the same saved task')
    arrow([(9.975,6.41),(9.975,6.01)])
    box(5.6,5.25,8.75,.69,'CURRENT PASS: KEEP THE PARAGRAPH','More acts → next paragraph     •     All complete → assemble',GREEN,GE,13,11.5)
    arrow([(14.42,5.6),(15.0,5.6),(15.0,11.66),(9.975,11.66),(9.975,11.08)],VE,label='next paragraph only after current pass',at=(12.28,11.66),size=10.5)
    arrow([(9.975,5.18),(9.975,4.52)],label='all paragraphs passed',at=(11.62,4.73),size=10.6)
    box(5.6,3.49,8.75,.96,'ASSEMBLE EXACT ACCEPTED PARAGRAPHS','Preserve text and order. Whole-chapter semantic checking remains pending.',BLUE,BE,13.3,11.2)
    arrow([(9.975,3.42),(9.975,3.01)])
    box(5.6,1.96,8.75,.98,'AUTHOR VALIDATION','Your judgment of voice and substance. Keep it separate from detector results.\nRecord approval against the unchanged construction, paragraphs and evidence.',GREEN,GE,13.4,11.3)

    box(15.83,14.71,3.5,3.02,'OPENAI MODEL SERVICE','GPT-6.2 Astra\n\nConstruction + review\nExpression + checking\n\nOne adapter; distinct prompts\nCredential: AGENT_API_KEY',BLUE,BE,12.5,11.2)
    ax.plot([15.48,15.48],[8.82,16.1],color=BE,lw=1.4,linestyle=(0,(3,3)),zorder=1)
    arrow([(15.48,16.1),(15.76,16.1)],BE,True,True)
    for y in (15.65,13.77,10.45,8.82): arrow([(14.42,y),(15.41,y)],BE,True,True)
    text(17.58,13.95,'Blue links = prompt + context\nout; structured JSON back.',10.7,color=BE)
    text(17.58,12.9,'The key authenticates the API.\nIt is excluded from prompts,\nconfiguration files and logs.',10.9,color=MUTED)
    box(.65,12.42,3.95,3.23,'VERSIONED RUN RECORD','Procedure + code commit\nLedger + source hashes\nProvider configuration\nExact resolved prompts\nEvery output and finding\nLoop state + repair route\nClosure authority',LIGHT,LINE,12.7,11.6,'run_binding.py  •  append-only call evidence')
    text(2.63,11.68,'Source manuscript claims may inform\nsubject evidence. AI-like manuscript\nwording is not voice evidence.',10.9,color=MUTED)
    box(.65,7.75,3.95,2.72,'TARGETED EXPRESSION REPAIR','Authorized expression defect, any layer\nPrevious exact paragraph + diagnosis\nAffected sentences and acts\nClosed meaning + the same examples\nPreserve clean text; recheck all layers',AMBER,AE,11.8,10.6,'editing.py  •  bounded attempt budget')
    arrow([(5.53,8.65),(4.67,8.65)],AE,label='expression defect',at=(5.04,8.84),size=8.9)
    arrow([(2.625,10.54),(2.625,10.89),(5.53,10.89)],AE,label='repair prompt',at=(4.06,10.9),size=9.7)
    box(.65,4.99,3.95,2.03,'STOP / REOPEN','Construction defect → construction\nEvidence gap / uncertainty → review\nIntellectual repair is not automated',AMBER,AE,12.3,10.8)
    arrow([(5.53,8.45),(5.12,8.45),(5.12,5.99),(4.67,5.99)],AE)
    text(3.0,7.37,'Other failures or uncertainty',10.1,color=AE)
    box(15.83,6.44,3.5,2.03,'PANGRAM SERVICE','Model selector: pangram-4\nConfirmed result version: 4.1\nCredential: PANGRAM_API_KEY\nPrivate scan of exact text',GREEN,GE,12.5,10.8)
    arrow([(14.42,7.07),(15.76,7.07)],GE,False,True)
    box(15.83,3.63,3.5,2.03,'DETECTOR PAUSE','Pending → poll existing task\nFlagged / error / unscorable → stop\nNo new paragraph while paused\nNo automatic detector-driven rewrite',AMBER,AE,12.4,10.5)
    arrow([(17.58,6.37),(17.58,5.73)],AE,label='no current pass',at=(17.58,6.04),size=10.2)
    text(17.58,2.66,'Detector results are observations.\nThey do not approve the argument\nor establish your authorial voice.',10.8,color=MUTED)
    text(2.625,3.99,'Existing Execution coordinates\nconstruction, paragraph progression\nand author-approval state.',11,color=MUTED)
    text(2.625,2.95,'One owning module per implemented loop.\nExternal canonical-loop integration\nremains unfinished.',10.7,color=MUTED)
    boundary(.65,.43,18.7,1.0,'CURRENT LIMITS')
    text(10,.81,'Full epistemic schema • evidence sufficiency • automatic intellectual repair • authenticated authority\nFixed sentence count during local repair • whole-chapter checking • external canonical-loop integration',11.1,color=MUTED)
    output.parent.mkdir(parents=True,exist_ok=True); fig.savefig(output,dpi=150,facecolor='white')
    if svg:
        svg.parent.mkdir(parents=True,exist_ok=True); fig.savefig(svg,facecolor='white')
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('Authorial_Agent_Four_Layer_Procedure.png'))
    parser.add_argument('--svg',type=Path,help='Optional scalable copy of the same diagram')
    args=parser.parse_args(); render(args.output,args.svg)


if __name__=='__main__': main()
