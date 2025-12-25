#!/usr/bin/env python3
"""
DCC Manager for Access IRC
Handles DCC (Direct Client-to-Client) file transfers
"""

import os
import socket
import struct
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Callable, List, Any

from gi.repository import GLib


class DCCTransferState(Enum):
    """State of a DCC transfer"""
    PENDING = "pending"          # Waiting for user acceptance
    CONNECTING = "connecting"    # Establishing connection
    TRANSFERRING = "transferring"  # Active transfer
    COMPLETED = "completed"      # Successfully completed
    FAILED = "failed"            # Failed with error
    CANCELLED = "cancelled"      # Cancelled by user


class DCCTransferDirection(Enum):
    """Direction of DCC transfer"""
    SEND = "send"
    RECEIVE = "receive"


@dataclass
class DCCTransfer:
    """Represents a DCC file transfer"""
    id: str                         # Unique transfer ID
    server: str                     # IRC server name
    nick: str                       # Remote user's nickname
    filename: str                   # Name of file
    filepath: str                   # Local path to file
    filesize: int                   # Size in bytes
    direction: DCCTransferDirection  # Send or receive
    state: DCCTransferState = DCCTransferState.PENDING
    bytes_transferred: int = 0      # Progress tracking
    ip: str = ""                    # Remote IP (for receives)
    port: int = 0                   # Port number
    error_message: str = ""         # Error description if failed
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    sock: Optional[socket.socket] = field(default=None, repr=False)
    thread: Optional[threading.Thread] = field(default=None, repr=False)
    cancelled: bool = False         # Flag to signal cancellation

    @property
    def progress_percent(self) -> float:
        """Get transfer progress as percentage"""
        if self.filesize == 0:
            return 0.0
        return (self.bytes_transferred / self.filesize) * 100

    @property
    def speed_bytes_per_second(self) -> float:
        """Calculate current transfer speed"""
        if self.start_time is None:
            return 0.0
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed == 0:
            return 0.0
        return self.bytes_transferred / elapsed


