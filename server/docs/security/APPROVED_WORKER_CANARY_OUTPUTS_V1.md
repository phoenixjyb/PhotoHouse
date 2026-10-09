# Approved worker canary output verification

The native canary uses a disposable 96 by 64 image and a generated two-second
128 by 72 video at five frames per second. It never opens family originals or
the production database. An explicit schema selector supports a0 and b1; a0
remains the default and the selector does not migrate a database.

Success requires finished thumbnail, perceptual-hash, probe and keyframe tasks,
the expected caption/video-embedding queue entries and a 16-digit hexadecimal
perceptual hash. Both 256 and 1024 thumbnail variants must be nonempty bounded
JPEGs that fully decode within their dimension limits. Every keyframe must pass
the same JPEG check, with one to 32 frames. Symlinks, wrong image formats,
missing files, truncated images and oversized dimensions fail qualification.
The video probe must match the generated source dimensions, duration and fps.

The success receipt reports decoded thumbnail dimensions and keyframe count.
It qualifies these synthetic worker lanes, not the existing family library,
playback publication, inference workers, native ASR or the SYSTEM task identity.

Local driver and package checks on October 5 passed ten tests and thirteen
subtests. Processes and media worker execution are mocked in that check; generated
JPEG fixtures exercise actual decoding. Corrupt or missing output, bad hashes,
wrong probe metadata and image-format/dimension/link failures are negative cases.
Windows execution remains a separate operation and acceptance gate.
