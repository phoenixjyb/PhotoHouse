"""Pure projections into existing HTTP provider settings, never activation.

No environment, storage, provider, runtime or model is inspected here. Resource
declarations other than the request timeout require separate runtime qualification.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model_deployment import _validated_snapshot

TARGET_ROLES = {
    'assistant': ('assistant_asr', 'assistant_tts'),
    'memory-contributions': ('memory_asr', 'annotation_polish'),
    'memory-narrative': ('narrative',),
}
FIELDS = {
    'assistant_asr': ('assistant_asr_url', 'assistant_asr_model', 'assistant_asr_token', 'assistant_asr_timeout_seconds'),
    'assistant_tts': ('assistant_tts_url', None, 'assistant_tts_token', 'assistant_tts_timeout_seconds'),
    'memory_asr': ('asr_url', 'asr_model', 'asr_token', 'asr_timeout_seconds'),
    'annotation_polish': ('ollama_url', 'ollama_model', None, 'ollama_timeout_seconds'),
    'narrative': ('ollama_url', 'ollama_model', None, 'ollama_timeout_seconds'),
}


class ModelBindingError(ValueError):
    """Fixed refusal reason; no private configuration or credential values."""


def _fail(reason):
    raise ModelBindingError(reason)


@dataclass(frozen=True, repr=False)
class ProviderBinding:
    role: str
    endpoint: str
    model: str | None
    credential_env: str | None
    request_timeout_seconds: int


def _credential(reference, values):
    if reference is None:
        return None
    if type(values) is not dict:
        _fail('credential_values_required')
    token = values.get(reference)
    if (type(token) is not str or not token or
            any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 or 0xd800 <= ord(c) <= 0xdfff for c in token)
            or len(token.encode('utf-8')) > 4096):
        _fail('credential_value_invalid')
    return token


@dataclass(frozen=True, repr=False)
class ConfigurationProjection:
    target: str
    selection: str
    selection_sha256: str
    providers: tuple[ProviderBinding, ...]
    disabled_roles: tuple[str, ...]

    def report(self):
        return {'status': 'projection_valid', 'target': self.target, 'selection': self.selection,
                'selection_sha256': self.selection_sha256,
                'projected_roles': [provider.role for provider in self.providers],
                'disabled_roles': list(self.disabled_roles),
                'request_timeouts_seconds': {p.role: p.request_timeout_seconds for p in self.providers},
                'credential_values_included': False, 'feature_flags_changed': False,
                'runtime_resources_enforced': False, 'runtime_probed': False,
                'artifacts_verified': False, 'quality_evaluated': False, 'activation_performed': False}

    def bind_fields(self, existing, *, credential_values=None):
        """Return a private field patch; never mutate, serialize or log its values.

        Explicit pre-existing providers must match the complete projected tuple.
        Clear the old fields deliberately before selecting a replacement.
        """
        if type(existing) is not dict:
            _fail('configuration_fields')
        for role in self.disabled_roles:
            if any(existing.get(key) is not None for key in FIELDS[role][:3] if key is not None):
                _fail('disabled_binding_configuration_conflict')
        patch = {}
        for provider in self.providers:
            url, model, token, timeout = FIELDS[provider.role]
            values = {url: provider.endpoint, timeout: provider.request_timeout_seconds}
            if model is not None:
                values[model] = provider.model
            if token is not None:
                values[token] = _credential(provider.credential_env, credential_values)
            default_timeout = 45 if self.target == 'assistant' else 30
            if existing.get(url) is not None:
                if any(existing.get(key, default_timeout if key == timeout else None) != value
                       for key, value in values.items()):
                    _fail('provider_configuration_conflict')
            else:
                if any(existing.get(key) is not None for key in (model, token) if key is not None):
                    _fail('provider_configuration_conflict')
                current_timeout = existing.get(timeout, default_timeout)
                if current_timeout not in (default_timeout, provider.request_timeout_seconds):
                    _fail('provider_configuration_conflict')
            patch.update(values)
        return patch


def project_configuration(deployment, *, target, platform, feature_enabled=False, rollback=False):
    """Prepare a target-specific immutable projection, without resolving secrets."""
    if not _validated_snapshot(deployment):
        _fail('validated_deployment_required')
    if type(target) is not str or target not in TARGET_ROLES:
        _fail('unsupported_projection_target')
    if type(platform) is not str or platform not in {'windows', 'linux', 'macos'}:
        _fail('target_platform_required')
    if type(feature_enabled) is not bool or type(rollback) is not bool:
        _fail('explicit_projection_flags')
    providers, disabled = [], []
    for role in TARGET_ROLES[target]:
        selected = deployment.resolve(role, rollback=rollback)
        if selected is None or not selected['binding']['enabled']:
            if target != 'assistant':
                _fail('required_binding_not_enabled')
            if selected is not None:
                disabled.append(role)
            continue
        if not feature_enabled:
            _fail('feature_opt_in_required')
        provider, runtime, artifact = selected['provider'], selected['runtime'], selected['artifact']
        if runtime['platform'] != platform:
            _fail('runtime_platform_mismatch')
        if provider['credential_env'] is not None and FIELDS[role][2] is None:
            _fail('credential_not_supported_by_target')
        cap = 60 if target == 'assistant' else 30
        timeout = min(cap, runtime['resources']['timeout_seconds'])
        providers.append(ProviderBinding(role, provider['endpoint'],
            None if role == 'assistant_tts' else artifact['model_name'],
            provider['credential_env'], timeout))
    if rollback and not providers:
        _fail('required_binding_not_enabled')
    return ConfigurationProjection(target, 'rollback' if rollback else 'current',
                                   deployment.selection_sha256, tuple(providers), tuple(disabled))
