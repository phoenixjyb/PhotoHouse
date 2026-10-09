package dev.photohouse.home

import okhttp3.Dns
import okhttp3.OkHttpClient
import java.net.InetAddress
import java.net.Proxy
import java.net.UnknownHostException

/** An explicit private-build server address, never a projector address or DNS server. */
class HomeLanAddress private constructor(internal val address: InetAddress) {
    override fun toString() = "HomeLanAddress([configured])"
    companion object {
        fun parse(raw: String): HomeLanAddress {
            val parts = raw.split('.')
            require(parts.size == 4 && parts.all { it.matches(Regex("0|[1-9][0-9]{0,2}")) })
            val numbers = parts.map { it.toInt() }
            require(numbers.all { it in 0..255 })
            require(numbers[0] == 10 || numbers[0] == 172 && numbers[1] in 16..31 || numbers[0] == 192 && numbers[1] == 168)
            // Numeric bytes only: parsing never consults DNS or the network.
            return HomeLanAddress(InetAddress.getByAddress(numbers.map { it.toByte() }.toByteArray()))
        }
    }
}

/** Only this PhotoHouse hostname is mapped. No public-DNS or alternate-host fallback. */
internal class HomeLanDns(private val hostname: String, private val address: InetAddress) : Dns {
    override fun lookup(hostname: String): List<InetAddress> {
        if (hostname != this.hostname) throw UnknownHostException("Host outside configured home feed")
        return listOf(address)
    }
    override fun toString() = "HomeLanDns([configured])"
}

internal fun homeLanClient(origin: HomeOrigin, address: HomeLanAddress): OkHttpClient =
    OkHttpClient.Builder().dns(HomeLanDns(origin.url.host, address.address))
        // A proxy could resolve the hostname itself and defeat the explicit LAN mapping.
        .proxy(Proxy.NO_PROXY).build()
