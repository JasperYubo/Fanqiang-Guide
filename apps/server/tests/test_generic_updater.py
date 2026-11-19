"""Protect discovered adapter state and recover a real 1.3 backup layout."""
import json,unittest
from unittest.mock import patch
import test_auto_update as f
m=f.m
class GenericUpdaterTests(unittest.TestCase):
    setUp=f.TransactionTests.setUp
    def test_discovered_profiles_and_receipts_are_preserved(self):
        root=self.machine.path('/var/lib/huarun-network/provider/discovered')
        before=self.updater.snapshot(root)
        self.assertEqual(self.updater.run()['status'],'updated')
        self.assertEqual(self.updater.snapshot(root),before)
    def test_installer_corrupting_adapter_state_is_rolled_back(self):
        root=self.machine.path('/var/lib/huarun-network/provider/discovered')
        before=self.updater.snapshot(root)
        original=self.updater.runner
        def corrupt(args,**kwargs):
            result=original(args,**kwargs)
            if args[0]=='bash' and args[1]!='-n':
                self.machine.put('/var/lib/huarun-network/provider/discovered/fixture/profile.json',b'{"changed":true}',0o644)
            return result
        self.updater.runner=corrupt
        self.assertEqual(self.updater.run()['status'],'rolled_back')
        self.assertEqual(self.updater.snapshot(root),before)
    def test_interrupted_v13_manifest_recovers_old_numeric_order(self):
        self.updater.private_dir(self.updater.state_dir);self.updater.private_dir(self.updater.backup_dir)
        transaction='txn-20261118T000000Z-'+'d'*16
        with patch.object(m,'ALL_PATHS',m.V13_ALL_PATHS):folder,manifest=self.updater.backup(transaction)
        journal={'schema_version':1,'transaction':transaction,'phase':'applying',
                 'candidate':{'source_sha':'a'*40,'installer_sha256':'b'*64},'previous_state':{},
                 'timer_before':{'enabled':'enabled','active':'active'},
                 'network_timer_before':{'enabled':'not-found','active':'inactive'}}
        self.updater.atomic_json(self.updater.journal_path,journal)
        for target in m.V13_ALL_PATHS:
            if manifest['entries'][target].get('type')=='directory':
                self.machine.put(target+'/config.json',b'changed')
            else:self.machine.put(target,b'changed during interrupted upgrade',0o644)
        self.assertEqual(self.updater.run()['status'],'rolled_back')
        for target in m.V13_ALL_PATHS:
            self.assertEqual(self.updater.snapshot(self.machine.path(target)),self.original[target],target)
        self.assertFalse(self.release.calls)
if __name__=='__main__':unittest.main()
