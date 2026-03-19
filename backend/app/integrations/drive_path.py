import re
from urllib.parse import parse_qs, urlparse


FOLDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def resolve_drive_folder_id(folder_input: str) -> str:
    value = folder_input.strip()
    if not value:
        raise ValueError("Folder input is empty")

    if FOLDER_ID_PATTERN.match(value):
        return value

    parsed = urlparse(value)

    path_parts = [part for part in parsed.path.split("/") if part]
    if "folders" in path_parts:
        index = path_parts.index("folders")
        if index + 1 < len(path_parts):
            folder_id = path_parts[index + 1]
            if FOLDER_ID_PATTERN.match(folder_id):
                return folder_id

    query_params = parse_qs(parsed.query)
    if "id" in query_params and query_params["id"]:
        folder_id = query_params["id"][0]
        if FOLDER_ID_PATTERN.match(folder_id):
            return folder_id

    raise ValueError("Could not extract a valid Google Drive folder ID from input")
