"""
Browser automation tools.

BrowserClient comes from o-browser package.
Domain-specific clients (LinkedIn, Crunchbase...) live here.
"""

try:
    from o_browser import BrowserClient
except ImportError:
    BrowserClient = None

from .linkedin import LinkedInClient  # noqa: linkedin/ subpackage
from .crunchbase import CrunchbaseClient
from .pappers import PappersClient
from .g2 import G2Client
from .indeed import IndeedClient
from .google import GoogleSearchClient

__all__ = [
    "BrowserClient",
    "LinkedInClient",
    "CrunchbaseClient",
    "PappersClient",
    "G2Client",
    "IndeedClient",
    "GoogleSearchClient",
]
