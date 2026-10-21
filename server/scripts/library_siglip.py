"""Library-worker SigLIP2 adapter for bounded, privately prepared PNG batches.

The established semantic adapter and its text identity stay byte-for-byte
unchanged. This wrapper gives library images a separate preprocessing identity
and accepts only worker-produced private RGB PNGs.
"""
from dataclasses import asdict
import copy
import hashlib
import importlib
import math
from pathlib import Path
import re
import stat
import threading

import image_embedding_receipts as receipts
import library_image_inputs as preparation
from semantic_siglip import SiglipModel
from semantic_openclip import _source_pin, _current
from app.access.semantic_encoder import JointSpaceBinding, TextVector, SemanticUnavailable
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
BATCH_SIZE = 8
PREPARED_MAX_BYTES = 16 * 1024**2
PREPARED_MAX_TOTAL_BYTES = 128 * 1024**2
DIMENSION = 768
SPACE = "siglip2-base-p16-256-3f9f96c"
MODEL_VERSION = "siglip2-3f9f96c-v1"


def _image_identity(base_image_identity, base_text_identity, recipe, wrapper_sha256,
                    preparation_sha256):
    """Derive the library image identity without changing the base text space."""
    if (base_image_identity.artifact_sha256 != base_text_identity.artifact_sha256
            or base_image_identity.vector_space_id != SPACE
            or base_text_identity.vector_space_id != SPACE
            or base_image_identity.model_version != MODEL_VERSION
            or base_text_identity.model_version != MODEL_VERSION
            or base_image_identity.dimension != DIMENSION
            or base_text_identity.dimension != DIMENSION
            or base_image_identity.normalization != "unit_l2"
            or base_text_identity.normalization != "unit_l2"):
        raise SemanticUnavailable()
    source_digests = {
        "base_image_preprocessing_sha256": base_image_identity.preprocessing_sha256,
        "base_text_preprocessing_sha256": base_text_identity.preprocessing_sha256,
        "library_wrapper_sha256": wrapper_sha256,
        "library_preparation_sha256": preparation_sha256,
    }
    image_recipe = {
        "schema": "photohouse.siglip2_library_image_recipe.v1",
        "base_image_identity": asdict(base_image_identity),
        "base_text_identity": asdict(base_text_identity),
        "preparation_recipe": copy.deepcopy(recipe),
        "source_digests": source_digests,
        "batch": {
            "size": BATCH_SIZE,
            "tail_padding": "repeat_last_input_to_fixed_size_then_discard_padding_outputs",
            "output": "float32_unit_l2_per_row",
        },
    }
    return (VectorSpaceIdentity(base_image_identity.artifact_sha256,
        receipts.recipe_sha256(image_recipe), SPACE, MODEL_VERSION, DIMENSION, "unit_l2"),
        image_recipe)


def _prepared_file(path, expected_sha256):
    """Pin and admit one private RGB PNG without consulting any original image."""
    try:
        candidate = Path(path)
        if (not candidate.is_absolute() or ".." in candidate.parts
                or type(expected_sha256) is not str or _SHA256.fullmatch(expected_sha256) is None):
            raise SemanticUnavailable()
        if candidate.resolve(strict=True) != candidate:
            raise SemanticUnavailable()
        # Reject aliases/reparse points and oversized inputs before the generic
        # receipt helper streams a digest. Prepared PNGs are capped at 16 MiB;
        # the generic checkpoint helper intentionally permits much larger files.
        for parent in reversed(candidate.parents):
            parent_info = parent.lstat()
            if stat.S_ISLNK(parent_info.st_mode) or getattr(parent_info, "st_file_attributes", 0) & 0x400:
                raise SemanticUnavailable()
        info = candidate.lstat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400
                or info.st_nlink != 1 or not 0 < info.st_size <= PREPARED_MAX_BYTES):
            raise SemanticUnavailable()
        # The private-storage helper checks ACL/permissions in addition to the
        # no-symlink regular-file checks performed by inspect_checkpoint.
        from app.access.private_storage import require_private_file
        require_private_file(candidate)
        pin = receipts.inspect_checkpoint(candidate, expected_sha256)
        if pin.stat_identity[3] != info.st_size:
            raise SemanticUnavailable()
        return pin
    except SemanticUnavailable:
        raise
    except Exception:
        raise SemanticUnavailable() from None


