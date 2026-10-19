import asyncio
import json
import os
import subprocess
from pathlib import Path

import decky


class Plugin:
    def __init__(self):
        self._home = self.resolve_home()
        self._ctl_path = self._home / ".local" / "bin" / "steamos-cec-toolkitctl"

    @staticmethod
    def resolve_home() -> Path:
        # The toolkit helper lives in the home of the user the installer ran as,
        # which is not necessarily /home/deck on Arch-derived systems (CachyOS
        # Handheld Edition, plain Arch). Prefer a home that actually contains the
        # helper, then fall back to the loader user's home.
        candidates: list[Path] = []

        # 1. System config if set by installer
        conf_path = Path("/etc/steamos-cec-toolkit.conf")
        if conf_path.is_file():
            try:
                for line in conf_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("STEAMOS_CEC_USER="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            candidates.append(Path(f"/home/{val}"))
                        break
            except Exception:
                pass

        # 2. Decky loader environment variables / attributes
        decky_home = getattr(decky, "DECKY_USER_HOME", None)
        if decky_home:
            candidates.append(Path(decky_home))
        for key in ("DECKY_USER_HOME", "SUDO_USER_HOME"):
            val = os.environ.get(key, "")
            if val:
                candidates.append(Path(val))
        for key in ("DECKY_USER", "SUDO_USER"):
            val = os.environ.get(key, "")
            if val:
                candidates.append(Path(f"/home/{val}"))

        # 3. Standard SteamOS / CachyOS / Arch handheld accounts
        candidates.append(Path("/home/deck"))
        candidates.append(Path("/home/cachyos"))

        home_dir = Path("/home")
        if home_dir.is_dir():
            try:
                for entry in home_dir.iterdir():
                    if entry.is_dir():
                        candidates.append(entry)
            except Exception:
                pass

        for key in ("HOME",):
            val = os.environ.get(key, "")
            if val:
                candidates.append(Path(val))
        candidates.append(Path.home())

        for candidate in candidates:
            if (candidate / ".local/bin/steamos-cec-toolkitctl").is_file():
                return candidate
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        return Path.home()

    @staticmethod
    def resolve_uid(home: Path) -> int:
        try:
            stat_res = home.stat()
            if stat_res.st_uid != 0:
                return stat_res.st_uid
        except Exception:
            pass
        try:
            import pwd
            return pwd.getpwnam(home.name).pw_uid
        except Exception:
            pass
        return os.getuid()

    async def _run_ctl(self, *args: str) -> dict:
        target_uid = self.resolve_uid(self._home)
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not runtime_dir or runtime_dir == "/run/user/0":
            runtime_dir = f"/run/user/{target_uid}"
        dbus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        if not dbus_addr or "run/user/0" in dbus_addr:
            dbus_addr = f"unix:path={runtime_dir}/bus"

        command = [str(self._ctl_path), *args]
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(self._home),
                "PATH": f"{self._home}/.local/bin:/usr/local/bin:/usr/bin:/bin",
                "SYSTEMD_PAGER": "",
                "XDG_RUNTIME_DIR": runtime_dir,
                "DBUS_SESSION_BUS_ADDRESS": dbus_addr,
            }
        )
        env.pop("LD_LIBRARY_PATH", None)

        decky.logger.info("SteamOS CEC Toolkit running command: %s", " ".join(command))

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await process.communicate()
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        decky.logger.info(
            "SteamOS CEC Toolkit command exited rc=%s stdout=%r stderr=%r",
            process.returncode,
            stdout_text,
            stderr_text,
        )

        if process.returncode != 0 and not stdout_text:
            return {
                "ok": False,
                "error": stderr_text or f"Command failed with exit code {process.returncode}",
            }

        try:
            payload = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "error": f"Invalid toolkitctl payload: {exc}: {stdout_text[:500]}",
            }

        if process.returncode != 0:
            payload["ok"] = False
            payload.setdefault("error", stderr_text or f"Command failed with exit code {process.returncode}")
        return payload

    async def get_status(self) -> dict:
        return await self._run_ctl("status")

    async def discover_cec(self) -> dict:
        return await self._run_ctl("discover-cec")

    async def discover_audio(self) -> dict:
        return await self._run_ctl("discover-audio")

    async def discover_input(self) -> dict:
        return await self._run_ctl("discover-input")

    async def set_config(self, updates: dict) -> dict:
        return await self._run_ctl("set-config", json.dumps(updates, separators=(",", ":")))

    async def set_service(self, name: str, enabled: bool) -> dict:
        return await self._run_ctl("set-service", name, "on" if enabled else "off")

    async def set_system_service(self, name: str, enabled: bool) -> dict:
        return await self._run_ctl("set-system-service", name, "on" if enabled else "off")

    async def set_external_volume(self, enabled: bool) -> dict:
        return await self._run_ctl("set-external-volume", "on" if enabled else "off")

    async def volume_up(self) -> dict:
        return await self._run_ctl("volume", "up")

    async def volume_down(self) -> dict:
        return await self._run_ctl("volume", "down")

    async def mute(self) -> dict:
        return await self._run_ctl("volume", "mute")

    async def wake_tv(self) -> dict:
        return await self._run_ctl("wake")

    async def standby_tv(self) -> dict:
        return await self._run_ctl("standby")

    async def restart_external_volume(self) -> dict:
        return await self._run_ctl("restart-external-volume")

    async def repair_cec_permissions(self) -> dict:
        return await self._run_ctl("repair-cec-permissions")

    async def debug_cec(self, seconds: int = 3) -> dict:
        safe_seconds = max(1, min(int(seconds), 5))
        return await self._run_ctl("debug-cec", str(safe_seconds))

    async def _main(self):
        decky.logger.info("SteamOS CEC Toolkit plugin loaded")

    async def _unload(self):
        decky.logger.info("SteamOS CEC Toolkit plugin unloading")

    async def _uninstall(self):
        decky.logger.info("SteamOS CEC Toolkit plugin uninstalled")
