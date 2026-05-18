from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from onvif import ONVIFCamera


class OnvifService:
    def resolve_stream_uri(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        profile_token: str | None = None,
    ) -> dict:
        try:
            camera = ONVIFCamera(host, port, username, password)
            device = camera.devicemgmt
            info = device.GetDeviceInformation()
            media = camera.create_media_service()
            profiles = media.GetProfiles()
            profile = next((item for item in profiles if item.token == profile_token), profiles[0])

            request = media.create_type("GetStreamUri")
            request.StreamSetup = {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}
            request.ProfileToken = profile.token
            uri = media.GetStreamUri(request).Uri

            return {
                "manufacturer": getattr(info, "Manufacturer", ""),
                "model": getattr(info, "Model", ""),
                "serial_number": getattr(info, "SerialNumber", ""),
                "profile_token": profile.token,
                "profile_name": getattr(profile, "Name", profile.token),
                "rtsp_url": uri,
            }
        except Exception as exc:  # pragma: no cover - depends on network device
            raise RuntimeError(f"failed to resolve ONVIF stream: {exc}") from exc

    @staticmethod
    def build_authenticated_rtsp_url(url: str, username: str, password: str) -> str:
        parsed = urlparse(url)
        netloc = parsed.netloc
        if "@" in netloc or not username:
            return url

        credentials = username
        if password:
            credentials += f":{password}"
        netloc = f"{credentials}@{netloc}"
        return urlunparse(parsed._replace(netloc=netloc))

    @staticmethod
    def mask_rtsp_url(url: str | None) -> str | None:
        if not url:
            return url

        parsed = urlparse(url)
        if "@" not in parsed.netloc:
            return url

        _, host = parsed.netloc.rsplit("@", 1)
        return urlunparse(parsed._replace(netloc=f"***:***@{host}"))


onvif_service = OnvifService()
