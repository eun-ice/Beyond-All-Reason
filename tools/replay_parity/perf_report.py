#!/usr/bin/env python3
"""Compare per-frame simulation time between two prepared replay runs (base vs PR) and plot them."""
import argparse,csv,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def load(directory):
    frames,sim,memf,mem,units=[],[],[],[],[]
    with (Path(directory)/'frametimes.tsv').open() as h:
        for row in csv.DictReader(h,delimiter='\t'):
            frames.append(int(row['frame']));sim.append(float(row['sim_ms']))
            if row.get('synced_lua_kb'):
                memf.append(int(row['frame']));mem.append(float(row['synced_lua_kb'])/1024);units.append(int(row['units']))
    return dict(frames=np.array(frames),sim=np.array(sim),memf=np.array(memf),mem=np.array(mem),units=np.array(units))

def rolling_median(values,window):
    r=window//2
    return np.array([np.median(values[max(0,i-r):i+r+1]) for i in range(len(values))])

def stats(run,interval,exclude):
    mask=((run['frames']-1)%interval!=0) if exclude else np.ones(len(run['frames']),bool)
    v=run['sim'][mask]
    return dict(frames=int(len(run['frames'])),mean_ms=float(v.mean()),median_ms=float(np.median(v)),p95_ms=float(np.percentile(v,95)),p99_ms=float(np.percentile(v,99)),max_ms=float(v.max()),total_s=float(v.sum()/1000),synced_lua_mb_max=float(run['mem'].max()) if len(run['mem']) else None,synced_lua_mb_end=float(run['mem'][-1]) if len(run['mem']) else None)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--label',required=True);p.add_argument('--title',default='')
    p.add_argument('--base',required=True);p.add_argument('--pr',required=True)
    p.add_argument('--base-name',default='Baseline');p.add_argument('--pr-name',default='PR #8935')
    p.add_argument('--interval',type=int,default=150);p.add_argument('--window',type=int,default=61)
    p.add_argument('--output',required=True)
    p.add_argument('--vline',action='append',default=[],help='frame:label, drawn as a vertical marker on all panels')
    a=p.parse_args()
    runs={a.base_name:load(a.base),a.pr_name:load(a.pr)}
    colors={a.base_name:'#e67e22',a.pr_name:'#2ecc71'}
    plt.style.use('dark_background')
    fig,(ax1,ax2,ax3)=plt.subplots(3,1,figsize=(16,11),sharex=True,gridspec_kw=dict(height_ratios=[3,2,1.5]))
    fig.subplots_adjust(top=0.9,hspace=0.12)
    result={}
    for name,run in runs.items():
        mask=(run['frames']-1)%a.interval!=0
        f=run['frames'][mask];v=run['sim'][mask]
        ax1.plot(f/1800,v,color=colors[name],alpha=0.18,linewidth=0.5)
        ax1.plot(f/1800,rolling_median(v,a.window),color=colors[name],linewidth=1.6,label=name)
        ax2.plot(f/1800,np.cumsum(v)/1000,color=colors[name],linewidth=1.6,label=name)
        if len(run['mem']):ax3.plot(run['memf']/1800,run['mem'],color=colors[name],linewidth=1.4,label=name)
        result[name]=stats(run,a.interval,True)
    ax1.set_ylabel('Sim frame time (ms)');ax1.set_title(f'Per-frame simulation time, {a.window}-frame rolling median (raw values faint; frames carrying the observer snapshot excluded)',fontsize=10)
    ax1.set_ylim(0,max(np.percentile(r['sim'],99.5) for r in runs.values())*1.5);ax1.grid(axis='y',alpha=0.15);ax1.legend(loc='upper left')
    ax2.set_ylabel('Cumulative sim time (s)');ax2.grid(axis='y',alpha=0.15);ax2.legend(loc='upper left')
    ax3.set_ylabel('Synced Lua (MB)');ax3.set_xlabel('Game time (minutes)');ax3.grid(axis='y',alpha=0.15)
    for spec in a.vline:
        frame,_,label=spec.partition(':')
        x=int(frame)/1800
        for ax in (ax1,ax2,ax3):
            ax.axvline(x,color='#f1c40f',linestyle='--',alpha=0.8,linewidth=1)
        ax1.text(x,ax1.get_ylim()[1]*0.97,' '+label,color='#f1c40f',va='top',fontsize=9)
    b=result[a.base_name];c=result[a.pr_name]
    sub=f"mean {b['mean_ms']:.2f} vs {c['mean_ms']:.2f} ms | p95 {b['p95_ms']:.2f} vs {c['p95_ms']:.2f} ms | total {b['total_s']:.1f} vs {c['total_s']:.1f} s"
    fig.suptitle((a.title or a.label)+'\n'+sub,fontsize=14,y=0.98)
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(out,dpi=140,facecolor=fig.get_facecolor());plt.close(fig)
    print(json.dumps(dict(label=a.label,base=str(a.base),pr=str(a.pr),stats=result,plot=str(out))))
if __name__=='__main__':main()
