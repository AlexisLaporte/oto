"""Convert markdown to Google Docs API batchUpdate requests.

Supports: headings (#-###), bold, italic, bullet/numbered lists, blockquotes, horizontal rules.
"""

import re
from typing import List, Dict, Tuple


def markdown_to_requests(text: str) -> Tuple[str, List[Dict]]:
    """Parse markdown and return (plain_text, formatting_requests).

    The plain text should be inserted first at index 1, then the formatting
    requests applied as a batchUpdate. Requests are returned in reverse index
    order so indices don't shift.
    """
    lines = text.split('\n')
    plain_parts: List[str] = []
    formatting: List[Dict] = []  # (start, end, style_info)

    # Track current position (1-based for Google Docs, text starts at index 1)
    pos = 1

    for line in lines:
        stripped = line.rstrip()

        # Horizontal rule
        if re.match(r'^-{3,}$|^\*{3,}$|^_{3,}$', stripped.strip()):
            # Insert a thin horizontal line via a simple separator
            segment = '\n'
            plain_parts.append(segment)
            # Add a horizontal rule request
            formatting.append({
                'type': 'hr',
                'start': pos,
                'end': pos + len(segment),
            })
            pos += len(segment)
            continue

        # Heading
        heading_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2)
            # Parse inline formatting within heading
            clean_text, inline_fmt = _parse_inline(heading_text, pos)
            segment = clean_text + '\n'
            plain_parts.append(segment)
            formatting.append({
                'type': 'heading',
                'level': level,
                'start': pos,
                'end': pos + len(segment) - 1,  # exclude trailing \n for style
            })
            formatting.extend(inline_fmt)
            pos += len(segment)
            continue

        # Bullet list
        bullet_match = re.match(r'^(\s*)[-*+]\s+(.+)$', stripped)
        if bullet_match:
            indent = len(bullet_match.group(1)) // 2
            content = bullet_match.group(2)
            clean_text, inline_fmt = _parse_inline(content, pos)
            segment = clean_text + '\n'
            plain_parts.append(segment)
            formatting.append({
                'type': 'bullet',
                'start': pos,
                'end': pos + len(segment),
                'indent': indent,
            })
            formatting.extend(inline_fmt)
            pos += len(segment)
            continue

        # Numbered list
        num_match = re.match(r'^(\s*)\d+[.)]\s+(.+)$', stripped)
        if num_match:
            indent = len(num_match.group(1)) // 2
            content = num_match.group(2)
            clean_text, inline_fmt = _parse_inline(content, pos)
            segment = clean_text + '\n'
            plain_parts.append(segment)
            formatting.append({
                'type': 'numbered',
                'start': pos,
                'end': pos + len(segment),
                'indent': indent,
            })
            formatting.extend(inline_fmt)
            pos += len(segment)
            continue

        # Blockquote
        quote_match = re.match(r'^>\s*(.*)$', stripped)
        if quote_match:
            content = quote_match.group(1)
            clean_text, inline_fmt = _parse_inline(content, pos)
            segment = clean_text + '\n'
            plain_parts.append(segment)
            formatting.append({
                'type': 'quote',
                'start': pos,
                'end': pos + len(segment),
            })
            formatting.extend(inline_fmt)
            pos += len(segment)
            continue

        # Regular paragraph or empty line
        clean_text, inline_fmt = _parse_inline(stripped, pos)
        segment = clean_text + '\n'
        plain_parts.append(segment)
        formatting.extend(inline_fmt)
        pos += len(segment)

    plain_text = ''.join(plain_parts)
    # Remove trailing newline if any
    if plain_text.endswith('\n'):
        plain_text = plain_text[:-1]

    requests = _build_requests(formatting)
    return plain_text, requests


