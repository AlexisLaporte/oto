#!/usr/bin/env python3
"""
Google Slides API client for generating presentations
"""
import io
import os
import json
import tempfile
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


def parse_bold_markdown(text):
    """Parse **bold** segments → (clean_text, [(start, end), ...]).

    Useful when injecting markdown-flavoured text into Slides placeholders :
    Slides API ne comprend pas le markdown, donc on extrait les ranges et on
    applique `updateTextStyle bold:True` dessus.
    """
    clean, bolds = [], []
    i, pos = 0, 0
    while i < len(text):
        if text[i:i + 2] == '**':
            j = text.find('**', i + 2)
            if j == -1:
                clean.append(text[i:])
                pos += len(text) - i
                break
            seg = text[i + 2:j]
            start = pos
            clean.append(seg)
            pos += len(seg)
            bolds.append((start, pos))
            i = j + 2
        else:
            clean.append(text[i])
            pos += 1
            i += 1
    return ''.join(clean), bolds


def _hex_to_rgb(hex_color):
    """
    Convert hex color to Google Slides RGB format (0.0-1.0)

    Args:
        hex_color: Hex color string like '#RRGGBB' or 'RRGGBB'

    Returns:
        dict: {'red': float, 'green': float, 'blue': float}
    """
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return {'red': r, 'green': g, 'blue': b}


