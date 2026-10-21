"""Explicit Windows factory; no CLI, launch on import, or app default binding."""
import ntpath

from app.access.selected_story_native import NativeStoryLaunch, NativeStoryProcessOwner
from app.access.selected_story_process import ProcessSelectedStoryProvider
from bounded_windows_job import WindowsAPI


def windows_story_process_owner(launch, *, enabled=False, cleanup_seconds=5):
    if type(launch) is not NativeStoryLaunch:
        raise ValueError('Explicit native story launch required')
    if any(not ntpath.isabs(path) or not ntpath.splitdrive(path)[0]
           for path in (launch.executable, launch.cwd)):
        raise ValueError('Explicit Windows drive or UNC paths required')
    # WindowsAPI is constructed lazily inside begin(), never on import or default
    # construction. Its verified private Job has no breakaway flags, and its root
    # is created suspended and assigned before any thread is resumed.
    return NativeStoryProcessOwner(launch, kernel_factory=WindowsAPI,
                                  enabled=enabled, cleanup_seconds=cleanup_seconds)


def windows_story_process_provider(launch, model, *, enabled=False, timeout=45, cleanup_seconds=5):
    # Reuse the explicit Windows-path check; construction remains inert.
    windows_story_process_owner(launch, cleanup_seconds=cleanup_seconds)
    return ProcessSelectedStoryProvider(launch, model, kernel_factory=WindowsAPI,
        enabled=enabled, timeout=timeout, cleanup_seconds=cleanup_seconds)
