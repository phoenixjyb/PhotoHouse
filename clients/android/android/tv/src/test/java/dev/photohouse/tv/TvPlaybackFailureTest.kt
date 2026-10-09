package dev.photohouse.tv

import androidx.media3.common.PlaybackException
import org.junit.Assert.assertTrue
import org.junit.Test

class TvPlaybackFailureTest {
    @Test fun media3CodesProduceSpecificBilingualDiagnostics() {
        assertTrue(TvPlaybackFailure(TvPlaybackFailure.Stage.NATIVE,
            PlaybackException.ERROR_CODE_PARSING_CONTAINER_UNSUPPORTED).message(false)
            .contains("does not support this video format"))
        assertTrue(TvPlaybackFailure(TvPlaybackFailure.Stage.NATIVE,
            PlaybackException.ERROR_CODE_DECODING_FAILED).message(true).contains("无法解码"))
        assertTrue(TvPlaybackFailure(TvPlaybackFailure.Stage.NATIVE,
            PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED).message(false)
            .contains("invalid or malformed"))
        assertTrue(TvPlaybackFailure(TvPlaybackFailure.Stage.NATIVE,
            PlaybackException.ERROR_CODE_IO_UNSPECIFIED).message(false)
            .contains("could not read"))
    }

    @Test fun legacyMediaPlayerNegativeCodesAreNotMisclassified() {
        val message = TvPlaybackFailure(TvPlaybackFailure.Stage.NATIVE, -1010, -1010).message(false)
        assertTrue(message.contains("reported a playback failure"))
    }

    @Test fun timeoutStagesKeepTheirReasonInBothLanguages() {
        assertTrue(TvPlaybackFailure(TvPlaybackFailure.Stage.SEEK_TIMEOUT).message(false).contains("seeking timed out"))
        assertTrue(TvPlaybackFailure(TvPlaybackFailure.Stage.REBUFFER_TIMEOUT).message(true).contains("缓冲超时"))
    }
}
