"""
Slack API Client.

Requires: requests
"""

import hmac
import hashlib
from typing import Optional, Dict, Any, List

import requests

from ...config import require_secret, get_secret


def verify_slack_signature(
    signing_secret: str,
    body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """
    Verify Slack webhook signature.

    Args:
        signing_secret: Slack signing secret
        body: Request body bytes
        timestamp: X-Slack-Request-Timestamp header
        signature: X-Slack-Signature header

    Returns:
        True if valid
    """
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    my_signature = "v0=" + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(my_signature, signature)


class SlackClient:
    """
    Slack API client.

    Two tokens are supported:
    - **bot token** (`xoxb-`, env `SLACK_BOT_TOKEN`) — messages appear as the bot app.
      Use for automated/agentic actions (notifications, reactions, scheduled posts).
    - **user token** (`xoxp-`, env `SLACK_USER_TOKEN`) — messages appear as the
      human user who installed the app. Use for outbound human-style com sent
      on behalf of that user.

    Reads/lookups (history, find user, list channels) use the bot token by default
    — bot scopes are usually granted and the response is the same. `post_message`,
    `update_message`, `open_dm`, `add_reaction` accept `as_user=True/False` to pick
    the token explicitly. If `as_user` is omitted, falls back to `default_as_user`
    set at construction (defaults to False = bot-style).
    """

    BASE_URL = "https://slack.com/api"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        user_token: Optional[str] = None,
        default_as_user: bool = False,
    ):
        """
        Initialize Slack client.

        Args:
            bot_token: Slack bot token (or set SLACK_BOT_TOKEN secret)
            user_token: Slack user token (or set SLACK_USER_TOKEN secret).
                Optional — only required for `as_user=True` calls.
            default_as_user: Default mode when a method's `as_user` arg is None.
        """
        self.bot_token = bot_token or get_secret("SLACK_BOT_TOKEN")
        self.user_token = user_token or get_secret("SLACK_USER_TOKEN")
        self.default_as_user = default_as_user
        if not self.bot_token and not self.user_token:
            raise ValueError("Need at least SLACK_BOT_TOKEN or SLACK_USER_TOKEN")

    def _resolve_token(self, as_user: Optional[bool]) -> str:
        mode = self.default_as_user if as_user is None else as_user
        if mode:
            if not self.user_token:
                raise ValueError("as_user=True requires SLACK_USER_TOKEN")
            return self.user_token
        if not self.bot_token:
            raise ValueError("as_user=False requires SLACK_BOT_TOKEN")
        return self.bot_token

    def _request(
        self,
        method: str,
        endpoint: str,
        as_user: Optional[bool] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make API request. Picks token based on as_user (None = default)."""
        url = f"{self.BASE_URL}/{endpoint}"
        headers = {"Authorization": f"Bearer {self._resolve_token(as_user)}"}

        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            raise Exception(f"Slack API error: {data.get('error')}")

        return data

    def post_message(
        self,
        channel: str,
        text: str = None,
        blocks: List[Dict] = None,
        thread_ts: str = None,
        as_user: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to a channel or DM.

        Args:
            channel: Channel ID or name
            text: Message text (fallback for blocks)
            blocks: Block Kit blocks
            thread_ts: Thread timestamp for reply
            as_user: True = post via user token (appears as the human user).
                False = bot token (appears as the bot app). None = client default.

        Returns:
            Message data with ts
        """
        data = {"channel": channel}
        if text:
            data["text"] = text
        if blocks:
            data["blocks"] = blocks
        if thread_ts:
            data["thread_ts"] = thread_ts

        return self._request("POST", "chat.postMessage", as_user=as_user, json=data)

    def delete_message(
        self,
        channel: str,
        ts: str,
        as_user: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Delete a message. Must be deleted with the same token that posted it
        (user-posted → user token, bot-posted → bot token).

        Args:
            channel: Channel ID
            ts: Message timestamp
            as_user: Same conventions as post_message.

        Returns:
            Response data
        """
        return self._request(
            "POST", "chat.delete", as_user=as_user, json={"channel": channel, "ts": ts}
        )

    def update_message(
        self,
        channel: str,
        ts: str,
        text: str = None,
        blocks: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing message.

        Args:
            channel: Channel ID
            ts: Message timestamp
            text: New text
            blocks: New blocks

        Returns:
            Updated message data
        """
        data = {"channel": channel, "ts": ts}
        if text:
            data["text"] = text
        if blocks:
            data["blocks"] = blocks

        return self._request("POST", "chat.update", json=data)

    def post_ephemeral(
        self,
        channel: str,
        user: str,
        text: str = None,
        blocks: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Send an ephemeral message (visible only to one user).

        Args:
            channel: Channel ID
            user: User ID
            text: Message text
            blocks: Block Kit blocks

        Returns:
            Message data
        """
        data = {"channel": channel, "user": user}
        if text:
            data["text"] = text
        if blocks:
            data["blocks"] = blocks

        return self._request("POST", "chat.postEphemeral", json=data)

    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get user information.

        Args:
            user_id: User ID

        Returns:
            User data
        """
        return self._request("GET", "users.info", params={"user": user_id})

    def list_channels(self, types: str = "public_channel") -> List[Dict[str, Any]]:
        """
        List channels.

        Args:
            types: Channel types (public_channel, private_channel, mpim, im)

        Returns:
            List of channels
        """
        data = self._request("GET", "conversations.list", params={"types": types})
        return data.get("channels", [])

    def add_reaction(self, channel: str, ts: str, name: str) -> Dict[str, Any]:
        """
        Add a reaction to a message.

        Args:
            channel: Channel ID
            ts: Message timestamp
            name: Emoji name (without colons)

        Returns:
            Response data
        """
        return self._request("POST", "reactions.add", json={
            "channel": channel,
            "timestamp": ts,
            "name": name,
        })

    def history(
        self,
        channel: str,
        limit: int = 50,
        cursor: Optional[str] = None,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Read recent messages from a channel (or DM/group).

        Args:
            channel: Channel ID
            limit: Max messages (capped at 100 by Slack)
            cursor: Pagination cursor from a previous call
            oldest: Only messages after this ts
            latest: Only messages before this ts

        Returns:
            Response data with "messages" array + "response_metadata.next_cursor"
        """
        params: Dict[str, Any] = {"channel": channel, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest
        return self._request("GET", "conversations.history", params=params)

    def open_dm(self, user: str) -> Dict[str, Any]:
        """
        Open (or return) a direct-message channel with a user.

        Args:
            user: User ID

        Returns:
            Response data with "channel.id" usable as channel for post_message
        """
        return self._request("POST", "conversations.open", json={"users": user})

    def find_user_by_email(self, email: str) -> Dict[str, Any]:
        """
        Look up a user by email.

        Args:
            email: Email address

        Returns:
            User data
        """
        return self._request("GET", "users.lookupByEmail", params={"email": email})

    def search_messages(self, query: str, count: int = 20) -> Dict[str, Any]:
        """
        Search messages across accessible channels. Requires `search:read` scope
        (only available on user tokens, not bot tokens).

        Args:
            query: Slack search query (supports `in:#channel`, `from:@user`, etc.)
            count: Max results

        Returns:
            Response data with "messages.matches"
        """
        return self._request("GET", "search.messages", params={"query": query, "count": count})
