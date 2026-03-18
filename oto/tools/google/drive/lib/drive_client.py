"""Google Drive API client with caching and rate limiting support."""

import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from oto.tools.google.credentials import get_credentials, get_user_credentials, list_accounts


class DriveClientError(Exception):
    """Custom exception for Drive client errors."""
    pass


class DriveClient:
    """Google Drive API client with built-in caching."""

    SCOPES = ['https://www.googleapis.com/auth/drive']
    CACHE_DIR = Path(__file__).parent.parent.parent / '.cache' / 'google-drive'
    CACHE_TTL = 3600  # 1 hour default cache TTL

    def __init__(self, credentials_json: str = None, cache_ttl: int = CACHE_TTL, account: str = None):
        """
        Initialize Drive client. Tries OAuth user credentials first, falls back to service account.

        Args:
            credentials_json: Path to Google Service Account JSON file (legacy)
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
            account: OAuth account name (None = auto-detect)
        """
        self.cache_ttl = cache_ttl
        self._ensure_cache_dir()

        # Load credentials
        try:
            if credentials_json and Path(credentials_json).exists():
                # Legacy: load from file path
                with open(credentials_json, 'r') as f:
                    creds_dict = json.load(f)
                self.credentials = Credentials.from_service_account_info(
                    creds_dict,
                    scopes=self.SCOPES
                )
            elif account or list_accounts():
                # OAuth user credentials (preferred)
                self.credentials = get_user_credentials(self.SCOPES, account=account)
            else:
                # Fallback: service account
                self.credentials = get_credentials(self.SCOPES)
        except json.JSONDecodeError as e:
            raise DriveClientError(f"Invalid credentials JSON: {e}")
        except Exception as e:
            raise DriveClientError(f"Failed to load credentials: {e}")

        # Initialize Drive service
        try:
            self.service = build(
                'drive',
                'v3',
                credentials=self.credentials
            )
        except Exception as e:
            raise DriveClientError(f"Failed to initialize Drive service: {e}")

    def _ensure_cache_dir(self):
        """Ensure cache directory exists."""
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, cache_key: str) -> Path:
        """Generate cache file path from key."""
        hash_key = hashlib.md5(cache_key.encode()).hexdigest()
        return self.CACHE_DIR / f"{hash_key}.json"

    def _load_cache(self, cache_key: str) -> Optional[Dict]:
        """Load data from cache if valid."""
        cache_file = self._get_cache_path(cache_key)
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)

            # Check TTL
            cached_at = datetime.fromisoformat(cached_data.get('_cached_at', ''))
            if datetime.now() - cached_at < timedelta(seconds=self.cache_ttl):
                return cached_data.get('data')
        except Exception:
            pass

        return None

    def _save_cache(self, cache_key: str, data: Any):
        """Save data to cache."""
        cache_file = self._get_cache_path(cache_key)
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'data': data,
                    '_cached_at': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            # Fail silently on cache errors
            pass

    def list_files(
        self,
        folder_id: Optional[str] = None,
        query: Optional[str] = None,
        page_size: int = 100,
        fields: str = 'files(id,name,mimeType,modifiedTime,size,webViewLink)'
    ) -> List[Dict]:
        """
        List files in Google Drive.

        Args:
            folder_id: Filter by parent folder ID
            query: Custom query filter (e.g., "name contains 'report'")
            page_size: Max results per page
            fields: Fields to retrieve (Google Drive API format)

        Returns:
            List of file metadata dictionaries
        """
        # Build cache key
        cache_key = f"list_files:{folder_id}:{query}:{page_size}"

        # Check cache
        cached_result = self._load_cache(cache_key)
        if cached_result is not None:
            return cached_result

        try:
            # Build query
            filters = []
            if folder_id:
                filters.append(f"'{folder_id}' in parents")
            if query:
                filters.append(query)

            final_query = " and ".join(filters) if filters else None

            # Execute query
            results = []
            page_token = None

            while True:
                request = self.service.files().list(
                    q=final_query,
                    spaces='drive',
                    fields=f'nextPageToken, {fields}',
                    pageSize=page_size,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                )

                response = request.execute()
                results.extend(response.get('files', []))

                page_token = response.get('nextPageToken')
                if not page_token:
                    break

            # Cache results
            self._save_cache(cache_key, results)
            return results

        except Exception as e:
            raise DriveClientError(f"Failed to list files: {e}")

    def download_file(self, file_id: str, output_path: str) -> Dict:
        """
        Download file from Google Drive.

        Args:
            file_id: Google Drive file ID
            output_path: Local path to save file

        Returns:
            Dictionary with file metadata and download status
        """
        try:
            # Get file metadata
            metadata_request = self.service.files().get(
                fileId=file_id,
                fields='id,name,mimeType,size',
                supportsAllDrives=True
            )
            metadata = metadata_request.execute()

            # Download file
            media_request = self.service.files().get_media(
                fileId=file_id,
                supportsAllDrives=True
            )

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'wb') as f:
                f.write(media_request.execute())

            return {
                'status': 'success',
                'file_id': file_id,
                'filename': metadata['name'],
                'output_path': str(output_file),
                'size': metadata.get('size'),
                'mime_type': metadata['mimeType']
            }

        except Exception as e:
            raise DriveClientError(f"Failed to download file {file_id}: {e}")

    def export_file(self, file_id: str, output_path: str, mime_type: str = 'text/plain') -> Dict:
        """
        Export a Google Docs/Sheets/Slides file to a specific format.

        Args:
            file_id: Google Drive file ID
            output_path: Local path to save exported file
            mime_type: Export MIME type (e.g., 'text/plain', 'application/pdf', 'text/markdown')

        Returns:
            Dictionary with file metadata and export status
        """
        try:
            # Get file metadata
            metadata_request = self.service.files().get(
                fileId=file_id,
                fields='id,name,mimeType',
                supportsAllDrives=True
            )
            metadata = metadata_request.execute()

            # Export file
            export_request = self.service.files().export_media(
                fileId=file_id,
                mimeType=mime_type
            )

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'wb') as f:
                f.write(export_request.execute())

            return {
                'status': 'success',
                'file_id': file_id,
                'filename': metadata['name'],
                'output_path': str(output_file),
                'original_mime_type': metadata['mimeType'],
                'exported_mime_type': mime_type
            }

        except Exception as e:
            raise DriveClientError(f"Failed to export file {file_id}: {e}")

    def upload_file(
        self,
        local_path: str,
        folder_id: Optional[str] = None,
        file_name: Optional[str] = None,
        convert_to_sheets: bool = False
    ) -> Dict:
        """
        Upload file to Google Drive.

        Args:
            local_path: Path to local file to upload
            folder_id: Parent folder ID (root if None)
            file_name: Custom name for uploaded file (original name if None)
            convert_to_sheets: Convert CSV to Google Sheets format

        Returns:
            Dictionary with uploaded file metadata
        """
        try:
            local_file = Path(local_path)
            if not local_file.exists():
                raise DriveClientError(f"Local file not found: {local_path}")

            # Prepare file metadata
            file_metadata = {
                'name': file_name or local_file.name
            }
            if folder_id:
                file_metadata['parents'] = [folder_id]

            # Convert CSV to Google Sheets if requested
            if convert_to_sheets and local_file.suffix.lower() == '.csv':
                file_metadata['mimeType'] = 'application/vnd.google-apps.spreadsheet'
                mime_type = 'text/csv'
            else:
                # Guess MIME type
                mime_type = self._guess_mime_type(local_file)

            # Upload file
            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(
                local_path,
                mimetype=mime_type,
                resumable=True
            )

            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink,size',
                supportsAllDrives=True
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)

            return {
                'status': 'success',
                'file_id': response['id'],
                'filename': response['name'],
                'web_link': response['webViewLink'],
                'size': response.get('size'),
                'local_path': local_path
            }

        except Exception as e:
            raise DriveClientError(f"Failed to upload file: {e}")

    def get_file_metadata(self, file_id: str) -> Dict:
        """
        Get metadata for a specific file.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata dictionary
        """
        try:
            request = self.service.files().get(
                fileId=file_id,
                fields='id,name,mimeType,size,modifiedTime,owners,webViewLink',
                supportsAllDrives=True
            )
            return request.execute()
        except Exception as e:
            raise DriveClientError(f"Failed to get file metadata: {e}")

    def move_file(self, file_id: str, destination_folder_id: str) -> Dict:
        """
        Move file to a different folder.

        Args:
            file_id: Google Drive file ID to move
            destination_folder_id: Target folder ID

        Returns:
            Dictionary with moved file metadata
        """
        try:
            # Get current parents
            file_metadata = self.service.files().get(
                fileId=file_id,
                fields='parents,name',
                supportsAllDrives=True
            ).execute()

            previous_parents = ",".join(file_metadata.get('parents', []))

            # Move file
            updated_file = self.service.files().update(
                fileId=file_id,
                addParents=destination_folder_id,
                removeParents=previous_parents,
                fields='id,name,parents,webViewLink',
                supportsAllDrives=True
            ).execute()

            return {
                'status': 'success',
                'file_id': updated_file['id'],
                'filename': updated_file['name'],
                'new_parents': updated_file.get('parents', []),
                'web_link': updated_file.get('webViewLink')
            }
        except Exception as e:
            raise DriveClientError(f"Failed to move file {file_id}: {e}")

    def create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> Dict:
        """
        Create a new folder in Google Drive.

        Args:
            folder_name: Name of the folder to create
            parent_folder_id: Parent folder ID (root if None)

        Returns:
            Dictionary with created folder metadata
        """
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]

            folder = self.service.files().create(
                body=file_metadata,
                fields='id,name,webViewLink',
                supportsAllDrives=True
            ).execute()

            return {
                'status': 'success',
                'folder_id': folder['id'],
                'folder_name': folder['name'],
                'web_link': folder.get('webViewLink')
            }
        except Exception as e:
            raise DriveClientError(f"Failed to create folder: {e}")

    @staticmethod
    def _guess_mime_type(file_path: Path) -> str:
        """Guess MIME type from file extension."""
        mime_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.gif': 'image/gif',
            '.zip': 'application/zip'
        }

        ext = file_path.suffix.lower()
        return mime_types.get(ext, 'application/octet-stream')
