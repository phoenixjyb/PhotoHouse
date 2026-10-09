import java.security.Permission;

/** JDK 17-only test/compiler guard; never included in an Android APK. */
@SuppressWarnings("removal")
public final class NoNetwork extends SecurityManager {
    @Override public void checkPermission(Permission permission) { }
    @Override public void checkConnect(String host, int port) { throw new SecurityException("Network forbidden in readiness checks"); }
    @Override public void checkConnect(String host, int port, Object context) { checkConnect(host, port); }
    @Override public void checkListen(int port) { throw new SecurityException("Listeners forbidden in readiness checks"); }
    @Override public void checkAccept(String host, int port) { checkConnect(host, port); }
}
