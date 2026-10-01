#!/usr/bin/env python3
"""Record an explicit human pilot in an existing laboratory, never in a vault."""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import uuid
import fcntl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_paths import load_lab


def report(records):
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError("Malformed pilot records")
    human = [r for r in records if r.get("actor") == "human"]
    for row in human:
        seconds = row.get("attention_seconds")
        corrections = row.get("corrections", 0)
        if (type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0
                or type(corrections) is not int or corrections < 0):
            raise ValueError("Invalid human timing or correction count")
    complete = [r for r in human if r.get("status") == "finished"]
    groups = {}
    for r in complete:
        groups.setdefault(r["pair"], {})[r["condition"]] = r
    pairs = []
    for name, arms in groups.items():
        if "baseline" in arms and "candidate" in arms:
            a, b = arms["baseline"], arms["candidate"]
            if a["attention_seconds"] > 0:
                pairs.append({"pair": name, "saved_seconds": a["attention_seconds"]-b["attention_seconds"],
                              "saved_fraction": 1-b["attention_seconds"]/a["attention_seconds"],
                              "correction_delta": b["corrections"]-a["corrections"],
                              "quality_pass": a["quality"] == b["quality"] == "pass",
                              "human_useful": b["useful"]})
    failure = any(r.get("quality") == "critical_failure" for r in human)
    dates = []
    for row in human:
        try:
            stamp = dt.datetime.fromisoformat(row["started_at"])
            if stamp.tzinfo is None:
                raise ValueError("Timezone required")
            dates.append(stamp)
        except (KeyError, ValueError, TypeError):
            pass
    session_count = len({r["session"] for r in human if r.get("session")})
    duration_days = ((max(dates)-min(dates)).total_seconds()/86400
                     if dates and len(dates) == len(human) else None)
    checks = {
        "minimum_eight_pairs": len(pairs) >= 8,
        "all_attempts_paired_and_finished": bool(human) and len(pairs)*2 == len(human) == len(complete),
        "minimum_four_sessions": session_count >= 4,
        "within_fourteen_days": duration_days is not None and duration_days <= 14,
        "all_attempts_quality_pass": bool(human) and all(r.get("quality") == "pass" for r in human),
        "no_critical_failure": not failure,
        "median_savings_sixty_seconds": bool(pairs) and statistics.median(p["saved_seconds"] for p in pairs) >= 60,
        "median_reduction_twenty_percent": bool(pairs) and statistics.median(p["saved_fraction"] for p in pairs) >= .2,
        "three_quarters_nonworse": bool(pairs) and sum(p["saved_seconds"] >= 0 for p in pairs)/len(pairs) >= .75,
        "corrections_not_increased": bool(pairs) and statistics.median(p["correction_delta"] for p in pairs) <= 0,
    }
    return {"evidence": "human_observations" if human else "not_observed", "record_count": len(records),
            "completed_human_attempts": len(complete), "abandoned_human_attempts": sum(r.get("status") == "abandoned" for r in human),
            "pairs": pairs, "session_count": session_count, "duration_days": duration_days, "checks": checks,
            "attention_quality_gate": "fail" if failure else "pass" if all(checks.values()) else "inconclusive_or_not_met",
            "promotion": "not_decided", "maintenance_budget": "not_observed",
            "note": "Timing is operator-controlled. Assess maintenance, case coverage and explicit human feedback before any promotion."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lab",required=True,type=Path)
    s=p.add_subparsers(dest="command",required=True)
    start=s.add_parser("start");start.add_argument("--pair",required=True);start.add_argument("--condition",choices=["baseline","candidate"],required=True);start.add_argument("--session",required=True);start.add_argument("--actor",choices=["human","simulation"],required=True)
    for name in ("pause","resume","finish","abandon"):
        x=s.add_parser(name);x.add_argument("id")
        if name in ("finish","abandon"):
            x.add_argument("--quality",choices=["pass","fail","critical_failure"],required=True)
            x.add_argument("--corrections",type=int,required=True)
            x.add_argument("--useful",choices=["yes","no","unknown"],default="unknown")
    s.add_parser("report")
    args=p.parse_args()
    try:
        root,config=load_lab(args.lab)
        path=root/"human-pilot.json"
        if path.is_symlink():raise ValueError("Pilot record must not be a symlink")
        fd=os.open(root/".pilot.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            records=json.loads(path.read_text()) if path.exists() else []
            now=time.time()
            if args.command=="report":output=report(records)
            elif args.command=="start":
                if any(r["status"]=="running" for r in records):raise ValueError("Pause or finish the active measurement first")
                if any(r['pair']==args.pair and r['condition']==args.condition and r['actor']==args.actor for r in records):raise ValueError("Pair condition already attempted; preserve failure and use a new pair")
                output={"id":str(uuid.uuid4()),"pair":args.pair,"condition":args.condition,"session":args.session,"actor":args.actor,"status":"running","attention_seconds":0,"since":now,"started_at":dt.datetime.now(dt.timezone.utc).isoformat(),"useful":"unknown"};records.append(output)
            else:
                output=next((r for r in records if r['id']==args.id),None)
                if output is None:raise ValueError("Unknown measurement")
                if output['status'] not in ('running','paused'):raise ValueError("Measurement is terminal")
                if args.command=='resume' and output['status']!='paused':raise ValueError("Measurement is not paused")
                if args.command=='pause' and output['status']!='running':raise ValueError("Measurement is not running")
                if args.command=='resume' and any(r['status']=='running' for r in records):raise ValueError("Another measurement is running")
                if output['status']=='running':
                    delta=now-output['since']
                    if not math.isfinite(delta) or delta<0:raise ValueError("Clock changed; timing cannot be trusted")
                    output['attention_seconds']+=delta
                output['since']=now
                output['status']={'pause':'paused','resume':'running','finish':'finished','abandon':'abandoned'}[args.command]
                if args.command in ('finish','abandon'):
                    if args.corrections<0:raise ValueError("Corrections must be nonnegative")
                    output.update(quality=args.quality,corrections=args.corrections,useful=args.useful)
            if args.command!='report':
                temp=root/('.pilot-'+str(uuid.uuid4())+'.tmp')
                with temp.open('x') as f:json.dump(records,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
                os.replace(temp,path)
            print(json.dumps(output,indent=2,ensure_ascii=False))
            return 0
    except (ValueError,OSError,KeyError) as error:
        print(json.dumps({'error':str(error)}),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
