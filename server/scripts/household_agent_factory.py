"""Explicit Windows composition: one pinned CPU recipe and claim for both profiles."""
from __future__ import annotations

from app.access.agent_local_runtime import LocalToolAgentRuntime
from app.access.agent_process import ProcessAgentDecisionProvider
from selected_story_service_recipe import build_recipe_provider as bind_windows_provider
from bounded_windows_job import WindowsAPI


def bind_household_providers(raw, *, expected_model, expected_launch_sha256,
                             expected_profile_sha256, enabled=False):
    """Build only. Operator initializes the shared claim blocked, then activates.

    Both adapters use the exact SAME native launch, private exchange parent,
    capacity proof and HostInferenceAdmission object. Model packet kind selects
    a closed input grammar, never a different executable/provider/model.
    """
    story = bind_windows_provider(raw, expected_model=expected_model,
        expected_launch_sha256=expected_launch_sha256,
        expected_profile_sha256=expected_profile_sha256, enabled=enabled)
    from pathlib import PureWindowsPath
    scripts = [part for part in story.launch.argv
               if str(part).lower().endswith('.py')]
    if len(scripts) != 1 or PureWindowsPath(scripts[0]).name != 'household_gguf_worker.py':
        raise ValueError('Explicit household worker launch required')
    decision = ProcessAgentDecisionProvider(story.launch, story.model,
        kernel_factory=WindowsAPI, enabled=enabled, timeout=story.timeout,
        cleanup_seconds=story.cleanup_seconds, host_admission=story.host_admission,
        exchange_root=story.exchange_root)
    return story, LocalToolAgentRuntime(decision, enabled=enabled)
