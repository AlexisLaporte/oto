"""Google Docs API client with navigation and editing support."""

from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from oto.tools.google.credentials import get_credentials, get_user_credentials, list_accounts


@dataclass
class Section:
    """Represents a section in a Google Doc."""
    title: str
    start_index: int
    end_index: int
    content: str
    heading_type: str  # HEADING_1, HEADING_2, etc.


class DocsClient:
    """Google Docs API client with navigation and editing."""

    SCOPES = ['https://www.googleapis.com/auth/documents']

    def __init__(self, credentials_json: str = None, account: str = None):
        if credentials_json and Path(credentials_json).exists():
            import json
            with open(credentials_json, 'r') as f:
                creds_dict = json.load(f)
            self.credentials = Credentials.from_service_account_info(
                creds_dict, scopes=self.SCOPES
            )
        elif account or list_accounts():
            self.credentials = get_user_credentials(self.SCOPES, account=account)
        else:
            self.credentials = get_credentials(self.SCOPES)

        self.service = build('docs', 'v1', credentials=self.credentials)
        self._doc_cache = {}

    def create(self, title: str, content: str = '', markdown: bool = False) -> dict:
        """Create a new Google Doc with optional content.

        Args:
            title: Document title
            content: Text content to insert
            markdown: If True, parse markdown and apply formatting
        """
        doc = self.service.documents().create(
            body={'title': title}
        ).execute()
        doc_id = doc['documentId']

        if content:
            if markdown:
                self._insert_markdown(doc_id, content)
            else:
                self.service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': [{
                        'insertText': {
                            'location': {'index': 1},
                            'text': content,
                        }
                    }]}
                ).execute()

        return {
            'id': doc_id,
            'title': title,
            'url': f'https://docs.google.com/document/d/{doc_id}/edit',
        }

    def _insert_markdown(self, doc_id: str, content: str):
        """Insert markdown content with formatting into a doc."""
        from oto.tools.google.docs.lib.markdown_to_docs import markdown_to_requests

        plain_text, fmt_requests = markdown_to_requests(content)

        # First insert plain text
        requests = [{
            'insertText': {
                'location': {'index': 1},
                'text': plain_text,
            }
        }]
        # Then apply formatting
        requests.extend(fmt_requests)

        self.service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

    def replace_content(self, doc_id: str, content: str, markdown: bool = False) -> dict:
        """Replace entire document content with new text."""
        doc = self.service.documents().get(documentId=doc_id).execute()
        body = doc['body']['content']
        end_index = body[-1]['endIndex'] if body else 1

        # Delete existing content
        requests = []
        if end_index > 2:
            requests.append({
                'deleteContentRange': {
                    'range': {'startIndex': 1, 'endIndex': end_index - 1}
                }
            })

        if markdown:
            from oto.tools.google.docs.lib.markdown_to_docs import markdown_to_requests
            plain_text, fmt_requests = markdown_to_requests(content)
            requests.append({
                'insertText': {
                    'location': {'index': 1},
                    'text': plain_text,
                }
            })
            requests.extend(fmt_requests)
        else:
            requests.append({
                'insertText': {
                    'location': {'index': 1},
                    'text': content,
                }
            })

        self.service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

        self.clear_cache(doc_id)
        return {'id': doc_id, 'status': 'replaced', 'length': len(content)}

    def get_document(self, doc_id: str, use_cache: bool = False) -> dict:
        """Get document content."""
        if use_cache and doc_id in self._doc_cache:
            return self._doc_cache[doc_id]

        doc = self.service.documents().get(documentId=doc_id).execute()
        self._doc_cache[doc_id] = doc
        return doc

    def clear_cache(self, doc_id: str = None):
        """Clear document cache."""
        if doc_id:
            self._doc_cache.pop(doc_id, None)
        else:
            self._doc_cache.clear()

    def list_headings(self, doc_id: str, include_all_caps: bool = True) -> List[Dict]:
        """List all headings in the document with their positions."""
        doc = self.get_document(doc_id)
        headings = []

        for element in doc['body']['content']:
            if 'paragraph' not in element:
                continue

            para = element['paragraph']
            style = para.get('paragraphStyle', {}).get('namedStyleType', '')
            text = self._get_paragraph_text(para)

            if not text:
                continue

            is_heading = False
            detected_style = style

            # Check formal heading styles
            if style in ['HEADING_1', 'HEADING_2', 'HEADING_3', 'TITLE']:
                is_heading = True
            # Check numbered sections like "1. PRESENTATION..."
            elif text and text[0].isdigit() and '.' in text[:5]:
                is_heading = True
                detected_style = 'SECTION'
            # Check ALL CAPS lines (like "WAY OF WORKING") - likely pseudo-headings
            elif include_all_caps and text.isupper() and len(text) > 5 and len(text) < 80:
                is_heading = True
                detected_style = 'ALL_CAPS'

            if is_heading:
                headings.append({
                    'text': text.strip(),
                    'start_index': element.get('startIndex', 0),
                    'end_index': element.get('endIndex', 0),
                    'style': detected_style
                })

        return headings

    def find_heading(self, doc_id: str, search_text: str) -> Optional[Dict]:
        """Find a heading by partial text match."""
        headings = self.list_headings(doc_id)
        search_lower = search_text.lower()

        for heading in headings:
            if search_lower in heading['text'].lower():
                return heading

        return None

    def get_section_content(self, doc_id: str, heading_text: str) -> Optional[Section]:
        """Get the content of a section (from heading to next heading)."""
        doc = self.get_document(doc_id)
        headings = self.list_headings(doc_id)

        # Find the target heading
        target_idx = None
        for i, h in enumerate(headings):
            if heading_text.lower() in h['text'].lower():
                target_idx = i
                break

        if target_idx is None:
            return None

        target = headings[target_idx]
        start = target['start_index']

        # End is either next heading or end of document
        if target_idx + 1 < len(headings):
            end = headings[target_idx + 1]['start_index']
        else:
            end = doc['body']['content'][-1].get('endIndex', start)

        # Extract content
        content = self._extract_text_range(doc, start, end)

        return Section(
            title=target['text'],
            start_index=start,
            end_index=end,
            content=content,
            heading_type=target['style']
        )

    def insert_before_heading(self, doc_id: str, heading_text: str, content: str) -> Dict:
        """Insert content before a specific heading."""
        heading = self.find_heading(doc_id, heading_text)
        if not heading:
            raise ValueError(f"Heading not found: {heading_text}")

        requests = [{
            'insertText': {
                'location': {'index': heading['start_index']},
                'text': content + '\n'
            }
        }]

        result = self.service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

        self.clear_cache(doc_id)

        return {
            'status': 'success',
            'inserted_at': heading['start_index'],
            'before_heading': heading['text'],
            'content_length': len(content)
        }

    def insert_after_heading(self, doc_id: str, heading_text: str, content: str) -> Dict:
        """Insert content after a specific heading (at end of that line)."""
        heading = self.find_heading(doc_id, heading_text)
        if not heading:
            raise ValueError(f"Heading not found: {heading_text}")

        requests = [{
            'insertText': {
                'location': {'index': heading['end_index']},
                'text': content + '\n'
            }
        }]

        result = self.service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

        self.clear_cache(doc_id)

        return {
            'status': 'success',
            'inserted_at': heading['end_index'],
            'after_heading': heading['text'],
            'content_length': len(content)
        }

    def move_section(self, doc_id: str, section_heading: str, before_heading: str) -> Dict:
        """Move a section (heading + content) before another heading."""
        # Get section to move
        section = self.get_section_content(doc_id, section_heading)
        if not section:
            raise ValueError(f"Section not found: {section_heading}")

        # Find target position
        target = self.find_heading(doc_id, before_heading)
        if not target:
            raise ValueError(f"Target heading not found: {before_heading}")

        # Build requests: delete then insert
        # (delete from end first so indices don't shift for insert)
        requests = [
            {
                'deleteContentRange': {
                    'range': {
                        'startIndex': section.start_index,
                        'endIndex': section.end_index
                    }
                }
            },
            {
                'insertText': {
                    'location': {'index': target['start_index']},
                    'text': section.content
                }
            }
        ]

        result = self.service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

        self.clear_cache(doc_id)

        return {
            'status': 'success',
            'moved_section': section.title,
            'from_index': section.start_index,
            'to_before': target['text'],
            'content_length': len(section.content)
        }

    def replace_section(self, doc_id: str, section_heading: str, new_content: str) -> Dict:
        """Replace a section's content (keeps heading, replaces body)."""
        section = self.get_section_content(doc_id, section_heading)
        if not section:
            raise ValueError(f"Section not found: {section_heading}")

        # Find where the heading ends (content starts after heading line)
        doc = self.get_document(doc_id)
        heading = self.find_heading(doc_id, section_heading)
        content_start = heading['end_index']

        requests = [
            {
                'deleteContentRange': {
                    'range': {
                        'startIndex': content_start,
                        'endIndex': section.end_index
                    }
                }
            },
            {
                'insertText': {
                    'location': {'index': content_start},
                    'text': '\n' + new_content + '\n'
                }
            }
        ]

        result = self.service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

        self.clear_cache(doc_id)

        return {
            'status': 'success',
            'replaced_section': section.title,
            'old_length': len(section.content),
            'new_length': len(new_content)
        }

    def delete_section(self, doc_id: str, section_heading: str) -> Dict:
        """Delete a section (heading + content)."""
        section = self.get_section_content(doc_id, section_heading)
        if not section:
            raise ValueError(f"Section not found: {section_heading}")

        requests = [{
            'deleteContentRange': {
                'range': {
                    'startIndex': section.start_index,
                    'endIndex': section.end_index
                }
            }
        }]

        result = self.service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

        self.clear_cache(doc_id)

        return {
            'status': 'success',
            'deleted_section': section.title,
            'deleted_length': len(section.content)
        }

    def _get_paragraph_text(self, paragraph: dict) -> str:
        """Extract text from a paragraph element."""
        text = ''
        for el in paragraph.get('elements', []):
            if 'textRun' in el:
                text += el['textRun'].get('content', '')
        return text.strip()

    def _extract_text_range(self, doc: dict, start: int, end: int) -> str:
        """Extract text between two indices."""
        text = ''
        for element in doc['body']['content']:
            el_start = element.get('startIndex', 0)
            el_end = element.get('endIndex', 0)

            if el_end <= start:
                continue
            if el_start >= end:
                break

            if 'paragraph' in element:
                for el in element['paragraph'].get('elements', []):
                    if 'textRun' in el:
                        text += el['textRun'].get('content', '')

        return text
