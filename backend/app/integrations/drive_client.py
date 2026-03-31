from dataclasses import dataclass
from datetime import datetime

from dateutil.parser import isoparse
import httpx

from app.core.config import settings


DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"


@dataclass
class DriveFile:
    file_id: str
    name: str
    modified_time: datetime | None
    size_bytes: int | None


def _escape_drive_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def resolve_folder_id_from_path(access_token: str, folder_path: str) -> str:
    raw = folder_path.strip()
    if not raw:
        raise ValueError("Folder path is empty")

    normalized = raw.replace("\\", "/")
    prefixes = [
        "/content/drive/MyDrive/",
        "content/drive/MyDrive/",
        "/MyDrive/",
        "MyDrive/",
    ]
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break

    normalized = normalized.strip("/")
    if not normalized:
        return "root"

    parts = [part.strip() for part in normalized.split("/") if part.strip()]
    parent_id = "root"
    headers = {"Authorization": f"Bearer {access_token}"}

    with httpx.Client(timeout=30) as client:
        for part in parts:
            part_escaped = _escape_drive_query_value(part)
            query = (
                f"'{parent_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and "
                f"name='{part_escaped}' and trashed=false"
            )
            params = {
                "q": query,
                "fields": "files(id,name)",
                "pageSize": 2,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            response = client.get(f"{DRIVE_API_BASE}/files", params=params, headers=headers)
            response.raise_for_status()
            files = response.json().get("files", [])
            if not files:
                raise ValueError(f"Folder segment not found in Drive path: {part}")
            parent_id = files[0]["id"]

    return parent_id


def list_txt_files(access_token: str, folder_id: str | None = None) -> list[DriveFile]:
    active_folder_id = folder_id or settings.google_drive_folder_id
    if not active_folder_id:
        raise ValueError("Missing GOOGLE_DRIVE_FOLDER_ID in environment")

    transcript_keyword = settings.transcript_filename_keyword.strip()
    query = f"'{active_folder_id}' in parents and mimeType='text/plain' and trashed=false"
    if transcript_keyword:
        query += f" and name contains '{transcript_keyword}'"

    params = {
        "q": query,
        "fields": "nextPageToken, files(id,name,modifiedTime,size)",
        "pageSize": 1000,
        "orderBy": "modifiedTime desc",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    files: list[DriveFile] = []
    
    with httpx.Client(timeout=30) as client:
        while True:
            response = client.get(f"{DRIVE_API_BASE}/files", params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

            for item in payload.get("files", []):
                modified_raw = item.get("modifiedTime")
                modified_time = isoparse(modified_raw) if modified_raw else None
                size_raw = item.get("size")
                size_bytes = int(size_raw) if size_raw is not None else None
                files.append(
                    DriveFile(
                        file_id=item["id"],
                        name=item["name"],
                        modified_time=modified_time,
                        size_bytes=size_bytes,
                    )
                )
                
            next_page_token = payload.get("nextPageToken")
            if not next_page_token:
                break
            params["pageToken"] = next_page_token

    return files


def download_text_file(access_token: str, file_id: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=30) as client:
        response = client.get(f"{DRIVE_API_BASE}/files/{file_id}", params={"alt": "media"}, headers=headers)
        response.raise_for_status()
    return response.text
