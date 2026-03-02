#!/bin/bash

###############################################################################
# Nexo Partner API - cURL Examples
#
# This script demonstrates proactive messaging using the Nexo Partner API
# with standalone cURL commands.
#
# Use case: Various notification scenarios
###############################################################################

set -e  # Exit on error

# Load environment variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env file not found at $ENV_FILE"
    echo "Please copy .env.example to .env and configure your credentials."
    exit 1
fi

# Source environment variables
source "$ENV_FILE"

# Validate required variables
if [ -z "$API_BASE_URL" ] || [ -z "$APP_ID" ] || [ -z "$APP_SECRET" ]; then
    echo "❌ Error: API_BASE_URL, APP_ID, and APP_SECRET are required."
    echo "Please configure them in $ENV_FILE"
    exit 1
fi

echo "🚀 Nexo Partner API - cURL Examples"
echo "===================================="
echo ""
echo "API Base URL: $API_BASE_URL"
echo "App ID: $APP_ID"
echo ""

###############################################################################
# Example 0: Test webhook locally
#
# Use this to send a test payload to your local webhook server.
# Start your webhook server first (e.g., python webhook_server.py or
# node webhook-server.mjs).
###############################################################################
WEBHOOK_URL="${WEBHOOK_URL:-http://localhost:8080}"

echo "🔧 Example 0: Test Webhook Payload (local)"
echo "--------------------------------------------"

TEST_PAYLOAD='{
  "event": "message_received",
  "app": {"id": "test-app", "name": "Test App"},
  "thread": {"id": "test-thread", "customer_id": "test-customer"},
  "message": {
    "id": "msg-001",
    "seq": 1,
    "role": "user",
    "content": "Hello from webhook test!",
    "content_json": {}
  },
  "history_tail": [],
  "metadata": {},
  "timestamp": "2026-02-25T12:00:00Z"
}'

echo "Command:"
echo "curl -X POST \"$WEBHOOK_URL/webhook\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '<test payload>'"
echo ""
echo "(Skipping actual request - start your webhook server and run manually)"
echo "Expected response: {\"reply\": \"...\"}"
echo ""

###############################################################################
# Example 1: List all subscribers
###############################################################################
echo "📋 Example 1: List Subscribers"
echo "-------------------------------"
echo "Command:"
echo "curl -X GET \"$API_BASE_URL/api/apps/$APP_ID/subscribers\" \\"
echo "  -H \"X-App-Id: $APP_ID\" \\"
echo "  -H \"X-App-Secret: $APP_SECRET\""
echo ""

SUBSCRIBERS_RESPONSE=$(curl -s -X GET "$API_BASE_URL/api/apps/$APP_ID/subscribers" \
  -H "X-App-Id: $APP_ID" \
  -H "X-App-Secret: $APP_SECRET")

echo "Response:"
echo "$SUBSCRIBERS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$SUBSCRIBERS_RESPONSE"
echo ""

# Extract first subscriber ID if available
SUBSCRIBER_ID=$(echo "$SUBSCRIBERS_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['subscribers'][0]['id'] if data.get('subscribers') else '')" 2>/dev/null || echo "$SUBSCRIBER_ID")

if [ -z "$SUBSCRIBER_ID" ]; then
    echo "⚠️  No subscribers found. Users need to authorize your app first."
    echo "Remaining examples require a subscriber. Exiting."
    exit 0
fi

echo "✅ Using subscriber: $SUBSCRIBER_ID"
echo ""

###############################################################################
# Example 2: Get subscriber threads
###############################################################################
echo "💬 Example 2: Get Subscriber Threads"
echo "-------------------------------------"
echo "Command:"
echo "curl -X GET \"$API_BASE_URL/api/apps/$APP_ID/subscribers/$SUBSCRIBER_ID/threads\" \\"
echo "  -H \"X-App-Id: $APP_ID\" \\"
echo "  -H \"X-App-Secret: $APP_SECRET\""
echo ""

THREADS_RESPONSE=$(curl -s -X GET "$API_BASE_URL/api/apps/$APP_ID/subscribers/$SUBSCRIBER_ID/threads" \
  -H "X-App-Id: $APP_ID" \
  -H "X-App-Secret: $APP_SECRET")

echo "Response:"
echo "$THREADS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$THREADS_RESPONSE"
echo ""

# Extract first thread ID if available
THREAD_ID=$(echo "$THREADS_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['threads'][0]['id'] if data.get('threads') else '')" 2>/dev/null || echo "$THREAD_ID")

if [ -z "$THREAD_ID" ]; then
    echo "⚠️  No active threads found. The subscriber needs to have an existing conversation."
    echo "Remaining examples require a thread. Exiting."
    exit 0
