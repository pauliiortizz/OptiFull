"""Cliente minimo para subir imagenes a Supabase Storage via su API REST
(sin dependencias pesadas tipo supabase-py/boto3, solo 'requests'). No-op si
no esta configurado -- el pipeline sigue funcionando guardando localmente."""
import requests


class SupabaseStorage:
    def __init__(self, url, service_key, bucket, enabled: bool) -> None:
        self.url         = (url or "").rstrip("/")
        self.service_key = service_key
        self.bucket      = bucket
        self.enabled     = bool(enabled and self.url and service_key)

    def subir(self, path: str, contenido: bytes, content_type: str) -> str:
        """Sube 'contenido' a <bucket>/<path> con el 'content_type' dado (imagenes, video, etc.), sobreescribiendo si
        ya existe, y devuelve la URL publica. None si Storage no esta habilitado o la subida falla."""
        if not self.enabled:
            return None
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        headers = {
            "Authorization": f"Bearer {self.service_key}",
            "apikey":        self.service_key,
            "Content-Type":  content_type,
            "x-upsert":      "true",
        }
        try:
            r = requests.put(endpoint, headers=headers, data=contenido, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"[Storage] Error subiendo '{path}': {e}")
            return None
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"

    def borrar(self, path: str) -> bool:
        """Borra <bucket>/<path>. True si se borro (o ya no existia)."""
        if not self.enabled:
            return False
        try:
            r = requests.delete(f"{self.url}/storage/v1/object/{self.bucket}/{path}",
                                headers={"Authorization": f"Bearer {self.service_key}", "apikey": self.service_key}, timeout=15)
            return r.status_code in (200, 204, 404)
        except Exception:
            return False

    def subir_png(self, path: str, contenido: bytes) -> str:
        """Sube 'contenido' (bytes PNG) a <bucket>/<path> y devuelve la URL publica (None si falla)."""
        return self.subir(path, contenido, "image/png")
