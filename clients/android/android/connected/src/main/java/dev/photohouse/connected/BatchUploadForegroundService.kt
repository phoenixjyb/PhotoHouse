package dev.photohouse.connected

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.os.SystemClock
import dev.photohouse.connected.core.BatchUploadQueue
import dev.photohouse.connected.core.ConnectedStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.UUID

/** One process-owned store: Activity recreation cannot create a second upload owner. */
internal object PhoneUploadRuntime {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var retainedStore: ConnectedStore? = null
    private var qaOverride: ConnectedStore? = null
    private fun isEmulatorQa() = BuildConfig.APPLICATION_ID == "dev.photohouse.connected.qa" &&
        Build.HARDWARE in setOf("ranchu", "goldfish")
    internal fun qaStore(): ConnectedStore? = if (isEmulatorQa()) qaOverride else null
    internal fun installQaStore(store: ConnectedStore?) {
        check(isEmulatorQa())
        qaOverride = store
    }
    fun store(create: (CoroutineScope) -> ConnectedStore): ConnectedStore =
        retainedStore ?: create(scope).also { retainedStore = it }
}

internal enum class BatchUploadCommand { RESUME, RETRY, RETRY_BATCH }

/** Credentials/locators never enter an Intent or a notification. Tickets are memory-only. */
internal object BatchUploadForegroundRequests {
    data class Request(val store: ConnectedStore, val command: BatchUploadCommand, val target: String?, val ticket: String)
    private val pending = linkedMapOf<String, Request>()
    private val latest = java.util.IdentityHashMap<ConnectedStore, String>()
    fun take(ticket: String?) = ticket?.let(pending::remove)
    fun remove(store: ConnectedStore) { pending.entries.removeAll { it.value.store === store }; latest.remove(store) }
    fun hasPending(store: ConnectedStore) = pending.values.any { it.store === store }
    fun isLatest(store: ConnectedStore, ticket: String?) = ticket != null && latest[store] == ticket

    fun start(context: Context, store: ConnectedStore, command: BatchUploadCommand, target: String? = null): Boolean {
        if (pending.isNotEmpty() || !store.beginBackgroundBatchUploads()) return false
        val ticket = UUID.randomUUID().toString()
        pending[ticket] = Request(store, command, target, ticket)
        latest[store] = ticket
        return try {
            checkNotNull(context.applicationContext.startForegroundService(Intent(context, BatchUploadForegroundService::class.java)
                .setAction(BatchUploadForegroundService.START).putExtra(BatchUploadForegroundService.TICKET, ticket)))
            true
        } catch (_: RuntimeException) {
            pending.remove(ticket)
            latest.remove(store)
            store.endBackgroundBatchUploads()
            false
        }
    }
}

/** User-started dataSync only. Process recreation restores metadata, never execution consent. */
class BatchUploadForegroundService : Service() {
    private var owner: ConnectedStore? = null
    private var ownerTicket: String? = null
    private var monitor: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var wakeAcquiredAt = 0L
    private var startedAt = 0L
    private var currentStartId = 0
    private val notifications get() = getSystemService(NotificationManager::class.java)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        notifications.createNotificationChannel(NotificationChannel(CHANNEL, "PhotoHouse 上传", NotificationManager.IMPORTANCE_LOW)
            .apply { description = "用户开始的文件上传进度与暂停控制"; setShowBadge(false) })
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        currentStartId = startId
        if (intent?.action == PAUSE) {
            // A delivered notification command cannot override a later explicit Resume.
            val current = owner
            if (current != null && intent.getStringExtra(TICKET) == ownerTicket &&
                BatchUploadForegroundRequests.isLatest(current, ownerTicket)) finish(paused = true)
            return START_NOT_STICKY
        }
        val request = if (intent?.action == START) BatchUploadForegroundRequests.take(intent.getStringExtra(TICKET)) else null
        if (request == null) {
            if (owner == null) stopSelfResult(startId)
            return START_NOT_STICKY
        }
        if (!request.store.backgroundBatchUploadsActive()) {
            if (owner == null) stopSelfResult(startId)
            return START_NOT_STICKY
        }
        if (owner != null && owner !== request.store) {
            request.store.endBackgroundBatchUploads()
            return START_NOT_STICKY
        }
        owner = request.store
        ownerTicket = request.ticket
        try {
            val notification = notification(request.store.batchUploads)
            if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            else startForeground(NOTIFICATION, notification)
            if (startedAt == 0L) startedAt = SystemClock.elapsedRealtime()
            notifications.cancel(PAUSED_NOTIFICATION)
            renewWakeLock()
            val queue = request.store.batchUploads ?: error("Upload queue unavailable")
            when (request.command) {
                BatchUploadCommand.RESUME -> queue.resume(request.target)
                BatchUploadCommand.RETRY -> request.target?.let(queue::retry)
                BatchUploadCommand.RETRY_BATCH -> request.target?.let(queue::retryBatch)
            }
            monitor?.cancel()
            monitor = PhoneUploadRuntime.scope.launch {
                try {
                while (owner === request.store) {
                    if (!request.store.backgroundBatchUploadsActive() ||
                        SystemClock.elapsedRealtime() - startedAt >= MAX_SESSION_MILLIS) {
                        finish(paused = true)
                        break
                    }
                    if (!queue.running && !BatchUploadForegroundRequests.hasPending(request.store)) {
                        finish(paused = queue.state.value.any { it.record.status == "failed" || it.record.status == "paused" })
                        break
                    }
                    if (SystemClock.elapsedRealtime() - wakeAcquiredAt >= WAKE_RENEW_MILLIS) renewWakeLock()
                    postNotification(NOTIFICATION, notification(queue))
                    delay(1000)
                }
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (_: RuntimeException) { finish(paused = true) }
            }
        } catch (_: RuntimeException) {
            finish(paused = true)
        }
        return START_NOT_STICKY
    }