fi

echo "✅ Using thread: $THREAD_ID"
echo ""

###############################################################################
# Example 3: Send order shipped notification
###############################################################################
echo "📦 Example 3: Send Order Shipped Notification"
echo "----------------------------------------------"

ORDER_MESSAGE='{
  "role": "assistant",
  "content": "📦 Great news! Your order #12345 has shipped!\n\nTracking: https://tracking.example.com/12345\nETA: 2-3 business days\n\nQuestions? Just reply!"
}'

echo "Command:"
echo "curl -X POST \"$API_BASE_URL/api/apps/$APP_ID/threads/$THREAD_ID/messages\" \\"
echo "  -H \"X-App-Id: $APP_ID\" \\"
echo "  -H \"X-App-Secret: $APP_SECRET\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '$ORDER_MESSAGE'"
echo ""

MESSAGE_RESPONSE=$(curl -s -X POST "$API_BASE_URL/api/apps/$APP_ID/threads/$THREAD_ID/messages" \
  -H "X-App-Id: $APP_ID" \
  -H "X-App-Secret: $APP_SECRET" \
  -H "Content-Type: application/json" \
  -d "$ORDER_MESSAGE")

echo "Response:"
echo "$MESSAGE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$MESSAGE_RESPONSE"
echo ""

###############################################################################
# Example 4: Send appointment reminder
###############################################################################
echo "⏰ Example 4: Send Appointment Reminder"
echo "---------------------------------------"

APPOINTMENT_MESSAGE='{
  "role": "assistant",
  "content": "⏰ Reminder: Your dental appointment is tomorrow at 2:00 PM.\n\nLocation: 123 Main St, Suite 200\nDoctor: Dr. Smith\n\nReply CONFIRM to confirm or RESCHEDULE to change."
}'

echo "Command:"
echo "curl -X POST \"$API_BASE_URL/api/apps/$APP_ID/threads/$THREAD_ID/messages\" \\"
echo "  -H \"X-App-Id: $APP_ID\" \\"
echo "  -H \"X-App-Secret: $APP_SECRET\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '$APPOINTMENT_MESSAGE'"
echo ""

echo "(Skipping actual request to avoid duplicate messages)"
echo "Expected response: Similar to Example 3"
echo ""

###############################################################################
# Example 5: Send payment confirmation
###############################################################################
echo "✅ Example 5: Send Payment Confirmation"
echo "---------------------------------------"

PAYMENT_MESSAGE='{
  "role": "assistant",
  "content": "✅ Payment Confirmed!\n\nAmount: $49.99\nTransaction ID: TXN-2024-001\nDate: 2026-02-22\n\nReceipt has been emailed to you. Thank you for your business!"
}'

echo "Command:"
echo "curl -X POST \"$API_BASE_URL/api/apps/$APP_ID/threads/$THREAD_ID/messages\" \\"
echo "  -H \"X-App-Id: $APP_ID\" \\"
echo "  -H \"X-App-Secret: $APP_SECRET\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '$PAYMENT_MESSAGE'"
echo ""

echo "(Skipping actual request to avoid duplicate messages)"
echo "Expected response: Similar to Example 3"
echo ""

###############################################################################
# Example 6: Error handling - Invalid credentials
###############################################################################
echo "❌ Example 6: Error Handling - Invalid Credentials"
echo "--------------------------------------------------"
echo "Command:"
echo "curl -X GET \"$API_BASE_URL/api/apps/$APP_ID/subscribers\" \\"
echo "  -H \"X-App-Id: invalid\" \\"
echo "  -H \"X-App-Secret: invalid\""
echo ""

ERROR_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X GET "$API_BASE_URL/api/apps/$APP_ID/subscribers" \
  -H "X-App-Id: invalid" \
  -H "X-App-Secret: invalid")

HTTP_CODE=$(echo "$ERROR_RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)
RESPONSE_BODY=$(echo "$ERROR_RESPONSE" | sed 's/HTTP_CODE:[0-9]*$//')

echo "Response (HTTP $HTTP_CODE):"
echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
echo ""

###############################################################################
# Summary
###############################################################################
echo "🎉 Examples completed!"
echo "======================"
echo ""
echo "Summary:"
echo "  ✅ Listed subscribers"
echo "  ✅ Retrieved threads"
echo "  ✅ Sent proactive message"
echo "  ✅ Demonstrated error handling"
echo ""
echo "Next steps:"
echo "  - Integrate these patterns into your application"
echo "  - Customize message content for your use cases"
echo "  - Set up webhooks for real-time events"
echo "  - Review the Partner API documentation"
echo ""
