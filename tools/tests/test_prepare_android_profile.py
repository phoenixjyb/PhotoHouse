"""Synthetic explicit release inputs; no Gradle, signing, network or household data."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import prepare_android_profile as profile

ROOT = Path(__file__).resolve().parents[2]


def values(module):
    strings = profile.PHONE_STRINGS if module == 'phone' else profile.TV_STRINGS
    bools = profile.PHONE_BOOLEANS if module == 'phone' else profile.TV_BOOLEANS
    result = {**{k:'' for k in strings}, **{k:'false' for k in bools}}
    result['photohouseOrigin' if module == 'phone' else 'photohouseTvOrigin'] = 'https://main.synthetic.invalid'
    if module == 'tv':result['photohouseTvCatalogVersion'] = '3'
    return result


def raw(values):
    return ''.join(k+'='+v+'\n' for k,v in sorted(values.items())).encode()


def gradle(module):
    return (ROOT/'clients/android/android'/('connected' if module == 'phone' else 'tv')/'build.gradle.kts').read_text()


class AndroidProfileTests(unittest.TestCase):
    def test_both_source_contracts_have_complete_explicit_profiles(self):
        for module in ('phone','tv'):
            report = profile.validate_profile(module, raw(values(module)), gradle(module))
            self.assertGreater(report['version_code'], 0)
            self.assertEqual(set(report['property_keys']), set(values(module)))
            self.assertNotIn('routing_values', report)

    def test_duplicate_unknown_missing_and_escaped_properties_refused(self):
        data = values('phone'); normal = raw(data)
        for candidate in (normal+b'photohouseOrigin=\n', normal+b'password=secret\n',
                raw({k:v for k,v in data.items() if k!='photohouseAssistantEnabled'}),
                raw({**data,'photohouseOrigin':'https://synthetic.invalid/\\escape'}), b'\xff', b'x'*16385):
            with self.subTest(size=len(candidate)), self.assertRaises(profile.Refused):
                profile.validate_profile('phone', candidate, gradle('phone'))

    def test_route_credentials_query_paths_and_public_http_refused(self):
        for route in ('http://synthetic.invalid','https://user:pass@synthetic.invalid',
                'https://synthetic.invalid/api','https://synthetic.invalid?token=secret',
                'https://synthetic.invalid#secret','https://synthetic.invalid:0', 'https://synthetic.invalid:99999',
                'https://host%2einvalid','https://synthetic.invalid?', 'https://synthetic.invalid#'):
            with self.subTest(route=route), self.assertRaises(profile.Refused):
                profile.validate_profile('phone', raw({**values('phone'),'photohouseOrigin':route}), gradle('phone'))
        with self.assertRaises(profile.Refused):
            profile.validate_profile('phone', raw({**values('phone'),'photohousePhoneHomeOrigin':'http://192.168.50.20:8080'}), gradle('phone'))
        for route in ('http://198.51.100.2','http://127.0.0.1','http://synthetic.invalid'):
            with self.assertRaises(profile.Refused):
                profile.validate_profile('tv', raw({**values('tv'),'photohouseTvOrigin':route}), gradle('tv'))

    def test_tv_https_media_and_ota_preserve_separate_private_lan_overrides(self):
        data = {**values('tv'),'photohouseTvOrigin':'https://home.synthetic.invalid:8443',
            'photohouseTvLanAddress':'192.168.50.20',
            'photohouseTvUpdateOrigin':'https://updates.synthetic.invalid', 'photohouseTvBrowseEnabled':'true'}
        report = profile.validate_profile('tv', raw(data), gradle('tv'))
        self.assertEqual(report['routing_value_sha256']['photohouseTvOrigin'], hashlib.sha256(data['photohouseTvOrigin'].encode()).hexdigest())
        with self.assertRaises(profile.Refused):
            profile.validate_profile('tv', raw({**data,'photohouseTvUpdateOrigin':'http://192.168.50.20:8080'}), gradle('tv'))

    def test_feature_dependencies_fixture_and_catalog_refused(self):
        changes = [('phone',{'photohousePhoneUploadEnabled':'true'}),
            ('phone',{'photohousePhonePreparedBrowseEnabled':'true'}),
            ('phone',{'photohouseHomeCalendarEnabled':'true'}),
            ('phone',{'photohousePhoneUiQa':'true'}),
            ('tv',{'photohouseStoryFixtureEnabled':'true'}),
            ('tv',{'photohouseTvCatalogVersion':'1','photohouseTvDiscoveryEnabled':'true'}),
            ('tv',{'photohouseTvCatalogVersion':'2','photohouseTvBrowseEnabled':'true'}),
            ('phone',{'photohousePhoneHomeLanAddress':'192.168.50.20'}),
            ('tv',{'photohouseTvLanAddress':'999.999.999.999','photohouseTvOrigin':'https://synthetic.invalid'})]
        for module, change in changes:
            with self.subTest(module=module,keys=tuple(change)), self.assertRaises(profile.Refused):
                profile.validate_profile(module, raw({**values(module),**change}), gradle(module))

    def test_changed_source_property_contract_fails_closed(self):
        with self.assertRaises(profile.Refused):
            profile.validate_profile('phone', raw(values('phone')), gradle('phone')+'\nproviders.gradleProperty("photohouseNewSwitch")')
        with self.assertRaises(profile.Refused):
            profile.validate_profile('phone', raw(values('phone')), gradle('phone')+'\nlocalConfig.getProperty("photohouseHiddenLocalSwitch")')

    def test_release_requires_main_origin_and_enabled_home_origin(self):
        for module, key in (('phone','photohouseOrigin'),('tv','photohouseTvOrigin')):
            with self.assertRaises(profile.Refused):profile.validate_profile(module,raw({**values(module),key:''}),gradle(module))
        with self.assertRaises(profile.Refused):
            profile.validate_profile('phone',raw({**values('phone'),'photohousePhoneHomeDiscoveryEnabled':'true'}),gradle('phone'))

    def test_home_origins_match_canonical_runtime_and_lan_ranges(self):
        for module, key in (('phone','photohouseOrigin'), ('phone','photohousePhoneHomeOrigin'),
                            ('tv','photohouseTvOrigin'), ('tv','photohouseTvUpdateOrigin')):
            for origin in ('https://localhost','https://192.168.50.20','https://HOME.synthetic.invalid',
                           'https://home.synthetic.invalid/','https://home.synthetic.invalid:443'):
                with self.subTest(module=module,origin=origin), self.assertRaises(profile.Refused):
                    profile.validate_profile(module, raw({**values(module),key:origin}), gradle(module))
        for module, key, origin_key in (('phone','photohousePhoneHomeLanAddress','photohousePhoneHomeOrigin'),
                ('tv','photohouseTvLanAddress','photohouseTvOrigin'), ('tv','photohouseTvUpdateLanAddress','photohouseTvUpdateOrigin')):
            for address in ('198.51.100.2','127.0.0.1','169.254.10.20','192.168.050.20'):
                with self.subTest(address=address), self.assertRaises(profile.Refused):
                    profile.validate_profile(module, raw({**values(module),key:address,origin_key:'https://home.synthetic.invalid'}), gradle(module))

    def test_oversized_source_refused_before_reading(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'build.gradle.kts';source.write_bytes(b'x'*(profile.MAX_GRADLE_BYTES+1))
            with self.assertRaises(profile.Refused):profile._read_source(source)

    def test_preparation_binds_clean_commit_profile_and_actual_gradle_blob(self):
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as temp:
            home=Path(temp); repo=home/'repo';repo.mkdir();selected=repo/'clients/android/android/connected';selected.mkdir(parents=True)
            source=selected/'build.gradle.kts';source.write_text(gradle('phone'))
            def git(*args):return subprocess.check_output(['git',*args],cwd=repo,stderr=subprocess.DEVNULL)
            git('init','-q');git('add','.');git('-c','user.name=Synthetic','-c','user.email=synthetic@example.invalid','commit','-qm','fixture')
            commit=git('rev-parse','HEAD').decode().strip()
            private=home/'private.properties';data=raw(values('phone'));private.write_bytes(data);private.chmod(0o600)
            expected=hashlib.sha256(data).hexdigest();before=source.read_bytes()
            report=profile.prepare(repo,'phone',private,commit,expected)
            self.assertEqual(report['source_commit'],commit);self.assertFalse(report['build_started'])
            self.assertEqual(source.read_bytes(),before);self.assertEqual(private.read_bytes(),data)
            with self.assertRaises(profile.Refused):profile.prepare(repo,'phone',private,commit,'a'*64)
            real_validate = profile.validate_profile
            def revoke(*args):
                result=real_validate(*args);private.chmod(0o644);return result
            with patch.object(profile,'validate_profile',side_effect=revoke), self.assertRaises((profile.Refused,ValueError)):
                profile.prepare(repo,'phone',private,commit,expected)
            private.chmod(0o600)
            # Emulate Windows stable metadata after a same-size profile rewrite.
            def rewrite(*args):
                result=real_validate(*args);private.write_bytes(data.replace(b'main.synthetic.invalid',b'evil.synthetic.invalid'));return result
            original_identity=profile.stable_stat_identity
            private_identity=original_identity(private.stat())
            def fixed_identity(info):
                actual=original_identity(info)
                return private_identity if actual[:2] == private_identity[:2] else actual
            with patch.object(profile,'validate_profile',side_effect=rewrite), patch.object(profile,'stable_stat_identity',side_effect=fixed_identity), self.assertRaises(profile.Refused):
                profile.prepare(repo,'phone',private,commit,expected)
            private.write_bytes(data)
            git('update-index','--assume-unchanged','clients/android/android/connected/build.gradle.kts')
            def alter(*args):
                result=real_validate(*args);source.write_bytes(before+b'\n// late source mutation');return result
            with patch.object(profile,'validate_profile',side_effect=alter), self.assertRaises(profile.Refused):
                profile.prepare(repo,'phone',private,commit,expected)
            source.write_bytes(before)
            git('update-index','--no-assume-unchanged','clients/android/android/connected/build.gradle.kts')
            source.write_text(source.read_text()+'\n// dirty')
            with self.assertRaises(profile.Refused):profile.prepare(repo,'phone',private,commit,expected)

    def test_cli_refusal_contains_no_profile_or_exception_values(self):
        output=io.StringIO()
        with patch.object(profile,'prepare',side_effect=ValueError('secret-password https://private.invalid')), redirect_stdout(output):
            code=profile.main(['--module','phone','--profile','/synthetic-private.properties','--commit','a'*40,'--profile-sha256','b'*64])
        self.assertEqual(code,2);self.assertEqual(json.loads(output.getvalue())['status'],'refused')
        self.assertNotIn('secret',output.getvalue());self.assertNotIn('https://',output.getvalue())


if __name__ == '__main__':unittest.main()
