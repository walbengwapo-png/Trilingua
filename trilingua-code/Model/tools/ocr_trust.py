"""Key creation and report verification. Signing is evaluator-only."""
import argparse
import json
from document.artifact_auth import generate_key, load_json
from document.report_trust import verify_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    key = commands.add_parser('keygen')
    key.add_argument('--purpose', choices=['acceptance', 'render-plan'], required=True)
    key.add_argument('--output', required=True)
    check = commands.add_parser('verify')
    check.add_argument('--report', required=True)
    check.add_argument('--key-file', required=True)
    check.add_argument('--manifest', required=True)
    args = parser.parse_args()
    if args.command == 'keygen':
        generate_key(args.output, args.purpose)
        print('Key created outside repository; restrict access to the service/evaluator owner.')
    else:
        from document.ocr_extractor import readiness
        report = load_json(args.report)
        scores = verify_report(report, args.key_file, args.manifest)
        state = readiness()
        for scope in scores:
            language, category = scope.split(' / ')
            verify_report(report, args.key_file, args.manifest, state, language, category)
        print(json.dumps({'signature_and_contract_valid': True, 'scope_scores': scores}))


if __name__ == '__main__':
    main()