class DCCManager:
    """Manages DCC file transfers"""

    # DCC protocol constants
    DCC_BLOCK_SIZE = 8192  # Size of transfer blocks
    DCC_TIMEOUT = 60       # Connection timeout in seconds

    def __init__(self, config_manager, callbacks: Dict[str, Callable]):
        """
        Initialize DCC manager

        Args:
            config_manager: ConfigManager instance for settings
            callbacks: Dict of callback functions for DCC events:
                - on_dcc_offer: (transfer: DCCTransfer) -> None
                - on_dcc_progress: (transfer: DCCTransfer) -> None
                - on_dcc_complete: (transfer: DCCTransfer) -> None
                - on_dcc_failed: (transfer: DCCTransfer) -> None
                - on_dcc_system_message: (server: str, message: str) -> None
        """
        self.config = config_manager
        self.callbacks = callbacks
        self.transfers: Dict[str, DCCTransfer] = {}
        self._transfer_lock = threading.Lock()
        self._next_id = 1

        # Listening sockets for sending files
        self._listen_sockets: Dict[str, socket.socket] = {}

    def _generate_transfer_id(self) -> str:
        """Generate unique transfer ID"""
        transfer_id = f"dcc_{self._next_id}"
        self._next_id += 1
        return transfer_id

    def _call_callback(self, callback_name: str, *args) -> bool:
        """
        Call a callback on the GTK main thread

        Returns:
            False (for GLib.idle_add)
        """
        callback = self.callbacks.get(callback_name)
        if callback:
            try:
                callback(*args)
            except Exception as e:
                print(f"DCC callback error ({callback_name}): {e}")
        return False

    def _ip_to_long(self, ip: str) -> int:
        """Convert IP address string to long integer (DCC format)"""
        return struct.unpack("!L", socket.inet_aton(ip))[0]

    def _long_to_ip(self, ip_long: int) -> str:
        """Convert long integer to IP address string"""
        return socket.inet_ntoa(struct.pack("!L", ip_long))

    def _get_local_ip(self) -> str:
        """Get local IP address for DCC"""
        # First check for configured external IP (for NAT)
        external_ip = self.config.get_dcc_external_ip()
        if external_ip:
            return external_ip

        # Try to determine local IP by connecting to a public address
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _find_available_port(self) -> Optional[int]:
        """Find an available port in the configured range"""
        port_start, port_end = self.config.get_dcc_port_range()

        for port in range(port_start, port_end + 1):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("0.0.0.0", port))
                s.close()
                return port
            except OSError:
                continue

        return None

    def parse_dcc_ctcp(self, server: str, sender: str, message: str) -> Optional[DCCTransfer]:
        """
        Parse a DCC CTCP message and create a transfer offer

        Args:
            server: Server name
            sender: Sender nickname
            message: CTCP message content (without \\x01 wrappers)

        Returns:
            DCCTransfer object if valid DCC SEND, None otherwise
        """
        # DCC SEND format: DCC SEND filename ip port filesize
        # Example: DCC SEND "my file.txt" 3232235777 5000 12345

        if not message.upper().startswith("DCC SEND "):
            return None

        parts = message[9:].strip()

        # Handle quoted filename
        if parts.startswith('"'):
            end_quote = parts.find('"', 1)
            if end_quote == -1:
                return None
            filename = parts[1:end_quote]
            rest = parts[end_quote + 1:].strip().split()
        else:
            parts_split = parts.split()
            if len(parts_split) < 4:
                return None
            filename = parts_split[0]
            rest = parts_split[1:]

        if len(rest) < 3:
            return None

        try:
            ip_long = int(rest[0])
            port = int(rest[1])
            filesize = int(rest[2])
        except ValueError:
            return None

        # Convert IP
        try:
            ip = self._long_to_ip(ip_long)
        except Exception:
            return None

        # Determine download path
        download_dir = self.config.get_dcc_download_directory()
        if not download_dir:
            download_dir = str(Path.home() / "Downloads")

        # Sanitize filename
        safe_filename = self._sanitize_filename(filename)
        filepath = str(Path(download_dir) / safe_filename)

        # Handle filename collisions
        filepath = self._get_unique_filepath(filepath)

        transfer = DCCTransfer(
            id=self._generate_transfer_id(),
            server=server,
            nick=sender,
            filename=filename,
            filepath=filepath,
            filesize=filesize,
            direction=DCCTransferDirection.RECEIVE,
            ip=ip,
            port=port
        )

        with self._transfer_lock:
            self.transfers[transfer.id] = transfer

        return transfer

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe filesystem use"""
        # Remove path separators and null bytes
        safe = filename.replace("\x00", "").replace("/", "_").replace("\\", "_")
        safe = safe.replace("..", "_")

        # Remove other problematic characters
        for char in [':', '*', '?', '"', '<', '>', '|']:
            safe = safe.replace(char, "_")

        # Ensure not empty
        if not safe.strip():
            safe = "unnamed_file"

        # Limit length
        if len(safe) > 200:
            safe = safe[:200]

        return safe

    def _get_unique_filepath(self, filepath: str) -> str:
        """Get unique filepath, adding numbers if file exists"""
        if not os.path.exists(filepath):
            return filepath

        base, ext = os.path.splitext(filepath)
        counter = 1

        while os.path.exists(f"{base}_{counter}{ext}"):
            counter += 1

        return f"{base}_{counter}{ext}"

    def accept_transfer(self, transfer_id: str) -> bool:
        """
        Accept an incoming DCC transfer

        Args:
            transfer_id: ID of transfer to accept

        Returns:
            True if accepted and started, False otherwise
        """
        with self._transfer_lock:
            transfer = self.transfers.get(transfer_id)
            if not transfer or transfer.state != DCCTransferState.PENDING:
                return False

            transfer.state = DCCTransferState.CONNECTING

        # Start receive in background thread
        thread = threading.Thread(
            target=self._receive_file_thread,
            args=(transfer_id,),
            daemon=True
        )
        transfer.thread = thread
        thread.start()

        return True

    def reject_transfer(self, transfer_id: str) -> bool:
        """
        Reject an incoming DCC transfer

        Args:
            transfer_id: ID of transfer to reject

        Returns:
            True if rejected, False otherwise
        """
        with self._transfer_lock:
            transfer = self.transfers.get(transfer_id)
            if not transfer or transfer.state != DCCTransferState.PENDING:
                return False

            transfer.state = DCCTransferState.CANCELLED
            del self.transfers[transfer_id]

        return True

    def cancel_transfer(self, transfer_id: str) -> bool:
        """
        Cancel an active DCC transfer

        Args:
            transfer_id: ID of transfer to cancel

        Returns:
            True if cancelled, False otherwise
        """
        with self._transfer_lock:
            transfer = self.transfers.get(transfer_id)
            if not transfer:
                return False

            transfer.cancelled = True
            transfer.state = DCCTransferState.CANCELLED

            # Close socket if open
            if transfer.sock:
                try:
                    transfer.sock.close()
                except Exception:
                    pass

        return True

    def _receive_file_thread(self, transfer_id: str) -> None:
        """Background thread for receiving a file"""
        with self._transfer_lock:
            transfer = self.transfers.get(transfer_id)
            if not transfer:
                return

        try:
            # Connect to sender
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.DCC_TIMEOUT)
            sock.connect((transfer.ip, transfer.port))

            transfer.sock = sock
            transfer.state = DCCTransferState.TRANSFERRING
            transfer.start_time = datetime.now()

            # Ensure download directory exists
            os.makedirs(os.path.dirname(transfer.filepath), exist_ok=True)

            # Receive file
            with open(transfer.filepath, 'wb') as f:
                while transfer.bytes_transferred < transfer.filesize and not transfer.cancelled:
                    remaining = transfer.filesize - transfer.bytes_transferred
                    chunk_size = min(self.DCC_BLOCK_SIZE, remaining)

                    data = sock.recv(chunk_size)
                    if not data:
                        break

                    f.write(data)
                    transfer.bytes_transferred += len(data)

                    # Send DCC acknowledgment (32-bit byte count)
                    ack = struct.pack("!L", transfer.bytes_transferred & 0xFFFFFFFF)
                    sock.send(ack)

                    # Progress callback (throttled)
                    if transfer.bytes_transferred % (self.DCC_BLOCK_SIZE * 10) == 0:
                        GLib.idle_add(self._call_callback, "on_dcc_progress", transfer)

            sock.close()
            transfer.sock = None
            transfer.end_time = datetime.now()

            if transfer.cancelled:
                transfer.state = DCCTransferState.CANCELLED
                # Clean up partial file
                try:
                    os.remove(transfer.filepath)
                except Exception:
                    pass
            elif transfer.bytes_transferred >= transfer.filesize:
                transfer.state = DCCTransferState.COMPLETED
                GLib.idle_add(self._call_callback, "on_dcc_complete", transfer)
            else:
                transfer.state = DCCTransferState.FAILED
                transfer.error_message = "Transfer incomplete"
                GLib.idle_add(self._call_callback, "on_dcc_failed", transfer)

        except socket.timeout:
            transfer.state = DCCTransferState.FAILED
            transfer.error_message = "Connection timed out"
            GLib.idle_add(self._call_callback, "on_dcc_failed", transfer)
        except ConnectionRefusedError:
            transfer.state = DCCTransferState.FAILED
            transfer.error_message = "Connection refused"
            GLib.idle_add(self._call_callback, "on_dcc_failed", transfer)
        except Exception as e:
            transfer.state = DCCTransferState.FAILED
            transfer.error_message = str(e)
            GLib.idle_add(self._call_callback, "on_dcc_failed", transfer)

    def initiate_send(self, server: str, nick: str, filepath: str,
                      send_ctcp_callback: Callable[[str, str, str], None]) -> Optional[str]:
        """
        Initiate a DCC SEND to a user

        Args:
            server: Server name
            nick: Target nickname
            filepath: Path to file to send
            send_ctcp_callback: Callback to send CTCP message (server, nick, message)

        Returns:
            Transfer ID if initiated, None if failed
        """
        if not os.path.exists(filepath):
            return None

        filesize = os.path.getsize(filepath)
        filename = os.path.basename(filepath)

        # Find available port
        port = self._find_available_port()
        if not port:
            return None

        # Get local IP
        local_ip = self._get_local_ip()
        ip_long = self._ip_to_long(local_ip)

        transfer = DCCTransfer(
            id=self._generate_transfer_id(),
            server=server,
            nick=nick,
            filename=filename,
            filepath=filepath,
            filesize=filesize,
            direction=DCCTransferDirection.SEND,
            ip=local_ip,
            port=port
        )

        with self._transfer_lock:
            self.transfers[transfer.id] = transfer

        # Create listening socket
        try:
            listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listen_sock.bind(("0.0.0.0", port))
            listen_sock.listen(1)
            listen_sock.settimeout(self.DCC_TIMEOUT)

            self._listen_sockets[transfer.id] = listen_sock

        except Exception as e:
            transfer.state = DCCTransferState.FAILED
            transfer.error_message = f"Failed to bind port: {e}"
            return None

        # Send CTCP DCC SEND
        # Quote filename if it contains spaces
        if ' ' in filename:
            ctcp_filename = f'"{filename}"'
        else:
            ctcp_filename = filename

        ctcp_msg = f"DCC SEND {ctcp_filename} {ip_long} {port} {filesize}"
        send_ctcp_callback(server, nick, ctcp_msg)

        # Start send thread
        thread = threading.Thread(
            target=self._send_file_thread,
            args=(transfer.id,),
            daemon=True
        )
        transfer.thread = thread
        thread.start()

        return transfer.id

    def _send_file_thread(self, transfer_id: str) -> None:
        """Background thread for sending a file"""
        with self._transfer_lock:
            transfer = self.transfers.get(transfer_id)
            listen_sock = self._listen_sockets.get(transfer_id)
            if not transfer or not listen_sock:
                return

        try:
            transfer.state = DCCTransferState.CONNECTING

            # Wait for incoming connection
            conn, addr = listen_sock.accept()
            listen_sock.close()
            del self._listen_sockets[transfer_id]

            transfer.sock = conn
            transfer.state = DCCTransferState.TRANSFERRING
            transfer.start_time = datetime.now()

            # Send file
            with open(transfer.filepath, 'rb') as f:
                while transfer.bytes_transferred < transfer.filesize and not transfer.cancelled:
                    remaining = transfer.filesize - transfer.bytes_transferred
                    chunk_size = min(self.DCC_BLOCK_SIZE, remaining)

                    data = f.read(chunk_size)
                    if not data:
                        break

                    conn.send(data)
                    transfer.bytes_transferred += len(data)

                    # Progress callback (throttled)
                    if transfer.bytes_transferred % (self.DCC_BLOCK_SIZE * 10) == 0:
                        GLib.idle_add(self._call_callback, "on_dcc_progress", transfer)

            conn.close()
            transfer.sock = None
            transfer.end_time = datetime.now()

            if transfer.cancelled:
                transfer.state = DCCTransferState.CANCELLED
            elif transfer.bytes_transferred >= transfer.filesize:
                transfer.state = DCCTransferState.COMPLETED
                GLib.idle_add(self._call_callback, "on_dcc_complete", transfer)
            else:
                transfer.state = DCCTransferState.FAILED
                transfer.error_message = "Transfer incomplete"
                GLib.idle_add(self._call_callback, "on_dcc_failed", transfer)

        except socket.timeout:
            transfer.state = DCCTransferState.FAILED
            transfer.error_message = "Connection timed out (no incoming connection)"
            GLib.idle_add(self._call_callback, "on_dcc_failed", transfer)
        except Exception as e:
            transfer.state = DCCTransferState.FAILED
            transfer.error_message = str(e)
            GLib.idle_add(self._call_callback, "on_dcc_failed", transfer)

    def get_active_transfers(self) -> List[DCCTransfer]:
        """Get list of all active transfers"""
        with self._transfer_lock:
            return [t for t in self.transfers.values()
                    if t.state in (DCCTransferState.PENDING,
                                   DCCTransferState.CONNECTING,
                                   DCCTransferState.TRANSFERRING)]

    def get_transfer(self, transfer_id: str) -> Optional[DCCTransfer]:
        """Get a transfer by ID"""
        with self._transfer_lock:
            return self.transfers.get(transfer_id)

    def cleanup(self) -> None:
        """Clean up all transfers and sockets"""
        with self._transfer_lock:
            for transfer in self.transfers.values():
                transfer.cancelled = True
                if transfer.sock:
                    try:
                        transfer.sock.close()
                    except Exception:
                        pass

            for sock in self._listen_sockets.values():
                try:
                    sock.close()
                except Exception:
                    pass

            self.transfers.clear()
            self._listen_sockets.clear()