    private fun renewWakeLock() {
        val lock = wakeLock ?: getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "$packageName:batch-upload")
            .apply { setReferenceCounted(false) }.also { wakeLock = it }
        if (lock.isHeld) lock.release()
        lock.acquire(WAKE_TIMEOUT_MILLIS)
        wakeAcquiredAt = SystemClock.elapsedRealtime()
    }

    private fun notification(queue: BatchUploadQueue?): Notification {
        val records = queue?.state?.value.orEmpty()
        val sent = records.sumOf { it.sent.coerceIn(0L, it.record.bytes) }
        val total = records.sumOf { it.record.bytes }
        val complete = records.count { it.record.status == "complete" }
        val phase = queue?.activity?.value?.phase
        val text = when (phase?.name) {
            "HASHING" -> "正在校验文件 · 可锁屏继续"
            "CHECKING" -> "正在核对服务器进度 · 可锁屏继续"
            "FINALIZING" -> "正在确认服务器接收结果"
            "WAITING_RETRY" -> "正在等待重试 · 可在此暂停"
            else -> "$complete / ${records.size} 项 · ${sent / 1048576} / ${total / 1048576} MiB"
        }
        val open = PendingIntent.getActivity(this, 1, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val pause = PendingIntent.getService(this, 2, Intent(this, BatchUploadForegroundService::class.java)
            .setAction(PAUSE).putExtra(TICKET, ownerTicket)
            .setData(android.net.Uri.parse("photohouse-upload:pause/$ownerTicket")),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val generic = Notification.Builder(this, CHANNEL).setSmallIcon(R.drawable.ic_upload_notification)
            .setContentTitle("PhotoHouse 正在上传").setContentText("解锁查看进度或暂停上传").build()
        return Notification.Builder(this, CHANNEL).apply {
            if (Build.VERSION.SDK_INT >= 31) setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE)
        }.setSmallIcon(R.drawable.ic_upload_notification)
            .setContentTitle("PhotoHouse 正在上传").setContentText(text).setContentIntent(open)
            .setOnlyAlertOnce(true).setOngoing(true).setCategory(Notification.CATEGORY_PROGRESS)
            .setVisibility(Notification.VISIBILITY_PRIVATE).setPublicVersion(generic)
            .setProgress(100, if (total > 0) (sent.toDouble() / total * 100).toInt().coerceIn(0,100) else 0, total <= 0)
            .addAction(Notification.Action.Builder(R.drawable.ic_upload_notification, "暂停上传", pause).build())
            .build()
    }

    private fun finish(paused: Boolean) {
        val previous = owner
        owner = null
        ownerTicket = null
        previous?.let { BatchUploadForegroundRequests.remove(it); it.endBackgroundBatchUploads() }
        monitor?.cancel(); monitor = null
        wakeLock?.let { if (it.isHeld) it.release() }; wakeLock = null
        startedAt = 0L
        stopForeground(STOP_FOREGROUND_REMOVE)
        if (paused && previous != null && canNotify()) {
            val open = PendingIntent.getActivity(this, 1, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            postNotification(PAUSED_NOTIFICATION, Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_upload_notification).setContentTitle("PhotoHouse 上传已暂停")
                .setContentText("打开相册继续；已接收的进度会保留").setContentIntent(open)
                .setVisibility(Notification.VISIBILITY_PRIVATE).setAutoCancel(true).build())
        }
        stopSelfResult(currentStartId)
    }

    private fun canNotify() = Build.VERSION.SDK_INT < 33 ||
        checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    // The runtime guard is shared by progress and paused notifications.
    @SuppressLint("MissingPermission")
    private fun postNotification(id: Int, notification: Notification) {
        if (canNotify()) notifications.notify(id, notification)
    }

    override fun onDestroy() {
        owner?.let { BatchUploadForegroundRequests.remove(it); it.endBackgroundBatchUploads() }; owner = null
        ownerTicket = null
        monitor?.cancel(); monitor = null
        wakeLock?.let { if (it.isHeld) it.release() }; wakeLock = null
        super.onDestroy()
    }

    companion object {
        internal const val START = "dev.photohouse.connected.upload.START"
        internal const val PAUSE = "dev.photohouse.connected.upload.PAUSE"
        internal const val TICKET = "ticket"
        private const val CHANNEL = "photohouse-uploads"
        private const val NOTIFICATION = 3101
        private const val PAUSED_NOTIFICATION = 3102
        private const val WAKE_TIMEOUT_MILLIS = 10 * 60 * 1000L
        private const val WAKE_RENEW_MILLIS = 5 * 60 * 1000L
        private const val MAX_SESSION_MILLIS = 2 * 60 * 60 * 1000L
    }
}
