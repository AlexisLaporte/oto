"""Google Sheets API client."""

import csv
import io
from typing import Optional, List, Any

from googleapiclient.discovery import build

from oto.tools.google.credentials import get_user_credentials, get_credentials, list_accounts


SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


class SheetsClientError(Exception):
    pass


class SheetsClient:
    """Google Sheets API client."""

    def __init__(self, account: Optional[str] = None):
        try:
            if account or list_accounts():
                credentials = get_user_credentials(SCOPES, account=account)
            else:
                credentials = get_credentials(SCOPES)
        except Exception as e:
            raise SheetsClientError(f"Failed to load credentials: {e}")

        self.service = build('sheets', 'v4', credentials=credentials)
        self.sheets = self.service.spreadsheets()

    def create(self, title: str) -> dict:
        """Create a new empty spreadsheet."""
        result = self.sheets.create(
            body={'properties': {'title': title}},
            fields='spreadsheetId,spreadsheetUrl,properties.title',
        ).execute()
        return {
            'id': result['spreadsheetId'],
            'title': result['properties']['title'],
            'url': result['spreadsheetUrl'],
        }

    def get_metadata(self, spreadsheet_id: str) -> dict:
        """Get spreadsheet metadata (title, sheets, etc.)."""
        result = self.sheets.get(
            spreadsheetId=spreadsheet_id,
            fields='spreadsheetId,properties.title,sheets.properties'
        ).execute()
        return {
            'id': result['spreadsheetId'],
            'title': result['properties']['title'],
            'sheets': [
                {
                    'id': s['properties']['sheetId'],
                    'title': s['properties']['title'],
                    'rows': s['properties'].get('gridProperties', {}).get('rowCount'),
                    'cols': s['properties'].get('gridProperties', {}).get('columnCount'),
                }
                for s in result.get('sheets', [])
            ]
        }

    def read(
        self,
        spreadsheet_id: str,
        range: str = 'A:ZZ',
        value_render: str = 'FORMATTED_VALUE',
    ) -> List[List[Any]]:
        """Read values from a range. Returns list of rows."""
        result = self.sheets.values().get(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueRenderOption=value_render,
        ).execute()
        return result.get('values', [])

    def write(
        self,
        spreadsheet_id: str,
        range: str,
        values: List[List[Any]],
        value_input: str = 'USER_ENTERED',
    ) -> dict:
        """Write values to a range (overwrites existing data)."""
        result = self.sheets.values().update(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption=value_input,
            body={'values': values},
        ).execute()
        return {
            'updated_range': result.get('updatedRange'),
            'updated_rows': result.get('updatedRows'),
            'updated_cols': result.get('updatedColumns'),
            'updated_cells': result.get('updatedCells'),
        }

    def append(
        self,
        spreadsheet_id: str,
        range: str,
        values: List[List[Any]],
        value_input: str = 'USER_ENTERED',
    ) -> dict:
        """Append rows after existing data."""
        result = self.sheets.values().append(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption=value_input,
            insertDataOption='INSERT_ROWS',
            body={'values': values},
        ).execute()
        updates = result.get('updates', {})
        return {
            'updated_range': updates.get('updatedRange'),
            'updated_rows': updates.get('updatedRows'),
            'updated_cells': updates.get('updatedCells'),
        }

    def clear(self, spreadsheet_id: str, range: str) -> dict:
        """Clear values in a range."""
        result = self.sheets.values().clear(
            spreadsheetId=spreadsheet_id,
            range=range,
            body={},
        ).execute()
        return {'cleared_range': result.get('clearedRange')}

    def write_csv(
        self,
        spreadsheet_id: str,
        csv_path: str,
        sheet_name: Optional[str] = None,
    ) -> dict:
        """Write a CSV file to a sheet (clears then writes)."""
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            values = list(reader)

        # Resolve actual sheet name if not provided
        if not sheet_name:
            meta = self.get_metadata(spreadsheet_id)
            sheet_name = meta['sheets'][0]['title'] if meta['sheets'] else 'Sheet1'

        range_name = f"'{sheet_name}'!A1"
        self.clear(spreadsheet_id, f"'{sheet_name}'")
        return self.write(spreadsheet_id, range_name, values)

    def read_csv(self, spreadsheet_id: str, range: str = 'A:ZZ') -> str:
        """Read a sheet and return as CSV string."""
        rows = self.read(spreadsheet_id, range)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue()
