#!/usr/bin/env python3

"""
Nexo Partner API - Proactive Messaging Example (Python)

This example demonstrates how to send proactive messages to subscribers
using the Nexo Partner API. It covers:
1. Listing subscribers
2. Getting subscriber threads
3. Sending a proactive message

Use case: Delivery service arrival notification

Note: Proactive messaging uses the same auth headers (X-App-Id, X-App-Secret)
but the POST /apps/{app_id}/threads/{thread_id}/messages endpoint shape is
separate from the webhook contract.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests
from dotenv import load_dotenv

# Load environment variables from parent directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


# Configuration from environment
class Config:
    """API configuration loaded from environment variables"""

    base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    app_id: Optional[str] = os.getenv("APP_ID")
    app_secret: Optional[str] = os.getenv("APP_SECRET")
    subscriber_id: Optional[str] = os.getenv("SUBSCRIBER_ID")
    thread_id: Optional[str] = os.getenv("THREAD_ID")

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration"""
        if not cls.app_id or not cls.app_secret:
            print("❌ Error: APP_ID and APP_SECRET are required.")
            print("Please copy .env.example to .env and fill in your credentials.")
            sys.exit(1)


class PartnerAPIClient:
    """Client for Nexo Partner API with authentication"""

    def __init__(self, base_url: str, app_id: str, app_secret: str):
        self.base_url = base_url.rstrip("/")
        self.app_id = app_id
        self.app_secret = app_secret
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-App-Id": app_id,
                "X-App-Secret": app_secret,
                "Content-Type": "application/json",
            }
        )

    def _make_request(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make an authenticated API request

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request body data (for POST requests)

        Returns:
            API response data

        Raises:
            Exception: If API request fails
        """
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(method, url, json=data)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            try:
                message = e.response.json().get("error", e.response.text)
            except Exception:
                message = e.response.text

            if status == 401:
                raise Exception(
                    f"Authentication failed: {message}. "
                    "Check your APP_ID and APP_SECRET."
                )
            elif status == 404:
                raise Exception(f"Resource not found: {message}")
            elif status == 500:
                raise Exception(f"Server error: {message}. Please try again later.")
            else:
                raise Exception(f"API error ({status}): {message}")

        except requests.exceptions.ConnectionError:
            raise Exception(
                f"Network error: Could not reach {self.base_url}. "
                "Is the server running?"
            )
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request error: {str(e)}")

    def list_subscribers(self) -> List[Dict[str, Any]]:
        """
        List all subscribers for this app

        Returns:
            List of subscriber objects
        """
        print("📋 Fetching subscribers...")
        data = self._make_request("GET", f"/api/apps/{self.app_id}/subscribers")
        return data.get("subscribers", [])

    def get_subscriber_threads(self, subscriber_id: str) -> List[Dict[str, Any]]:
        """
        Get all conversation threads for a subscriber

        Args:
            subscriber_id: The subscriber's ID

        Returns:
            List of thread objects
        """
        print(f"💬 Fetching threads for subscriber {subscriber_id}...")
        data = self._make_request(
            "GET", f"/api/apps/{self.app_id}/subscribers/{subscriber_id}/threads"
        )
        return data.get("threads", [])

    def send_message(self, thread_id: str, message: Dict[str, str]) -> Dict[str, Any]:
        """
        Send a proactive message to a thread

        Args:
            thread_id: The thread ID to send the message to
            message: Message object with role and content

        Returns:
            Created message object
        """
        print(f"📤 Sending message to thread {thread_id}...")
        return self._make_request(
            "POST",
            f"/api/apps/{self.app_id}/threads/{thread_id}/messages",
            data=message,
        )


def main() -> None:
    """Main example: Send a delivery arrival notification"""
    print("🚀 Nexo Partner API - Proactive Messaging Example\n")

    # Validate configuration
    Config.validate()

    # Initialize API client
    client = PartnerAPIClient(Config.base_url, Config.app_id, Config.app_secret)

    try:
        # Step 1: List subscribers (or use provided SUBSCRIBER_ID)
        target_subscriber_id = Config.subscriber_id

        if not target_subscriber_id:
            subscribers = client.list_subscribers()
            print(f"✅ Found {len(subscribers)} subscriber(s)\n")

            if not subscribers:
                print(
                    "⚠️  No subscribers found. Users need to authorize your app first."
                )
                return

            # Use the first subscriber for this example
            target_subscriber_id = subscribers[0]["id"]
            print(f"📌 Using subscriber: {target_subscriber_id}\n")

        # Step 2: Get subscriber's threads (or use provided THREAD_ID)
        target_thread_id = Config.thread_id

        if not target_thread_id:
            threads = client.get_subscriber_threads(target_subscriber_id)
            print(f"✅ Found {len(threads)} thread(s)\n")

            if not threads:
                print(
                    "⚠️  No active threads found. The subscriber needs to have an existing conversation."
                )
                return

            # Use the first thread for this example
            target_thread_id = threads[0]["id"]
            print(f"📌 Using thread: {target_thread_id}\n")

        # Step 3: Send a proactive message
        # Use case: Delivery service arrival notification
        delivery_id = "DLV-78910"
        driver_name = "Alex"

        message = {
            "role": "assistant",
            "content": (
                f"🚚 Your delivery is arriving soon!\n\n"
                f"Delivery ID: {delivery_id}\n"
                f"Driver: {driver_name}\n"
                f"ETA: 15 minutes\n\n"
                f"Please be available to receive your package. "
                f"You can track your driver in real-time through the app.\n\n"
                f"Need to give special delivery instructions? Just reply to this message!"
            ),
        }

        sent_message = client.send_message(target_thread_id, message)
        print("✅ Message sent successfully!\n")
        print("Message details:")
        print(f"  ID: {sent_message['id']}")
        print(f"  Thread: {sent_message['thread_id']}")
        print(f"  Content: {sent_message['content'][:50]}...")
        print(f"  Created: {sent_message['created_at']}\n")

        print("🎉 Example completed successfully!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
