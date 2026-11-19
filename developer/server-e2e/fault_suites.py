"""Run the mandatory network/provider fault suites with zero skipped tests."""
import json,pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
SUITES=('test_network.py','test_ip_provider.py','test_aws_provider.py','test_egress.py','test_network_setup.py')
GENERIC_SUITES=('test_generic_provider.py','test_provider_discovery.py','test_network_discovery.py','test_generic_updater.py')

ASSISTED_SUITES=('test_provider_readiness.py',)

def main():
    loader=unittest.TestLoader();suite=unittest.TestSuite()
    assisted='--assisted' in sys.argv[1:]
    selected=SUITES + (GENERIC_SUITES if assisted or '--generic' in sys.argv[1:] else ()) + (ASSISTED_SUITES if assisted else ())
    for pattern in selected:
        tests=loader.discover(str(ROOT/'apps/server/tests'),pattern=pattern)
        if tests.countTestCases()<1:raise SystemExit('required fault suite empty: '+pattern)
        suite.addTests(tests)
    result=unittest.TextTestRunner(stream=sys.stderr,verbosity=1).run(suite)
    report={'passed':result.wasSuccessful() and not result.skipped,'tests':result.testsRun,'skipped':len(result.skipped),'suites':list(selected)}
    print(json.dumps(report,sort_keys=True))
    return 0 if report['passed'] else 1
if __name__=='__main__':sys.exit(main())