def _parse_inline(text: str, base_pos: int) -> Tuple[str, List[Dict]]:
    """Parse inline bold/italic markers, return clean text + formatting entries."""
    fmt = []
    result = []
    offset = 0  # tracks position in clean text relative to base_pos

    i = 0
    while i < len(text):
        # Bold: **text** or __text__
        bold_match = re.match(r'\*\*(.+?)\*\*|__(.+?)__', text[i:])
        if bold_match:
            content = bold_match.group(1) or bold_match.group(2)
            start = base_pos + offset
            result.append(content)
            offset += len(content)
            fmt.append({
                'type': 'bold',
                'start': start,
                'end': start + len(content),
            })
            i += bold_match.end()
            continue

        # Italic: *text* or _text_
        italic_match = re.match(r'\*(.+?)\*|_(.+?)_', text[i:])
        if italic_match:
            content = italic_match.group(1) or italic_match.group(2)
            start = base_pos + offset
            result.append(content)
            offset += len(content)
            fmt.append({
                'type': 'italic',
                'start': start,
                'end': start + len(content),
            })
            i += italic_match.end()
            continue

        result.append(text[i])
        offset += 1
        i += 1

    return ''.join(result), fmt


HEADING_STYLES = {
    1: 'HEADING_1',
    2: 'HEADING_2',
    3: 'HEADING_3',
}


def _build_requests(formatting: List[Dict]) -> List[Dict]:
    """Convert formatting entries to Google Docs API requests, in reverse order."""
    requests = []

    for entry in formatting:
        t = entry['type']

        if t == 'heading':
            requests.append({
                'updateParagraphStyle': {
                    'range': {'startIndex': entry['start'], 'endIndex': entry['end']},
                    'paragraphStyle': {
                        'namedStyleType': HEADING_STYLES.get(entry['level'], 'HEADING_3'),
                    },
                    'fields': 'namedStyleType',
                }
            })

        elif t == 'bold':
            requests.append({
                'updateTextStyle': {
                    'range': {'startIndex': entry['start'], 'endIndex': entry['end']},
                    'textStyle': {'bold': True},
                    'fields': 'bold',
                }
            })

        elif t == 'italic':
            requests.append({
                'updateTextStyle': {
                    'range': {'startIndex': entry['start'], 'endIndex': entry['end']},
                    'textStyle': {'italic': True},
                    'fields': 'italic',
                }
            })

        elif t == 'bullet':
            requests.append({
                'createParagraphBullets': {
                    'range': {'startIndex': entry['start'], 'endIndex': entry['end']},
                    'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE',
                }
            })

        elif t == 'numbered':
            requests.append({
                'createParagraphBullets': {
                    'range': {'startIndex': entry['start'], 'endIndex': entry['end']},
                    'bulletPreset': 'NUMBERED_DECIMAL_NESTED',
                }
            })

        elif t == 'quote':
            requests.append({
                'updateParagraphStyle': {
                    'range': {'startIndex': entry['start'], 'endIndex': entry['end']},
                    'paragraphStyle': {
                        'indentStart': {'magnitude': 36, 'unit': 'PT'},
                        'borderLeft': {
                            'color': {'color': {'rgbColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}}},
                            'width': {'magnitude': 3, 'unit': 'PT'},
                            'padding': {'magnitude': 8, 'unit': 'PT'},
                            'dashStyle': 'SOLID',
                        },
                    },
                    'fields': 'indentStart,borderLeft',
                }
            })
            # Quotes in italic
            requests.append({
                'updateTextStyle': {
                    'range': {'startIndex': entry['start'], 'endIndex': entry['end']},
                    'textStyle': {'italic': True},
                    'fields': 'italic',
                }
            })

        elif t == 'hr':
            # Style the newline as a thin bottom border
            requests.append({
                'updateParagraphStyle': {
                    'range': {'startIndex': entry['start'], 'endIndex': entry['end']},
                    'paragraphStyle': {
                        'borderBottom': {
                            'color': {'color': {'rgbColor': {'red': 0.7, 'green': 0.7, 'blue': 0.7}}},
                            'width': {'magnitude': 1, 'unit': 'PT'},
                            'padding': {'magnitude': 6, 'unit': 'PT'},
                            'dashStyle': 'SOLID',
                        },
                    },
                    'fields': 'borderBottom',
                }
            })

    return requests
