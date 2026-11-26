"""Local entry point; no live calls unless explicitly requested."""
import argparse, json, os
from pathlib import Path
from model import Graph
from ingest import ingest
from faculty import Faculty
from expression import Expression
from checking import Checking
from execution import Execution
from providers import JSONModel, SuppliedResearch
from research import EuropePMC
from governance import BilateralResearch

class ResearchBridge:
    def __init__(self, provider, support, challenge):
        self.provider=provider; self.support=support; self.challenge=challenge; self.report=None
    def search(self, intent):
        self.report=BilateralResearch(self.provider).investigate(intent,self.support,self.challenge)
        if any(a['status']!='retrieved' for a in self.report['attempts']):
            raise RuntimeError('Bilateral retrieval incomplete')
        return [dict(text=r['text'],source=r['source'],metadata=dict(r['metadata'],directions=r['directions'],polarity='unassessed')) for r in self.report['records']]

def execute(graph, intent, constructor, writer, reviewer, research):
    engine=Execution(graph,Faculty(graph,constructor,research),Expression(graph,writer),Checking(graph,reviewer))
    result=engine.start(intent)
    if result.get('run'):
        result['draft']=engine.e.inspect(result['run'])
    if result.get('assessment'):
        result['review']=engine.c.inspect(result['assessment'])
    if getattr(research,'report',None) is not None:
        result['research_report']=research.report
    return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('--intent',required=True); p.add_argument('--database',default='agent_run.sqlite'); p.add_argument('--ledger',default=str(Path(__file__).with_name('Authorial_Voice_Ledger_v0.4.xlsx'))); p.add_argument('--support'); p.add_argument('--challenge'); p.add_argument('--live',action='store_true'); p.add_argument('--output',default='run_report.json'); a=p.parse_args()
    if not a.live: p.error('Explicit --live required; automated tests use fixtures instead')
    if not all(os.environ.get(k) for k in ('AGENT_API_KEY','AGENT_MODEL','AGENT_ENDPOINT')): p.error('Set AGENT_API_KEY, AGENT_MODEL and AGENT_ENDPOINT locally')
    if bool(a.support)!=bool(a.challenge): p.error('Supply both research queries or neither')
    def model(role): return JSONModel(os.environ.get('AGENT_'+role+'_MODEL',os.environ['AGENT_MODEL']),os.environ['AGENT_ENDPOINT'],'AGENT_API_KEY')
    g=Graph(a.database)
    try:
        ingest(g,a.ledger)
        research=ResearchBridge(EuropePMC(),a.support,a.challenge) if a.support else SuppliedResearch()
        result=execute(g,a.intent,model('CONSTRUCTION'),model('EXPRESSION'),model('CHECKING'),research)
        Path(a.output).write_text(json.dumps(result,indent=2),encoding='utf-8'); print(result['state']); print(a.output)
    finally: g.db.close()
if __name__=='__main__': main()
