package dev.photohouse.ota

import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import dev.photohouse.home.HomeOrigin
import dev.photohouse.home.HomeLanAddress
import dev.photohouse.home.HttpsUpdateClient
import dev.photohouse.home.UpdateOffer
import java.io.File
import java.security.MessageDigest

data class PreparedPhotoHouseUpdate(val offer: UpdateOffer, val file: File)

object PhotoHouseOta {
    private const val PHONE_PACKAGE = "dev.photohouse.connected"
    private const val TV_PACKAGE = "dev.photohouse.tv"

    suspend fun prepare(context: Context, origin: String, channel: String, lanAddress: String = ""): PreparedPhotoHouseUpdate {
        val expectedPackage = when (channel) { "phone" -> PHONE_PACKAGE; "tv" -> TV_PACKAGE; else -> error("Unsupported update channel") }
        val packageName = context.packageName
        require(packageName == expectedPackage) { "This app is not eligible for PhotoHouse updates" }
        val manager = context.packageManager
        val installed = manager.getPackageInfoCompat(packageName)
        val signer = signerSha256(installed)
        val updateOrigin = HomeOrigin.parse(origin)
        val client = if (lanAddress.isEmpty()) HttpsUpdateClient(updateOrigin)
            else HttpsUpdateClient(updateOrigin, HomeLanAddress.parse(lanAddress))
        val offer = client.check(channel, packageName, installed.longVersionCodeCompat(), signer)
        val directory = File(context.cacheDir, "updates").apply { if (!exists() && !mkdirs()) error("Update cache unavailable") }
        val file = File(directory, "$channel-${offer.sha256}.apk")
        client.download(offer, file)
        val archive = manager.getPackageArchiveInfoCompat(file.absolutePath) ?: run { file.delete(); error("Downloaded APK is invalid") }
        if (archive.packageName != packageName || archive.longVersionCodeCompat() != offer.versionCode ||
            archive.versionName != offer.versionName || signerSha256(archive) != offer.signingCertSha256 || signerSha256(archive) != signer) {
            file.delete()
            error("Downloaded APK identity does not match this installation")
        }
        return PreparedPhotoHouseUpdate(offer, file)
    }

    fun canInstall(context: Context): Boolean = context.packageManager.canRequestPackageInstalls()

    fun unknownSourcesSettings(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))

    fun installerIntent(context: Context, update: PreparedPhotoHouseUpdate): Intent {
        require(canInstall(context)) { "Allow app installs for PhotoHouse first" }
        require(update.file.isFile && update.offer.packageName == context.packageName)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.updates", update.file)
        return Intent(Intent.ACTION_INSTALL_PACKAGE).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
    }

    private fun signerSha256(info: PackageInfo): String {
        @Suppress("DEPRECATION")
        val signers = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
        require(signers != null && signers.size == 1) { "PhotoHouse update requires one current signing certificate" }
        return MessageDigest.getInstance("SHA-256").digest(signers.single().toByteArray())
            .joinToString("") { "%02x".format(it) }
    }

    @Suppress("DEPRECATION")
    private fun PackageManager.getPackageInfoCompat(packageName: String): PackageInfo =
        if (Build.VERSION.SDK_INT >= 33) getPackageInfo(packageName, PackageManager.PackageInfoFlags.of(signingFlags().toLong()))
        else getPackageInfo(packageName, signingFlags())

    @Suppress("DEPRECATION")
    private fun PackageManager.getPackageArchiveInfoCompat(path: String): PackageInfo? =
        if (Build.VERSION.SDK_INT >= 33) getPackageArchiveInfo(path, PackageManager.PackageInfoFlags.of(signingFlags().toLong()))
        else getPackageArchiveInfo(path, signingFlags())

    private fun signingFlags(): Int = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES

    private fun PackageInfo.longVersionCodeCompat(): Long =
        if (Build.VERSION.SDK_INT >= 28) longVersionCode else @Suppress("DEPRECATION") versionCode.toLong()
}
