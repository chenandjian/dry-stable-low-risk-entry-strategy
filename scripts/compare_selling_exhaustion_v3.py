"""Read-only fixed-universe V2/V3 signal comparison; prints JSON, not returns."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strategy6.selling_exhaustion import evaluate_selling_exhaustion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=str(ROOT / 'data/cuphandle.db'))
    args = parser.parse_args()
    baseline = {}
    source = subprocess.check_output(
        ['git', 'show', 'a2da9fb:strategy6/selling_exhaustion.py'], cwd=ROOT).decode('utf-8')
    exec(compile(source, 'frozen_v2', 'exec'), baseline)
    started = time.perf_counter()
    with sqlite3.connect(Path(args.db).resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        universe = [r[0] for r in conn.execute('SELECT DISTINCT code FROM daily_ohlc ORDER BY code')]
        if len(universe) < 200:
            raise ValueError('Fixed comparison requires at least 200 stocks')
        sample = [universe[i * len(universe) // 200] for i in range(200)]
        details, targeted = [], []
        counts = dict(evaluated=0, old=0, new=0, added=0, removed=0, unchanged=0,
                      guardViolations=0, scoreChanges=0, recentImprovement=0)
        fingerprint = hashlib.sha256()
        for code in sorted(set(sample + ['600673', '000811', '002774', '688112', '001339', '688052'])):
            rows = [dict(r) for r in conn.execute(
                'SELECT date,open,high,low,close,volume FROM daily_ohlc WHERE code=? AND date<=? ORDER BY date',
                (code, '2026-09-18'))]
            fingerprint.update(json.dumps([code, rows], sort_keys=True).encode())
            for i, row in enumerate(rows):
                if row['date'] < '2026-08-24':
                    continue
                old = baseline['evaluate_selling_exhaustion'](rows[:i+1])
                new = evaluate_selling_exhaustion(rows[:i+1])
                change = ('retained' if old['matched'] and new['matched'] else
                          'added' if new['matched'] else 'removed' if old['matched'] else 'neither')
                record = dict(code=code, date=row['date'], old=old['status'], new=new['status'],
                              score=new['score'], change=change, reasons=new['failReasons'],
                              floorDistance=new['phaseMetrics'].get('floorDistanceAtr'),
                              closePath=new['metrics'].get('closeSupportPath'),
                              dailyReturn=(row['close']/rows[i-1]['close']-1)*100 if i else None)
                if code not in sample or code == '000811':
                    targeted.append(record)
                if code not in sample:
                    continue
                counts['evaluated'] += 1
                counts['old'] += old['matched']
                counts['new'] += new['matched']
                counts['added'] += change == 'added'
                counts['removed'] += change == 'removed'
                counts['unchanged'] += change == 'retained'
                counts['scoreChanges'] += old['score'] != new['score']
                if new['matched']:
                    m, p = new['metrics'], new['phaseMetrics']
                    counts['recentImprovement'] += m['closeSupportPath'] == 'RECENT_IMPROVEMENT'
                    counts['guardViolations'] += (p['floorDistanceAtr'] > 1 or p['rise3Atr'] > .5
                                                  or p['rise1Atr'] > .5 or m['newLowCount3'] > 1
                                                  or m['newLowDepthAtr3'] > .3)
                if change != 'neither':
                    details.append(record)
    print(json.dumps(dict(baseline='a2da9fb', universe=len(universe), sample=sample,
                          start='2026-08-24', end='2026-09-18', inputSha256=fingerprint.hexdigest(),
                          counts=counts, details=details, targeted=targeted,
                          seconds=round(time.perf_counter()-started, 2)), ensure_ascii=True))


if __name__ == '__main__':
    main()
