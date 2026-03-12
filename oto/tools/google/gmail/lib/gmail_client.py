"""Gmail API client using OAuth2 user credentials."""

import base64
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import parseaddr
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


class GmailClientError(Exception):
    """Gmail API error."""


class GmailClient:
    """Gmail API client.

    Args:
        credentials: OAuth2 user credentials. If None, uses get_user_credentials().
        account: Named account to use (None = auto-detect if single account).
    """

    def __init__(self, credentials: Optional[Credentials] = None, account: Optional[str] = None):
        if credentials is None:
            from oto.tools.google.credentials import get_user_credentials
            credentials = get_user_credentials(SCOPES, account=account)
        self.service = build('gmail', 'v1', credentials=credentials)

    def list_messages(
        self,
        query: Optional[str] = None,
        label_ids: Optional[list[str]] = None,
        max_results: int = 20,
    ) -> list[dict]:
        """List messages with metadata (id, snippet, from, subject, date)."""
        kwargs = {'userId': 'me', 'maxResults': max_results}
        if query:
            kwargs['q'] = query
        if label_ids:
            kwargs['labelIds'] = label_ids

        resp = self.service.users().messages().list(**kwargs).execute()
        messages = resp.get('messages', [])

        results = []
        for msg in messages:
            meta = self.service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['From', 'Subject', 'Date'],
            ).execute()
            headers = {h['name']: h['value'] for h in meta.get('payload', {}).get('headers', [])}
            results.append({
                'id': meta['id'],
                'threadId': meta['threadId'],
                'snippet': meta.get('snippet', ''),
                'from': headers.get('From', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'labelIds': meta.get('labelIds', []),
            })

        return results

    def get_message(self, message_id: str) -> dict:
        """Get full message content with attachment metadata."""
        msg = self.service.users().messages().get(
            userId='me', id=message_id, format='full',
        ).execute()

        headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
        body = self._extract_body(msg.get('payload', {}))
        attachments = self._list_attachments(msg.get('payload', {}))

        result = {
            'id': msg['id'],
            'threadId': msg['threadId'],
            'subject': headers.get('Subject', ''),
            'from': headers.get('From', ''),
            'to': headers.get('To', ''),
            'cc': headers.get('Cc', ''),
            'date': headers.get('Date', ''),
            'body': body,
            'labelIds': msg.get('labelIds', []),
        }
        if attachments:
            result['attachments'] = attachments
        return result

    def download_attachments(self, message_id: str, output_dir: str) -> list[dict]:
        """Download all attachments from a message.

        Returns list of {filename, path, size_bytes}.
        """
        msg = self.service.users().messages().get(
            userId='me', id=message_id, format='full',
        ).execute()

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        downloaded = []

        for part in self._iter_parts(msg.get('payload', {})):
            filename = part.get('filename')
            att_id = part.get('body', {}).get('attachmentId')
            if not filename or not att_id:
                continue

            att = self.service.users().messages().attachments().get(
                userId='me', messageId=message_id, id=att_id,
            ).execute()
            data = base64.urlsafe_b64decode(att['data'])
            path = out / filename
            path.write_bytes(data)
            downloaded.append({
                'filename': filename,
                'path': str(path),
                'size_bytes': len(data),
            })

        return downloaded

    def get_signature(self) -> str:
        """Get the primary Gmail signature (HTML)."""
        result = self.service.users().settings().sendAs().list(userId='me').execute()
        for alias in result.get('sendAs', []):
            if alias.get('isPrimary'):
                return alias.get('signature', '')
        return ''

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html: Optional[str] = None,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> dict:
        """Send an email. Returns the sent message metadata."""
        message = self._build_message(to, subject, body, html, cc, bcc, attachments)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = self.service.users().messages().send(
            userId='me', body={'raw': raw},
        ).execute()
        return {'id': sent['id'], 'threadId': sent.get('threadId', '')}

    def reply(
        self,
        message_id: str,
        body: str,
        html: Optional[str] = None,
        cc: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> dict:
        """Reply to a message. Preserves thread, subject, and headers."""
        original = self.service.users().messages().get(
            userId='me', id=message_id, format='full',
        ).execute()
        headers = {h['name']: h['value'] for h in original['payload']['headers']}
        thread_id = original['threadId']

        # Determine recipient: reply to sender (unless we sent it, then reply to To)
        from_addr = headers.get('From', '')
        to_addr = headers.get('To', '')
        reply_to_header = headers.get('Reply-To', '')
        profile = self.service.users().getProfile(userId='me').execute()
        my_email = profile['emailAddress']

        if reply_to_header:
            reply_to = parseaddr(reply_to_header)[1]
        elif my_email.lower() in from_addr.lower():
            reply_to = parseaddr(to_addr)[1]
        else:
            reply_to = parseaddr(from_addr)[1]

        if not reply_to:
            raise GmailClientError(f"Cannot determine reply recipient (from={from_addr!r}, to={to_addr!r})")

        subject = headers.get('Subject', '')
        if not subject.lower().startswith('re:'):
            subject = f"Re: {subject}"

        message = self._build_message(reply_to, subject, body, html, cc, None, attachments)
        orig_msg_id = headers.get('Message-ID', '')
        if orig_msg_id:
            message['In-Reply-To'] = orig_msg_id
            message['References'] = orig_msg_id

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = self.service.users().messages().send(
            userId='me', body={'raw': raw, 'threadId': thread_id},
        ).execute()
        return {'id': sent['id'], 'threadId': sent.get('threadId', ''), 'to': reply_to}

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        html: Optional[str] = None,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        attachments: Optional[list[str]] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> dict:
        """Create a draft email. Pass thread_id + in_reply_to for threaded replies."""
        message = self._build_message(to, subject, body, html, cc, bcc, attachments)
        if in_reply_to:
            message['In-Reply-To'] = in_reply_to
            message['References'] = in_reply_to
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        msg_body: dict = {'raw': raw}
        if thread_id:
            msg_body['threadId'] = thread_id
        draft = self.service.users().drafts().create(
            userId='me', body={'message': msg_body},
        ).execute()
        return {'id': draft['id'], 'message_id': draft['message']['id']}

    def create_draft_reply(
        self,
        message_id: str,
        body: str,
        html: Optional[str] = None,
        cc: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> dict:
        """Create a draft reply to a message. Preserves thread, subject, and headers."""
        original = self.service.users().messages().get(
            userId='me', id=message_id, format='full',
        ).execute()
        headers = {h['name']: h['value'] for h in original['payload']['headers']}
        thread_id = original['threadId']

        from_addr = headers.get('From', '')
        to_addr = headers.get('To', '')
        reply_to_header = headers.get('Reply-To', '')
        profile = self.service.users().getProfile(userId='me').execute()
        my_email = profile['emailAddress']

        if reply_to_header:
            reply_to = parseaddr(reply_to_header)[1]
        elif my_email.lower() in from_addr.lower():
            reply_to = parseaddr(to_addr)[1]
        else:
            reply_to = parseaddr(from_addr)[1]

        if not reply_to:
            raise GmailClientError(f"Cannot determine reply recipient (from={from_addr!r}, to={to_addr!r})")

        subject = headers.get('Subject', '')
        if not subject.lower().startswith('re:'):
            subject = f"Re: {subject}"

        orig_msg_id = headers.get('Message-ID', '')
        return self.create_draft(
            to=reply_to, subject=subject, body=body, html=html,
            cc=cc, attachments=attachments,
            thread_id=thread_id, in_reply_to=orig_msg_id or None,
        )

    def _build_message(self, to, subject, body, html=None, cc=None, bcc=None, attachments=None):
        """Build a MIME message."""
        has_attachments = attachments and len(attachments) > 0

        if has_attachments:
            message = MIMEMultipart('mixed')
            if html:
                text_part = MIMEMultipart('alternative')
                text_part.attach(MIMEText(body, 'plain'))
                text_part.attach(MIMEText(html, 'html'))
                message.attach(text_part)
            else:
                message.attach(MIMEText(body, 'plain'))
            for filepath in attachments:
                message.attach(self._make_attachment(filepath))
        elif html:
            message = MIMEMultipart('alternative')
            message.attach(MIMEText(body, 'plain'))
            message.attach(MIMEText(html, 'html'))
        else:
            message = MIMEText(body)

        message['to'] = to
        message['subject'] = subject
        if cc:
            message['cc'] = cc
        if bcc:
            message['bcc'] = bcc
        return message

    @staticmethod
    def _make_attachment(filepath: str) -> MIMEBase:
        """Create a MIME attachment from a file path."""
        path = Path(filepath)
        content_type, _ = mimetypes.guess_type(str(path))
        if content_type is None:
            content_type = 'application/octet-stream'
        main_type, sub_type = content_type.split('/', 1)

        part = MIMEBase(main_type, sub_type)
        part.set_payload(path.read_bytes())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=path.name)
        return part

    def search(self, query: str, max_results: int = 20) -> list[dict]:
        """Search messages using Gmail query syntax."""
        return self.list_messages(query=query, max_results=max_results)

    def archive_messages(self, message_ids: list[str]) -> list[dict]:
        """Archive messages (remove INBOX label). Returns list of results."""
        results = []
        for mid in message_ids:
            res = self.service.users().messages().modify(
                userId='me', id=mid,
                body={'removeLabelIds': ['INBOX']},
            ).execute()
            results.append({'id': res['id'], 'labelIds': res.get('labelIds', [])})
        return results

    def trash_message(self, message_id: str) -> dict:
        """Move a message to trash."""
        return self.service.users().messages().trash(
            userId='me', id=message_id,
        ).execute()

    def _list_attachments(self, payload: dict) -> list[dict]:
        """List attachment metadata from message payload."""
        attachments = []
        for part in self._iter_parts(payload):
            filename = part.get('filename')
            att_id = part.get('body', {}).get('attachmentId')
            if filename and att_id:
                attachments.append({
                    'filename': filename,
                    'mimeType': part.get('mimeType', ''),
                    'size': part.get('body', {}).get('size', 0),
                })
        return attachments

    def _iter_parts(self, payload: dict):
        """Recursively yield all parts from a message payload."""
        parts = payload.get('parts', [])
        for part in parts:
            yield part
            yield from self._iter_parts(part)

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from message payload."""
        # Simple single-part message
        if payload.get('body', {}).get('data'):
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')

        # Multipart: look for text/plain first, then text/html
        parts = payload.get('parts', [])
        for mime_type in ('text/plain', 'text/html'):
            text = self._find_part(parts, mime_type)
            if text:
                return text

        return ''

    def _find_part(self, parts: list, mime_type: str) -> Optional[str]:
        """Recursively find a part by MIME type."""
        for part in parts:
            if part.get('mimeType') == mime_type and part.get('body', {}).get('data'):
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
            # Recurse into nested parts
            nested = part.get('parts', [])
            if nested:
                result = self._find_part(nested, mime_type)
                if result:
                    return result
        return None
