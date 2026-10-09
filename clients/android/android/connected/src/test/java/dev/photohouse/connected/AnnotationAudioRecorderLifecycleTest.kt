package dev.photohouse.connected

import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class AnnotationAudioRecorderLifecycleTest {
    @Test fun stopBeforeWorkerStartsPreventsCaptureAndCannotBeReset() {
        val lifecycle = RecordingLifecycle()
        lifecycle.stop(discard = true) {}

        assertFalse(lifecycle.claim())
        assertFalse(lifecycle.isRunning)
        assertTrue(lifecycle.wasDiscarded)
    }

    @Test fun oneCaptureCannotStartTwiceAndStopIsTerminal() {
        val lifecycle = RecordingLifecycle()
        assertTrue(lifecycle.claim())
        assertFalse(lifecycle.claim())
        lifecycle.stop(discard = false) {}

        assertFalse(lifecycle.isRunning)
        assertFalse(lifecycle.claim())
    }

    @Test fun recorderRejectsOverlappingCapturesUntilCurrentCaptureIsReleased() {
        val recorder = AnnotationAudioRecorder()
        val first = recorder.beginCapture()

        assertThrows(IllegalStateException::class.java) { recorder.beginCapture() }
        first.discard()
        assertTrue(first.wasDiscarded)
        recorder.beginCapture().discard()
    }

    @Test fun discardAfterCaptureFinishesButBeforeUploadConsumeRejectsWav() {
        val lifecycle = RecordingLifecycle()
        assertTrue(lifecycle.claim())
        assertTrue(lifecycle.start {})
        lifecycle.finish()

        lifecycle.stop(discard = true) {}

        assertTrue(lifecycle.wasDiscarded)
        assertFalse(lifecycle.consumeForUpload())
    }

    @Test fun uploadConsumeClosesTheDiscardWindow() {
        val lifecycle = RecordingLifecycle()
        assertTrue(lifecycle.claim())
        assertTrue(lifecycle.start {})
        lifecycle.finish()
        assertTrue(lifecycle.consumeForUpload())

        lifecycle.stop(discard = true) {}

        assertFalse(lifecycle.wasDiscarded)
        assertFalse(lifecycle.consumeForUpload())
    }
}
