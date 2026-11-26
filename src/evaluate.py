"""Run development regression cases in isolated databases; never auto-approve."""
import argparse, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def prepare(destination):
    cases=json.loads((ROOT/'evaluation_cases.json').read_text())['cases']
    destination.mkdir(parents=True,exist_ok=False)
    for case in cases:
        folder=destination/case['id']; folder.mkdir()
        (folder/'review.json').write_text(json.dumps({'case':case['id'],'criteria':[{'criterion':c,'judgment':None,'evidence':None} for c in case['criteria']], 'voice_fidelity':None,'pangram_human_percent':None,'author_approval':None},indent=2))
    return cases

def main():
    p=argparse.ArgumentParser(); p.add_argument('destination',type=Path); p.add_argument('--live',action='store_true'); a=p.parse_args()
    cases=prepare(a.destination.resolve())
    if a.live:
        for case in cases:
            folder=a.destination.resolve()/case['id']
            command=[sys.executable,str(ROOT/'run_agent.py'),'--live','--intent',case['intent'],'--database',str(folder/'graph.sqlite'),'--output',str(folder/'report.json')]
            if case.get('research'):
                command.extend(['--support',case['research']['support'],'--challenge',case['research']['challenge']])
            result=subprocess.run(command,cwd=ROOT)
            (folder/'execution.json').write_text(json.dumps({'returncode':result.returncode}))
    print('Prepared',len(cases),'cases; human review required.')
if __name__=='__main__': main()
