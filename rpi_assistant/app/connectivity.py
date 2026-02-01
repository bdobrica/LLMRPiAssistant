"""Network connectivity utilities."""
import socket
import subprocess
from typing import Optional


def check_internet_connection(host: str = "8.8.8.8", port: int = 53, timeout: int = 3) -> bool:
    """
    Check if internet connection is available by attempting to connect to a DNS server.
    
    Args:
        host: DNS server to check (default: Google DNS)
        port: Port to connect to (default: 53 for DNS)
        timeout: Connection timeout in seconds
    
    Returns:
        True if connection successful, False otherwise
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except (socket.error, socket.timeout):
        return False


def check_internet_ping(host: str = "1.1.1.1", count: int = 1, timeout: int = 2) -> bool:
    """
    Check internet connection using ping.
    
    Args:
        host: Host to ping (default: Cloudflare DNS)
        count: Number of ping packets
        timeout: Timeout in seconds
    
    Returns:
        True if ping successful, False otherwise
    """
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", str(timeout), host],
            capture_output=True,
            timeout=timeout + 1
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return False


def get_connection_status() -> dict:
    """
    Get detailed connection status.
    
    Returns:
        Dictionary with connection details
    """
    return {
        "dns_reachable": check_internet_connection("8.8.8.8", 53, timeout=2),
        "cloudflare_reachable": check_internet_connection("1.1.1.1", 53, timeout=2),
        "ping_works": check_internet_ping("1.1.1.1", count=1, timeout=2),
    }
