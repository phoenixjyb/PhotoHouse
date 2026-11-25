"""Inert shared-claim factory proof; no Windows API, storage or provider calls."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
import household_agent_factory as factory
from selected_story_service_recipe import SCHEMA, SCHEMA_V2
from app.access.host_inference_admission import HostInferenceAdmission,HostResourceProfile
from app.access.selected_story_native import NativeStoryLaunch
from app.access.selected_story_process import process_launch_digest
from app.access.agent_process import ProcessAgentDecisionProvider

class HouseholdFactoryTests(unittest.TestCase):
 def test_same_launch_exchange_capacity_and_claim_object_are_shared_without_io(self):
  exe=r'C:\Synthetic\python.exe';root=Path('/synthetic/exchange');launch=NativeStoryLaunch(exe,'a'*64,(exe,'-I','-B',r'C:\Synthetic\scripts\household_gguf_worker.py'),r'C:\Synthetic',{'PATH':r'C:\Windows\System32'})
  profile=HostResourceProfile('cpu',process_launch_digest(launch,exchange_root=root),8*1024**3,1024**3);probe=Mock(side_effect=AssertionError('capacity read'))
  host=HostInferenceAdmission(Path('/synthetic/host'),profile,capacity_probe=probe,enabled=False)
  story=SimpleNamespace(launch=launch,model='qwen-local',timeout=60,cleanup_seconds=5,host_admission=host,exchange_root=root)
  with patch.object(factory,'bind_windows_provider',return_value=story),patch.object(factory,'strict_recipe',return_value={'schema':SCHEMA_V2,'agent_model':'agent-1.5b'}),patch.object(factory,'WindowsAPI')as kernel,patch.object(host,'acquire')as acquire,patch.object(host,'set_maintenance')as maintenance:
   original,runtime=factory.bind_household_providers(b'fixture',expected_model='qwen-local',expected_launch_sha256='b'*64,expected_profile_sha256='c'*64)
  self.assertIs(original,story);self.assertIs(type(runtime.provider),ProcessAgentDecisionProvider);self.assertEqual('agent-1.5b',runtime.provider.model);self.assertIs(runtime.provider.host_admission,story.host_admission);self.assertIs(runtime.provider.launch,story.launch);self.assertEqual(runtime.provider.exchange_root,story.exchange_root);self.assertFalse(runtime.enabled);kernel.assert_not_called();probe.assert_not_called();acquire.assert_not_called();maintenance.assert_not_called()

 def test_v1_keeps_story_model_for_agent_packets(self):
  exe=r'C:\Synthetic\python.exe';root=Path('/synthetic/exchange');launch=NativeStoryLaunch(exe,'a'*64,(exe,'-I','-B',r'C:\Synthetic\scripts\household_gguf_worker.py'),r'C:\Synthetic',{'PATH':r'C:\Windows\System32'})
  profile=HostResourceProfile('cpu',process_launch_digest(launch,exchange_root=root),8*1024**3,1024**3);host=HostInferenceAdmission(Path('/synthetic/host'),profile,capacity_probe=Mock(),enabled=False)
  story=SimpleNamespace(launch=launch,model='story-4b',timeout=60,cleanup_seconds=5,host_admission=host,exchange_root=root)
  with patch.object(factory,'bind_windows_provider',return_value=story),patch.object(factory,'strict_recipe',return_value={'schema':SCHEMA,'model':'story-4b'}):
   _original,runtime=factory.bind_household_providers(b'fixture',expected_model='story-4b',expected_launch_sha256='b'*64,expected_profile_sha256='c'*64)
  self.assertEqual('story-4b',runtime.provider.model)
 def test_original_single_purpose_worker_cannot_silently_be_used_for_agent_packets(self):
  story=SimpleNamespace(launch=SimpleNamespace(argv=(r'C:\Synthetic\selected_story_gguf_worker.py',)))
  with patch.object(factory,'bind_windows_provider',return_value=story),patch.object(factory,'strict_recipe',return_value={'schema':SCHEMA,'model':'qwen-local'}),self.assertRaisesRegex(ValueError,'household worker'):factory.bind_household_providers(b'fixture',expected_model='qwen-local',expected_launch_sha256='b'*64,expected_profile_sha256='c'*64)
