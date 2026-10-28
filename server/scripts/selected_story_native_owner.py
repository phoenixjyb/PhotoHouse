"""Explicit Windows factory; no CLI, launch on import, or app default binding."""
import ntpath
from pathlib import Path

from app.access.host_inference_admission import HostInferenceAdmission, HostResourceProfile
from app.access.selected_story_native import NativeStoryLaunch, NativeStoryProcessOwner
from app.access.selected_story_process import ProcessSelectedStoryProvider
from app.access.windows_story_service_capacity import WindowsStoryServiceCapacityProbe
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


def windows_story_process_provider(launch, model, *, enabled=False, timeout=45, cleanup_seconds=5,
                                  host_admission=None, exchange_root=None):
    # Reuse the explicit Windows-path check; construction remains inert.
    windows_story_process_owner(launch, cleanup_seconds=cleanup_seconds)
    return ProcessSelectedStoryProvider(launch, model, kernel_factory=WindowsAPI,
        enabled=enabled, timeout=timeout, cleanup_seconds=cleanup_seconds,
        host_admission=host_admission, exchange_root=exchange_root)


def windows_story_service_provider(launch, model, *, host_directory, capacity_directory,
                                   profile, policy_id, identity, conflict_images,
                                   exchange_root, enabled=False, timeout=60, cleanup_seconds=5):
    """Compose the default-off persistent CPU service with actual capacity reads.

    Pass the provider to RuntimeConfiguration.selected_story_provider. Explicit
    operator activation/revocation uses provider.host_admission.set_maintenance;
    its legacy clearance_id argument carries policy_id, not external clearance.
    Construction never initializes storage or clears maintenance. The configured
    exact conflict images must meaningfully identify competing workloads; shared
    Python images are not disambiguated or excluded. Unknown policy stays OFF.
    """
    gib = 1024 ** 3
    if (type(launch) is not NativeStoryLaunch or type(profile) is not HostResourceProfile
            or not Path(host_directory).is_absolute() or exchange_root is None
            or launch.memory_limit > 2 * gib or launch.process_limit > 8
            or launch.minimum_free_ram < 8 * gib
            or profile.minimum_free_ram < launch.minimum_free_ram
            or type(timeout) not in (int, float) or not 0 < timeout <= 60):
        raise ValueError('Explicit bounded CPU story service configuration required')
    probe = WindowsStoryServiceCapacityProbe(profile, capacity_directory, policy_id,
        conflict_images, identity=identity, enabled=enabled)
    admission = HostInferenceAdmission(host_directory, profile, capacity_probe=probe, enabled=enabled)
    return windows_story_process_provider(launch, model, enabled=enabled, timeout=timeout,
        cleanup_seconds=cleanup_seconds, host_admission=admission, exchange_root=exchange_root)