def _decode_prepared(pin, Image):
    """Decode only metadata-free, single-frame, already reduced RGB PNG files."""
    try:
        stream = receipts._open_pinned(Path(pin.path), pin.stat_identity)
        with stream:
            with Image.open(stream) as source:
                if (source.format != "PNG" or source.mode != "RGB"
                        or getattr(source, "n_frames", 1) != 1
                        or source.info != {} or source.getexif()):
                    raise SemanticUnavailable()
                width, height = source.size
                if (type(width) is not int or type(height) is not int
                        or not 1 <= width <= preparation.MAX_PREPARED_SIDE
                        or not 1 <= height <= preparation.MAX_PREPARED_SIDE
                        or width * height > preparation.MAX_PREPARED_SIDE ** 2):
                    raise SemanticUnavailable()
                source.load()
                image = source.copy()
                if image.mode != "RGB" or image.size != (width, height):
                    image.close()
                    raise SemanticUnavailable()
                return image
    except SemanticUnavailable:
        raise
    except Exception:
        raise SemanticUnavailable() from None


def _normalise_batch(output, torch):
    """Return deterministic finite float32 unit rows from an exact 8x768 tensor."""
    try:
        tensor = output.detach().to(device="cpu", dtype=torch.float32)
        if tuple(tensor.shape) != (BATCH_SIZE, DIMENSION):
            raise SemanticUnavailable()
        vectors = []
        for row_index in range(BATCH_SIZE):
            values = tensor[row_index].tolist()
            if (len(values) != DIMENSION
                    or any(type(value) not in (int, float) or not math.isfinite(value)
                           for value in values)):
                raise SemanticUnavailable()
            norm = math.sqrt(math.fsum(float(value) * float(value) for value in values))
            if not math.isfinite(norm) or norm <= 0:
                raise SemanticUnavailable()
            vector = tuple(float(value) / norm for value in values)
            if not all(math.isfinite(value) for value in vector):
                raise SemanticUnavailable()
            vectors.append(vector)
        return tuple(vectors)
    except SemanticUnavailable:
        raise
    except Exception:
        raise SemanticUnavailable() from None


