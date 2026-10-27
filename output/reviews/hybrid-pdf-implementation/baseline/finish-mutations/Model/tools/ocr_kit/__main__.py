import argparse
import json
from pathlib import Path
from .corpus import BANNER, intake, reference_sheet, ingest_checks, build_manifest, save
from .feasibility import feasibility


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser(description=BANNER)
    commands=parser.add_subparsers(dest='command',required=True)
    collect=commands.add_parser('intake');collect.add_argument('folder');collect.add_argument('--output',required=True)
    experiment=commands.add_parser('feasibility');experiment.add_argument('--intake',required=True)
    experiment.add_argument('--dpi',nargs='+',type=int,choices=[300,400],default=[300])
    experiment.add_argument('--deskew',action='store_true');experiment.add_argument('--binarize',action='store_true')
    experiment.add_argument('--output',required=True)
    check=commands.add_parser('reference-check');check.add_argument('--intake',required=True)
    check.add_argument('--sheet',required=True);check.add_argument('--ingest',action='store_true');check.add_argument('--output')
    build=commands.add_parser('build-manifest');build.add_argument('--intake',required=True)
    build.add_argument('--checks',required=True);build.add_argument('--approval',required=True);build.add_argument('--output',required=True)
    args=parser.parse_args();print(BANNER)
    if args.command=='intake':
        result=intake(args.folder);save(args.output,result)
        print(json.dumps({'samples':len(result['samples']),'gaps':result['gaps']},ensure_ascii=False))
    elif args.command=='feasibility':
        result=feasibility(load(args.intake),args.dpi,args.deskew,args.binarize);save(args.output,result)
        for sample in result['samples']:print(json.dumps(sample,ensure_ascii=False))
        print(json.dumps(result['slices'],ensure_ascii=False))
    elif args.command=='reference-check':
        if args.ingest:
            if not args.output:parser.error('--output is required when ingesting checks')
            result=ingest_checks(load(args.intake),args.sheet,args.output);print(f"Recorded {len(result['checks'])} supplied checks")
        else:
            reference_sheet(load(args.intake),args.sheet);print('Blank sheet created; no review/sign-off recorded')
    else:
        result=build_manifest(load(args.intake),load(args.checks),load(args.approval),args.output)
        print(f"Prepared {len(result['cases'])} evaluator cases; no acceptance report or signature issued")


if __name__=='__main__':
    main()