class SlidesClient:
    """Client for Google Slides API operations"""

    SCOPES = [
        'https://www.googleapis.com/auth/presentations',
        'https://www.googleapis.com/auth/drive'
    ]

    def __init__(self, credentials_json=None, account=None):
        """
        Initialize Slides client.

        Resolution order (premier qui répond gagne) :
        1. `credentials_json` (path or JSON string) — service account legacy
        2. `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` env var — service account legacy
        3. OAuth user credentials via `oto.tools.google.credentials.get_user_credentials`
           (avec ou sans nom d'`account`). Préféré pour manipuler des fichiers
           du Drive personnel d'un utilisateur.

        Args:
            credentials_json: Path to service account JSON or JSON string (legacy)
            account: OAuth account name (None = auto-detect single account)
        """
        # 1) Service account explicit
        if credentials_json is None:
            credentials_json = os.getenv('GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON')

        if credentials_json:
            if os.path.isfile(credentials_json):
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_json, scopes=self.SCOPES)
            else:
                credentials_info = json.loads(credentials_json)
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info, scopes=self.SCOPES)
        else:
            # 2) OAuth user credentials (preferred for personal Drive ops)
            from oto.tools.google.credentials import get_user_credentials
            credentials = get_user_credentials(self.SCOPES, account=account)

        self.slides_service = build('slides', 'v1', credentials=credentials)
        self.drive_service = build('drive', 'v3', credentials=credentials)

    def create_presentation(self, title, folder_id=None, template_id=None):
        """
        Create a new presentation, optionally from a template

        Args:
            title: Title of the presentation
            folder_id: Optional Google Drive folder ID to create in
            template_id: Optional presentation ID to use as template (copies theme)

        Returns:
            dict: Presentation resource with id, title, etc.
        """
        if template_id:
            # Copy template presentation
            copy_metadata = {
                'name': title
            }
            if folder_id:
                copy_metadata['parents'] = [folder_id]

            copied_file = self.drive_service.files().copy(
                fileId=template_id,
                body=copy_metadata,
                supportsAllDrives=True,
                fields='id'
            ).execute()

            presentation_id = copied_file['id']
            presentation = self.slides_service.presentations().get(
                presentationId=presentation_id).execute()

        elif folder_id:
            # Create file in Drive first, then use Slides API
            file_metadata = {
                'name': title,
                'mimeType': 'application/vnd.google-apps.presentation',
                'parents': [folder_id]
            }
            file = self.drive_service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()
            presentation_id = file['id']
            # Get presentation details
            presentation = self.slides_service.presentations().get(
                presentationId=presentation_id).execute()
        else:
            body = {'title': title}
            presentation = self.slides_service.presentations().create(
                body=body).execute()
        return presentation

    def get_presentation(self, presentation_id):
        """Get presentation details"""
        return self.slides_service.presentations().get(
            presentationId=presentation_id).execute()

    def get_layout_id_by_name(self, presentation_id, layout_name):
        """
        Get layout object ID by predefined layout name

        Args:
            presentation_id: ID of the presentation
            layout_name: Name like 'TITLE_AND_BODY', 'TITLE_ONLY', etc.

        Returns:
            str: Layout object ID, or None if not found
        """
        presentation = self.get_presentation(presentation_id)

        # Build a mapping of available layouts
        layouts_by_name = {}
        default_layout_id = None

        for layout in presentation.get('layouts', []):
            props = layout.get('layoutProperties', {})
            display_name = props.get('displayName', '')
            name = props.get('name', '')
            object_id = layout['objectId']

            # Map by API name (always available)
            layouts_by_name[name] = object_id

            # Also map by display name for easier lookup
            if display_name:
                layouts_by_name[display_name] = object_id

            # Remember DEFAULT or first layout as fallback
            if display_name == 'DEFAULT' or name == 'DEFAULT':
                default_layout_id = object_id
            elif default_layout_id is None:
                default_layout_id = object_id

        # Try to find the requested layout
        if layout_name in layouts_by_name:
            return layouts_by_name[layout_name]

        # Fallback: use DEFAULT for TITLE_AND_BODY if not available
        if layout_name == 'TITLE_AND_BODY' and 'DEFAULT' in layouts_by_name:
            return layouts_by_name['DEFAULT']

        # Last resort: return default
        return default_layout_id

    def add_slide(self, presentation_id, layout='BLANK', insertion_index=None):
        """
        Add a new slide to presentation

        Args:
            presentation_id: ID of the presentation
            layout: Layout type (BLANK, TITLE_ONLY, TITLE, SECTION_HEADER, etc.)
            insertion_index: Position to insert (None = end)

        Returns:
            str: Object ID of the created slide
        """
        # Try to find layout by name first (for templates)
        layout_id = self.get_layout_id_by_name(presentation_id, layout)

        if layout_id:
            # Use layout object ID
            requests = [{
                'createSlide': {
                    'slideLayoutReference': {
                        'layoutId': layout_id
                    }
                }
            }]
        else:
            # Use predefined layout name (for new presentations)
            requests = [{
                'createSlide': {
                    'slideLayoutReference': {
                        'predefinedLayout': layout
                    }
                }
            }]

        if insertion_index is not None:
            requests[0]['createSlide']['insertionIndex'] = insertion_index

        response = self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()

        return response['replies'][0]['createSlide']['objectId']

    def add_text_box(self, presentation_id, slide_id, text, x, y, width, height):
        """
        Add a text box to a slide

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            text: Text content
            x, y, width, height: Position and size in EMU (1 pt = 12700 EMU)

        Returns:
            str: Object ID of the created text box
        """
        object_id = f'textbox_{slide_id}_{len(text)}'

        requests = [
            {
                'createShape': {
                    'objectId': object_id,
                    'shapeType': 'TEXT_BOX',
                    'elementProperties': {
                        'pageObjectId': slide_id,
                        'size': {
                            'width': {'magnitude': width, 'unit': 'EMU'},
                            'height': {'magnitude': height, 'unit': 'EMU'}
                        },
                        'transform': {
                            'scaleX': 1,
                            'scaleY': 1,
                            'translateX': x,
                            'translateY': y,
                            'unit': 'EMU'
                        }
                    }
                }
            },
            {
                'insertText': {
                    'objectId': object_id,
                    'text': text,
                    'insertionIndex': 0
                }
            }
        ]

        self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()

        return object_id

    def set_text_style(self, presentation_id, object_id, font_size=None, bold=None):
        """
        Set text style for an object

        Args:
            presentation_id: ID of the presentation
            object_id: ID of the text object
            font_size: Font size in points
            bold: Whether text should be bold
        """
        requests = []

        if font_size:
            requests.append({
                'updateTextStyle': {
                    'objectId': object_id,
                    'style': {
                        'fontSize': {
                            'magnitude': font_size,
                            'unit': 'PT'
                        }
                    },
                    'fields': 'fontSize'
                }
            })

        if bold is not None:
            requests.append({
                'updateTextStyle': {
                    'objectId': object_id,
                    'style': {'bold': bold},
                    'fields': 'bold'
                }
            })

        if requests:
            self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()

    def format_text_range(self, presentation_id, object_id, start_index, end_index,
                         bold=None, italic=None, underline=None, link=None,
                         fg_color=None, bg_color=None):
        """
        Apply formatting to a specific text range

        Args:
            presentation_id: ID of the presentation
            object_id: ID of the text object
            start_index: Start position (0-based)
            end_index: End position (exclusive)
            bold: Boolean for bold
            italic: Boolean for italic
            underline: Boolean for underline
            link: URL string for hyperlink
            fg_color: Foreground color (hex like '#FF0000' or RGB dict)
            bg_color: Background color (hex like '#FFFF00' or RGB dict)
        """
        style = {}
        fields = []

        if bold is not None:
            style['bold'] = bold
            fields.append('bold')

        if italic is not None:
            style['italic'] = italic
            fields.append('italic')

        if underline is not None:
            style['underline'] = underline
            fields.append('underline')

        if link:
            style['link'] = {'url': link}
            fields.append('link')

        if fg_color:
            rgb = _hex_to_rgb(fg_color) if isinstance(fg_color, str) else fg_color
            style['foregroundColor'] = {
                'opaqueColor': {'rgbColor': rgb}
            }
            fields.append('foregroundColor')

        if bg_color:
            rgb = _hex_to_rgb(bg_color) if isinstance(bg_color, str) else bg_color
            style['backgroundColor'] = {
                'opaqueColor': {'rgbColor': rgb}
            }
            fields.append('backgroundColor')

        if not fields:
            return  # Nothing to do

        request = {
            'updateTextStyle': {
                'objectId': object_id,
                'textRange': {
                    'type': 'FIXED_RANGE',
                    'startIndex': start_index,
                    'endIndex': end_index
                },
                'style': style,
                'fields': ','.join(fields)
            }
        }

        self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': [request]}
        ).execute()

    def insert_image(self, presentation_id, slide_id, image_url, x, y, width, height):
        """
        Insert an image into a slide

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide
            image_url: URL of the image (must be publicly accessible)
            x, y: Position in EMU (1 pt = 12700 EMU)
            width, height: Size in EMU

        Returns:
            str: Object ID of the created image
        """
        import uuid
        object_id = f'image_{uuid.uuid4().hex[:8]}'

        requests = [{
            'createImage': {
                'objectId': object_id,
                'url': image_url,
                'elementProperties': {
                    'pageObjectId': slide_id,
                    'size': {
                        'width': {'magnitude': width, 'unit': 'EMU'},
                        'height': {'magnitude': height, 'unit': 'EMU'}
                    },
                    'transform': {
                        'scaleX': 1,
                        'scaleY': 1,
                        'translateX': x,
                        'translateY': y,
                        'unit': 'EMU'
                    }
                }
            }
        }]

        self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()

        return object_id

    def upload_image_to_drive(self, image_path, folder_id=None):
        """
        Upload a local image file to Google Drive

        Args:
            image_path: Path to the local image file
            folder_id: Optional folder ID to upload to

        Returns:
            str: Publicly accessible URL of the uploaded image
        """
        from googleapiclient.http import MediaFileUpload
        import mimetypes

        file_name = Path(image_path).name
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = 'image/png'

        file_metadata = {'name': file_name}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaFileUpload(image_path, mimetype=mime_type)
        file = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webContentLink',
            supportsAllDrives=True
        ).execute()

        # Make the file publicly readable
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        self.drive_service.permissions().create(
            fileId=file['id'],
            body=permission,
            supportsAllDrives=True
        ).execute()

        # Return the direct download URL
        file_id = file['id']
        return f"https://drive.google.com/uc?export=view&id={file_id}"

    def move_to_folder(self, file_id, folder_id):
        """
        Move a file to a specific folder in Drive

        Args:
            file_id: ID of the file
            folder_id: ID of the target folder
        """
        # Get current parents
        file = self.drive_service.files().get(
            fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))

        # Move to new folder
        self.drive_service.files().update(
            fileId=file_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()

    def create_folder(self, folder_name, parent_folder_id=None):
        """
        Create a folder in Google Drive

        Args:
            folder_name: Name of the folder
            parent_folder_id: Optional parent folder ID

        Returns:
            str: ID of the created folder
        """
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]

        folder = self.drive_service.files().create(
            body=file_metadata,
            fields='id',
            supportsAllDrives=True
        ).execute()

        return folder['id']

    def share_presentation(self, presentation_id, role='reader', type='anyone'):
        """
        Share a presentation

        Args:
            presentation_id: ID of the presentation
            role: Permission role (reader, writer, commenter)
            type: Permission type (user, group, domain, anyone)
        """
        permission = {
            'type': type,
            'role': role
        }

        self.drive_service.permissions().create(
            fileId=presentation_id,
            body=permission,
            supportsAllDrives=True
        ).execute()

    def get_presentation_url(self, presentation_id):
        """Get the URL to view/edit a presentation"""
        return f"https://docs.google.com/presentation/d/{presentation_id}/edit"

    def replace_image_placeholder(self, presentation_id, image_object_id, image_url, replace_method='CENTER_INSIDE'):
        """
        Replace an image placeholder with actual image content

        Args:
            presentation_id: ID of the presentation
            image_object_id: Object ID of the image element to replace
            image_url: URL of the image (must be publicly accessible)
            replace_method: How to fit the image ('CENTER_INSIDE' or 'CENTER_CROP')

        Returns:
            API response
        """
        requests = [{
            'replaceImage': {
                'imageObjectId': image_object_id,
                'url': image_url,
                'imageReplaceMethod': replace_method
            }
        }]

        return self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()

    def get_image_placeholders_in_slide(self, presentation_id, slide_id):
        """
        Get all image elements/placeholders in a slide

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide

        Returns:
            list: List of image object IDs
        """
        presentation = self.get_presentation(presentation_id)

        for slide in presentation.get('slides', []):
            if slide['objectId'] == slide_id:
                image_ids = []
                for elem in slide.get('pageElements', []):
                    if 'image' in elem:
                        image_ids.append(elem['objectId'])
                return image_ids

        return []

    def get_slide_ids(self, presentation_id):
        """
        Get list of all slide IDs in presentation

        Args:
            presentation_id: ID of presentation

        Returns:
            list: List of slide object IDs in order
        """
        presentation = self.get_presentation(presentation_id)
        return [slide['objectId'] for slide in presentation.get('slides', [])]

    def get_text_content(self, presentation_id, slide_id, object_id):
        """
        Get text content from a shape or text box

        Args:
            presentation_id: ID of presentation
            slide_id: ID of slide
            object_id: ID of shape/text box

        Returns:
            str: Text content or None if not found
        """
        presentation = self.get_presentation(presentation_id)

        for slide in presentation.get('slides', []):
            if slide['objectId'] == slide_id:
                for elem in slide.get('pageElements', []):
                    if elem['objectId'] == object_id:
                        if 'shape' in elem and 'text' in elem['shape']:
                            text = ''
                            for text_elem in elem['shape']['text'].get('textElements', []):
                                if 'textRun' in text_elem:
                                    text += text_elem['textRun'].get('content', '')
                            return text
        return None

    def get_text_objects_in_slide(self, presentation_id, slide_id):
        """
        Get all text objects (shapes with text) in a slide

        Args:
            presentation_id: ID of presentation
            slide_id: ID of slide

        Returns:
            list: List of dicts with objectId, text content, shapeType, and position info
        """
        presentation = self.get_presentation(presentation_id)

        for slide in presentation.get('slides', []):
            if slide['objectId'] == slide_id:
                text_objects = []

                for elem in slide.get('pageElements', []):
                    if 'shape' in elem:
                        shape = elem['shape']
                        if 'text' in shape:
                            # Extract text content
                            text = ''
                            for text_elem in shape['text'].get('textElements', []):
                                if 'textRun' in text_elem:
                                    text += text_elem['textRun'].get('content', '')

                            text_objects.append({
                                'objectId': elem['objectId'],
                                'shapeType': shape.get('shapeType'),
                                'text': text,
                                'transform': elem.get('transform'),
                                'size': elem.get('size')
                            })

                return text_objects

        return []

    def _edit_text_preserve_style(self, presentation_id, object_id, new_text):
        """
        Internal method: Edit text while preserving formatting

        Preserves the style (size, bold, color, etc.) of the first text run
        """
        # Get current shape and extract style
        presentation = self.get_presentation(presentation_id)

        # Find the shape
        shape_element = None
        for slide in presentation.get('slides', []):
            for element in slide.get('pageElements', []):
                if element['objectId'] == object_id:
                    shape_element = element
                    break
            if shape_element:
                break

        if not shape_element or 'shape' not in shape_element:
            raise ValueError(f"Shape {object_id} not found")

        shape = shape_element['shape']

        # Extract text style from first text run
        text_style = None
        paragraph_style = None

        if 'text' in shape:
            text_content = shape['text']
            text_elements = text_content.get('textElements', [])

            # Get text style from first text run
            for text_elem in text_elements:
                if 'textRun' in text_elem:
                    text_run = text_elem['textRun']
                    text_style = text_run.get('style', {})
                    break

            # Get paragraph style
            for text_elem in text_elements:
                if 'paragraphMarker' in text_elem:
                    paragraph_style = text_elem['paragraphMarker'].get('style', {})
                    break

        # Build requests: delete, insert, apply styles
        requests = [
            {
                'deleteText': {
                    'objectId': object_id,
                    'textRange': {'type': 'ALL'}
                }
            },
            {
                'insertText': {
                    'objectId': object_id,
                    'text': new_text,
                    'insertionIndex': 0
                }
            }
        ]

        # Apply text style if found
        if text_style:
            requests.append({
                'updateTextStyle': {
                    'objectId': object_id,
                    'style': text_style,
                    'textRange': {'type': 'ALL'},
                    'fields': '*'
                }
            })

        # Apply paragraph style if found
        if paragraph_style:
            requests.append({
                'updateParagraphStyle': {
                    'objectId': object_id,
                    'style': paragraph_style,
                    'textRange': {'type': 'ALL'},
                    'fields': '*'
                }
            })

        return self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()

    def edit_text(self, presentation_id, object_id, new_text,
                  start_index=None, end_index=None, preserve_style=True):
        """
        Edit text in an existing shape or text box

        Args:
            presentation_id: ID of the presentation
            object_id: ID of the shape/text box
            new_text: New text content
            start_index: Optional start position (None = replace all)
            end_index: Optional end position (None = replace all)
            preserve_style: Preserve formatting (size, bold, color) - default True

        Returns:
            dict: API response

        Example:
            # Replace all text in a text box (preserving style)
            client.edit_text(pres_id, obj_id, "New content")

            # Replace without preserving style
            client.edit_text(pres_id, obj_id, "New content", preserve_style=False)

            # Replace specific range
            client.edit_text(pres_id, obj_id, "Insert", start_index=5, end_index=10)
        """
        # If replacing all text and preserving style, use optimized method
        if start_index is None and end_index is None and preserve_style:
            return self._edit_text_preserve_style(presentation_id, object_id, new_text)

        # Otherwise use traditional delete+insert (loses style)
        requests = []

        if start_index is None and end_index is None:
            # Replace all text
            requests = [
                {
                    'deleteText': {
                        'objectId': object_id,
                        'textRange': {'type': 'ALL'}
                    }
                },
                {
                    'insertText': {
                        'objectId': object_id,
                        'text': new_text,
                        'insertionIndex': 0
                    }
                }
            ]
        else:
            # Replace specific range
            if start_index is None:
                start_index = 0

            # If end_index not provided, we need to delete to end
            # For simplicity, if end_index is None, we replace from start_index to end
            if end_index is None:
                # Delete from start to end, then insert
                requests = [
                    {
                        'deleteText': {
                            'objectId': object_id,
                            'textRange': {
                                'type': 'FROM_START_INDEX',
                                'startIndex': start_index
                            }
                        }
                    },
                    {
                        'insertText': {
                            'objectId': object_id,
                            'text': new_text,
                            'insertionIndex': start_index
                        }
                    }
                ]
            else:
                # Delete specific range, then insert
                requests = [
                    {
                        'deleteText': {
                            'objectId': object_id,
                            'textRange': {
                                'type': 'FIXED_RANGE',
                                'startIndex': start_index,
                                'endIndex': end_index
                            }
                        }
                    },
                    {
                        'insertText': {
                            'objectId': object_id,
                            'text': new_text,
                            'insertionIndex': start_index
                        }
                    }
                ]

        return self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()

    def replace_all_text(self, presentation_id, find_text, replace_text,
                        match_case=False, page_object_ids=None):
        """
        Replace all occurrences of text in presentation (global find/replace)

        Useful for replacing placeholders like {{company}}, {{date}}, etc.

        Args:
            presentation_id: ID of presentation
            find_text: Text to find
            replace_text: Replacement text
            match_case: Whether to match case (default: False)
            page_object_ids: Optional list of slide IDs to limit search

        Returns:
            dict: API response with occurrencesChanged count

        Example:
            # Replace all placeholders
            result = client.replace_all_text(pres_id, '{{company}}', 'Acme Corp')
            print(f"Replaced {result['replies'][0]['replaceAllText']['occurrencesChanged']} occurrences")
        """
        request = {
            'replaceAllText': {
                'containsText': {
                    'text': find_text,
                    'matchCase': match_case
                },
                'replaceText': replace_text
            }
        }

        if page_object_ids:
            request['replaceAllText']['pageObjectIds'] = page_object_ids

        return self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': [request]}
        ).execute()

    def duplicate_slide(self, presentation_id, slide_id, insertion_index=None):
        """
        Duplicate a slide within the same presentation (uses native API)

        Args:
            presentation_id: ID of the presentation
            slide_id: ID of the slide to duplicate
            insertion_index: Optional position for new slide (default: after source)

        Returns:
            str: Object ID of the duplicated slide

        Example:
            new_slide_id = client.duplicate_slide(pres_id, slide_id)
        """
        request = {
            'duplicateObject': {
                'objectId': slide_id
            }
        }

        if insertion_index is not None:
            request['duplicateObject']['insertionIndex'] = insertion_index

        result = self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': [request]}
        ).execute()

        # Extract new slide ID from response
        if 'replies' in result and len(result['replies']) > 0:
            reply = result['replies'][0]
            if 'duplicateObject' in reply:
                return reply['duplicateObject']['objectId']

        return None

    def copy_slide_to_presentation(self, source_presentation_id, source_slide_id,
                                   target_presentation_id, insertion_index=None,
                                   preserve_layout=True):
        """
        Copy a slide from one presentation to another by recreating its elements

        This method reads the source slide structure and recreates all elements
        in the target presentation. Works across different presentations.

        Args:
            source_presentation_id: ID of source presentation
            source_slide_id: ID of slide to copy
            target_presentation_id: ID of target presentation
            insertion_index: Optional position for new slide
            preserve_layout: Try to preserve original layout (default: True)

        Returns:
            str: Object ID of the new slide

        Note:
            - Supports: text shapes, images, basic positioning
            - May not preserve: complex animations, some advanced features
            - Images need to be accessible (same Drive account or public)

        Example:
            new_slide_id = client.copy_slide_to_presentation(
                source_pres_id, source_slide_id, target_pres_id
            )
        """
        # Read source slide structure
        source_pres = self.get_presentation(source_presentation_id)
        source_slide = None

        for slide in source_pres.get('slides', []):
            if slide['objectId'] == source_slide_id:
                source_slide = slide
                break

        if not source_slide:
            raise ValueError(f"Slide {source_slide_id} not found in source presentation")

        # Determine layout for new slide
        source_layout_id = None
        if preserve_layout and 'slideProperties' in source_slide:
            source_layout_id = source_slide['slideProperties'].get('layoutObjectId')

        # Create new slide in target presentation
        # Use API directly to avoid layout ID being treated as layout name
        requests = []

        if source_layout_id:
            # Check if source layout exists in target (same template)
            target_pres = self.get_presentation(target_presentation_id)
            target_layout_exists = any(
                layout['objectId'] == source_layout_id
                for layout in target_pres.get('layouts', [])
            )

            if target_layout_exists:
                # Use same layout ID directly (same template)
                requests = [{
                    'createSlide': {
                        'slideLayoutReference': {
                            'layoutId': source_layout_id
                        }
                    }
                }]
            else:
                # Try to find matching layout by name (different templates)
                source_layout_name = None
                for layout in source_pres.get('layouts', []):
                    if layout['objectId'] == source_layout_id:
                        source_layout_name = layout.get('layoutProperties', {}).get('name')
                        break

                if source_layout_name:
                    target_layout_id = self.get_layout_id_by_name(target_presentation_id, source_layout_name)
                    if target_layout_id:
                        requests = [{
                            'createSlide': {
                                'slideLayoutReference': {
                                    'layoutId': target_layout_id
                                }
                            }
                        }]

        # Fallback: use BLANK layout
        if not requests:
            requests = [{
                'createSlide': {
                    'slideLayoutReference': {
                        'predefinedLayout': 'BLANK'
                    }
                }
            }]

        if insertion_index is not None:
            requests[0]['createSlide']['insertionIndex'] = insertion_index

        response = self.slides_service.presentations().batchUpdate(
            presentationId=target_presentation_id,
            body={'requests': requests}
        ).execute()

        new_slide_id = response['replies'][0]['createSlide']['objectId']

        # Get the newly created slide with placeholders
        target_pres_initial = self.get_presentation(target_presentation_id)
        new_slide = None
        for slide in target_pres_initial.get('slides', []):
            if slide['objectId'] == new_slide_id:
                new_slide = slide
                break

        # Match and fill placeholders to preserve layout-defined styles
        if new_slide:
            # Collect source placeholders with text
            source_placeholders = []
            for element in source_slide.get('pageElements', []):
                if 'shape' in element:
                    shape = element['shape']
                    if shape.get('placeholder'):
                        text_content = ''
                        if 'text' in shape:
                            for text_elem in shape['text'].get('textElements', []):
                                if 'textRun' in text_elem:
                                    text_content += text_elem['textRun'].get('content', '')

                        source_placeholders.append({
                            'type': shape['placeholder'].get('type'),
                            'index': shape['placeholder'].get('index', 0),
                            'text': text_content
                        })

            # Collect target placeholders
            target_placeholders = []
            for element in new_slide.get('pageElements', []):
                if 'shape' in element:
                    shape = element['shape']
                    if shape.get('placeholder'):
                        target_placeholders.append({
                            'objectId': element['objectId'],
                            'type': shape['placeholder'].get('type'),
                            'index': shape['placeholder'].get('index', 0)
                        })

            # Match placeholders by type and index, then fill with text
            text_requests = []
            for source_ph in source_placeholders:
                if not source_ph['text']:
                    continue

                # Find matching target placeholder
                for target_ph in target_placeholders:
                    if (source_ph['type'] == target_ph['type'] and
                        source_ph['index'] == target_ph['index']):
                        text_requests.append({
                            'insertText': {
                                'objectId': target_ph['objectId'],
                                'text': source_ph['text'],
                                'insertionIndex': 0
                            }
                        })
                        break

            if text_requests:
                self.slides_service.presentations().batchUpdate(
                    presentationId=target_presentation_id,
                    body={'requests': text_requests}
                ).execute()

        # Copy non-placeholder elements from source
        requests = []

        for element in source_slide.get('pageElements', []):
            element_type = None

            # Determine element type
            if 'shape' in element:
                # Skip placeholders (already handled above)
                if element['shape'].get('placeholder'):
                    continue
                element_type = 'shape'
            elif 'image' in element:
                element_type = 'image'
            elif 'table' in element:
                element_type = 'table'
            elif 'line' in element:
                element_type = 'line'
            elif 'video' in element:
                element_type = 'video'
            else:
                # Skip unknown element types
                continue

            # Extract common properties
            transform = element.get('transform', {})
            size = element.get('size', {})

            # Create request based on element type
            if element_type == 'shape':
                shape = element['shape']

                # Create shape
                create_request = {
                    'createShape': {
                        'objectId': None,  # Let API generate ID
                        'shapeType': shape.get('shapeType', 'TEXT_BOX'),
                        'elementProperties': {
                            'pageObjectId': new_slide_id,
                            'size': size,
                            'transform': transform
                        }
                    }
                }
                requests.append(create_request)

                # Store text to add in second pass
                if 'text' in shape:
                    text_content = ''
                    for text_elem in shape['text'].get('textElements', []):
                        if 'textRun' in text_elem:
                            text_content += text_elem['textRun'].get('content', '')

            elif element_type == 'image':
                image = element['image']
                content_url = image.get('contentUrl')

                if content_url:
                    create_request = {
                        'createImage': {
                            'url': content_url,
                            'elementProperties': {
                                'pageObjectId': new_slide_id,
                                'size': size,
                                'transform': transform
                            }
                        }
                    }
                    requests.append(create_request)

        # Execute batch to create non-placeholder elements
        if requests:
            self.slides_service.presentations().batchUpdate(
                presentationId=target_presentation_id,
                body={'requests': requests}
            ).execute()

        # Second pass: Add text content to non-placeholder shapes
        # Get the updated slide
        target_pres = self.get_presentation(target_presentation_id)
        target_slide = None

        for slide in target_pres.get('slides', []):
            if slide['objectId'] == new_slide_id:
                target_slide = slide
                break

        if target_slide:
            text_requests = []
            source_shapes_with_text = []

            # Collect source non-placeholder shapes with text
            for element in source_slide.get('pageElements', []):
                if 'shape' in element:
                    # Skip placeholders
                    if element['shape'].get('placeholder'):
                        continue

                    if 'text' in element['shape']:
                        text_content = ''
                        for text_elem in element['shape']['text'].get('textElements', []):
                            if 'textRun' in text_elem:
                                text_content += text_elem['textRun'].get('content', '')
                        if text_content:
                            source_shapes_with_text.append({
                                'transform': element.get('transform', {}),
                                'text': text_content
                            })

            # Match with target non-placeholder shapes by position
            target_shapes = [
                e for e in target_slide.get('pageElements', [])
                if 'shape' in e and not e['shape'].get('placeholder')
            ]

            for i, source_shape_info in enumerate(source_shapes_with_text):
                if i < len(target_shapes):
                    target_shape_id = target_shapes[i]['objectId']
                    text_requests.append({
                        'insertText': {
                            'objectId': target_shape_id,
                            'text': source_shape_info['text'],
                            'insertionIndex': 0
                        }
                    })

            if text_requests:
                self.slides_service.presentations().batchUpdate(
                    presentationId=target_presentation_id,
                    body={'requests': text_requests}
                ).execute()

        return new_slide_id

    # ------------------------------------------------------------------
    # High-level builders (template-driven generation)
    # ------------------------------------------------------------------

    def convert_pptx_to_native(self, pptx_id, name, folder_id=None):
        """
        Convert a .pptx file already in Drive into a native Google Slides file.

        `drive.files().copy()` ne convertit pas le mimeType, donc on télécharge
        puis on ré-upload en spécifiant `mimeType=application/vnd.google-apps.presentation`
        — Drive fait la conversion à l'upload.

        Args:
            pptx_id: Drive file ID of the source .pptx
            name: Name of the resulting Google Slides file
            folder_id: Optional Drive folder ID to place the result in

        Returns:
            str: presentationId of the newly created Google Slides file
        """
        req = self.drive_service.files().get_media(fileId=pptx_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)

        with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp:
            tmp.write(buf.read())
            tmp_path = tmp.name

        media = MediaFileUpload(
            tmp_path,
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        )
        body = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.presentation',
        }
        if folder_id:
            body['parents'] = [folder_id]
        f = self.drive_service.files().create(
            body=body, media_body=media, fields='id', supportsAllDrives=True,
        ).execute()
        return f['id']

    def get_layouts_map(self, presentation_id):
        """
        Return {layout_name: {'objectId': ..., 'placeholders': [(type, index), ...]}}.

        Useful pour découvrir les layouts d'un master importé avant de les
        utiliser via `build_from_layouts`.
        """
        pres = self.get_presentation(presentation_id)
        out = {}
        for layout in pres.get('layouts', []):
            props = layout.get('layoutProperties', {})
            name = props.get('name', '')
            placeholders = []
            for el in layout.get('pageElements', []):
                if 'shape' in el and el['shape'].get('placeholder'):
                    ph = el['shape']['placeholder']
                    placeholders.append((ph.get('type'), ph.get('index', 0)))
            out[name] = {
                'objectId': layout['objectId'],
                'placeholders': placeholders,
                'displayName': props.get('displayName', ''),
            }
        return out

    def clear_all_slides(self, presentation_id, keepalive_layout_id=None):
        """
        Supprime toutes les slides existantes en gardant une slide temporaire
        (l'API Slides refuse une présentation à 0 slide).

        Args:
            presentation_id: ID de la présentation
            keepalive_layout_id: layoutId d'une slide temporaire à insérer en queue.
                Si None, prend le premier layout disponible.

        Returns:
            str: objectId de la slide temporaire keepalive
                 (à supprimer après avoir créé tes vraies slides)
        """
        pres = self.slides_service.presentations().get(
            presentationId=presentation_id, fields='slides(objectId),layouts(objectId)'
        ).execute()
        existing = [s['objectId'] for s in pres.get('slides', [])]

        if keepalive_layout_id is None:
            layouts = pres.get('layouts', [])
            if not layouts:
                raise ValueError("Aucun layout disponible pour le keepalive")
            keepalive_layout_id = layouts[0]['objectId']

        keepalive_id = 'tmp_keepalive_oto'
        # Si déjà présent (re-run), réutiliser
        if keepalive_id in existing:
            others = [s for s in existing if s != keepalive_id]
            if others:
                self.slides_service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={'requests': [{'deleteObject': {'objectId': s}} for s in others]},
                ).execute()
            return keepalive_id

        requests = [{
            'createSlide': {
                'objectId': keepalive_id,
                'slideLayoutReference': {'layoutId': keepalive_layout_id},
            }
        }]
        for s in existing:
            requests.append({'deleteObject': {'objectId': s}})
        self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body={'requests': requests}
        ).execute()
        return keepalive_id

    def build_from_layouts(self, presentation_id, slides_def,
                           override_body_bold=True, parse_markdown_bold=True):
        """
        Génère une série de slides à partir d'une liste de définitions, en
        peu de batchUpdate (= robuste face au quota 60 writes/min/user).

        Approche :
        1. 1 batchUpdate `createSlide` avec `placeholderIdMappings` → objectIds
           prédictibles.
        2. 1 batchUpdate `insertText` + `updateTextStyle` (bold) sur tous les
           placeholders à remplir.

        Args:
            presentation_id: ID de la présentation cible (déjà nettoyée si besoin)
            slides_def: liste de tuples `(slide_id, layout_id, fills)` où `fills`
                est un dict `{(placeholder_type, placeholder_index): text}`.
                `slide_id` doit faire ≥ 5 caractères (contrainte API).
            override_body_bold: si True (défaut), force `bold:False` sur tous les
                placeholders BODY avant d'appliquer les ranges bold issues du
                markdown. Utile quand le master rend BODY en gras par défaut
                (cas du template Otomata) — sinon `**bold**` est invisible.
            parse_markdown_bold: si True (défaut), parse les segments `**…**`
                du texte et applique `updateTextStyle bold:True` dessus.

        Returns:
            list[str]: la liste des objectIds des slides créées
        """
        # Phase 1 — création des slides + placeholderIdMappings
        create_reqs = []
        for idx, (slide_id, layout_id, fills) in enumerate(slides_def):
            if len(slide_id) < 5:
                raise ValueError(
                    f"slide_id {slide_id!r} doit faire ≥ 5 caractères "
                    f"(contrainte Slides API)"
                )
            ph_mappings = [
                {
                    'layoutPlaceholder': {'type': ph_type, 'index': ph_index},
                    'objectId': f'{slide_id}_{ph_type}_{ph_index}',
                }
                for (ph_type, ph_index) in fills.keys()
            ]
            create_reqs.append({
                'createSlide': {
                    'objectId': slide_id,
                    'insertionIndex': idx,
                    'slideLayoutReference': {'layoutId': layout_id},
                    'placeholderIdMappings': ph_mappings,
                }
            })

        if create_reqs:
            self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body={'requests': create_reqs}
            ).execute()

        # Phase 2 — insertText + updateTextStyle
        fill_reqs = []
        for slide_id, _layout_id, fills in slides_def:
            for (ph_type, ph_index), text in fills.items():
                obj_id = f'{slide_id}_{ph_type}_{ph_index}'
                if parse_markdown_bold:
                    clean, bolds = parse_bold_markdown(text)
                else:
                    clean, bolds = text, []
                if not clean:
                    continue
                fill_reqs.append({
                    'insertText': {
                        'objectId': obj_id,
                        'text': clean,
                        'insertionIndex': 0,
                    }
                })
                # Casser l'héritage bold du master (cas Otomata) sur les BODY
                if override_body_bold and ph_type == 'BODY':
                    fill_reqs.append({
                        'updateTextStyle': {
                            'objectId': obj_id,
                            'textRange': {'type': 'ALL'},
                            'style': {'bold': False},
                            'fields': 'bold',
                        }
                    })
                # Appliquer les ranges bold issues du markdown
                for start, end in bolds:
                    fill_reqs.append({
                        'updateTextStyle': {
                            'objectId': obj_id,
                            'textRange': {
                                'type': 'FIXED_RANGE',
                                'startIndex': start,
                                'endIndex': end,
                            },
                            'style': {'bold': True},
                            'fields': 'bold',
                        }
                    })

        if fill_reqs:
            self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body={'requests': fill_reqs}
            ).execute()

        return [slide_id for slide_id, _, _ in slides_def]

    def export_pdf(self, presentation_id, output_path):
        """Exporte la présentation en PDF localement (via Drive export)."""
        data = self.drive_service.files().export(
            fileId=presentation_id, mimeType='application/pdf'
        ).execute()
        with open(output_path, 'wb') as f:
            f.write(data)
        return output_path