class LibrarySiglipModel:
    """Batch-only library image adapter with the original SigLIP2 text tower."""

    @classmethod
    def load(cls, *, model_directory, artifacts, package_versions,
             preparation_source_sha256):
        try:
            if (type(preparation_source_sha256) is not str
                    or _SHA256.fullmatch(preparation_source_sha256) is None):
                raise SemanticUnavailable()
            # This explicit call performs the official model/artifact/package
            # checks and pins the untouched base image and text recipes.
            inner = SiglipModel.load(model_directory=model_directory,
                artifacts=artifacts, package_versions=package_versions)
            wrapper_pin = _source_pin(Path(__file__).resolve())
            prep_pin = _source_pin(Path(preparation.__file__).resolve())
            if prep_pin.sha256 != preparation_source_sha256:
                raise SemanticUnavailable()
            image_identity, image_recipe = _image_identity(inner.image_identity,
                inner.text_identity, preparation.PROFILE_RECIPE,
                wrapper_pin.sha256, prep_pin.sha256)
            result = cls()
            result._inner = inner
            result.image_identity = image_identity
            result.text_identity = inner.text_identity
            result._image_recipe = image_recipe
            result._wrapper_pin = wrapper_pin
            result._preparation_pin = prep_pin
            result._lock = threading.Lock()
            result._binding = None
            result.verify()
            return result
        except SemanticUnavailable:
            raise
        except Exception:
            raise SemanticUnavailable() from None

    @property
    def binding(self):
        return self._binding

    def bind(self, binding):
        if (self._binding is not None or type(binding) is not JointSpaceBinding
                or binding.image_identity != self.image_identity
                or binding.text_identity != self.text_identity):
            raise SemanticUnavailable()
        # The inner adapter receives a namespaced binding over its original
        # image identity; library-image qualification can never masquerade as
        # the established scene-image binding.
        inner_qualification = receipts.recipe_sha256({
            "schema": "photohouse.siglip2_library_inner_binding.v1",
            "outer_binding_sha256": binding.binding_sha256,
            "base_image_identity": asdict(self._inner.image_identity),
            "base_text_identity": asdict(self._inner.text_identity),
        })
        inner_binding = JointSpaceBinding(self._inner.image_identity,
            self._inner.text_identity, inner_qualification)
        self._inner.bind(inner_binding)
        self._binding = binding
        return self

    def verify(self):
        self._inner.verify()
        _current(self._wrapper_pin)
        _current(self._preparation_pin)

    def _check(self, check):
        check()
        self._inner._check(check)
        _current(self._wrapper_pin)
        _current(self._preparation_pin)

    def receipt(self):
        return copy.deepcopy({
            "schema": "photohouse.siglip2_library_recipe_receipt.v1",
            "image_identity": asdict(self.image_identity),
            "text_identity": asdict(self.text_identity),
            "base_model_receipt": self._inner.receipt(),
            "image_recipe": self._image_recipe,
            "cpu_threads": 2,
            "activation_approved": False,
            "relevance_accepted": False,
        })

    def encode_prepared_batch(self, prepared_paths_and_sha, *, check=lambda: None):
        """Encode 1..8 worker-owned PNGs, padding model work to exactly eight."""
        if (type(prepared_paths_and_sha) not in (list, tuple)
                or not 1 <= len(prepared_paths_and_sha) <= BATCH_SIZE
                or not self._lock.acquire(blocking=False)):
            raise SemanticUnavailable()
        acquired_inner = False
        images = []
        pins = []
        try:
            if not self._inner._lock.acquire(blocking=False):
                raise SemanticUnavailable()
            acquired_inner = True
            self._check(check)
            total_bytes = 0
            for entry in prepared_paths_and_sha:
                if type(entry) not in (tuple, list) or len(entry) != 2:
                    raise SemanticUnavailable()
                pin = _prepared_file(entry[0], entry[1])
                total_bytes += pin.stat_identity[3]
                if total_bytes > PREPARED_MAX_TOTAL_BYTES:
                    raise SemanticUnavailable()
                pins.append(pin)
            Image = importlib.import_module("PIL.Image")
            for pin in pins:
                images.append(_decode_prepared(pin, Image))
            self._check(check)
            # Rehash after decoding but before inference so a changed private
            # file is refused before it can affect model work. Keep the final
            # recheck too, since the file could change during inference.
            for pin in pins:
                receipts.verify_checkpoint(pin)
            h = self._inner._handle
            padded = list(images)
            padded.extend([images[-1]] * (BATCH_SIZE - len(padded)))
            pixels = h["processor"](images=padded, return_tensors="pt")["pixel_values"]
            if tuple(pixels.shape) != (BATCH_SIZE, 3, 256, 256):
                raise SemanticUnavailable()
            with h["torch"].inference_mode():
                output = h["model"].get_image_features(
                    pixel_values=pixels.to(device="cpu", dtype=h["torch"].float32))
            vectors = _normalise_batch(output, h["torch"])
            self._check(check)
            for pin in pins:
                receipts.verify_checkpoint(pin)
            return vectors[:len(pins)]
        except SemanticUnavailable:
            raise
        except Exception:
            raise SemanticUnavailable() from None
        finally:
            for image in images:
                image.close()
            if acquired_inner:
                self._inner._lock.release()
            self._lock.release()

    def encode(self, query, *, check=lambda: None):
        """Reuse the original text vector and rebind only its outer qualification."""
        if self._binding is None:
            raise SemanticUnavailable()
        self._check(check)
        text = self._inner.encode(query, check=check)
        self._check(check)
        return TextVector(self.binding.binding_sha256, text.query_sha256,
            text.vector, canonical_vector_checksum(text.vector))
