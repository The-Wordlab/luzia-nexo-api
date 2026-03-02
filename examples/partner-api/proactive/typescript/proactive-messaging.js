#!/usr/bin/env node

/**
 * Nexo Partner API - Proactive Messaging Example (Node.js)
 *
 * This example demonstrates how to send proactive messages to subscribers
 * using the Nexo Partner API. It covers:
 * 1. Listing subscribers
 * 2. Getting subscriber threads
 * 3. Sending a proactive message
 *
 * Use case: E-commerce order shipping notification
 *
 * Note: Proactive messaging uses the same auth headers (X-App-Id, X-App-Secret)
 * but the POST /apps/{app_id}/threads/{thread_id}/messages endpoint shape is
 * separate from the webhook contract.
 */

import axios from 'axios';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

// Load environment variables from parent directory
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
dotenv.config({ path: join(__dirname, '..', '.env') });

// Configuration from environment
const config = {
  baseUrl: process.env.API_BASE_URL || 'http://localhost:8000',
  appId: process.env.APP_ID,
  appSecret: process.env.APP_SECRET,
  subscriberId: process.env.SUBSCRIBER_ID,
  threadId: process.env.THREAD_ID,
};

// Validate required configuration
if (!config.appId || !config.appSecret) {
  console.error('❌ Error: APP_ID and APP_SECRET are required.');
  console.error('Please copy .env.example to .env and fill in your credentials.');
  process.exit(1);
}

/**
 * Make an authenticated API request to the Partner API
 * @param {string} method - HTTP method (GET, POST, etc.)
 * @param {string} endpoint - API endpoint path
 * @param {object} data - Request body data (for POST requests)
 * @returns {Promise<object>} API response data
 */
async function makeApiRequest(method, endpoint, data = null) {
  try {
    const response = await axios({
      method,
      url: `${config.baseUrl}${endpoint}`,
      headers: {
        'X-App-Id': config.appId,
        'X-App-Secret': config.appSecret,
        'Content-Type': 'application/json',
      },
      data,
    });

    return response.data;
  } catch (error) {
    if (error.response) {
      // Server responded with error status
      const status = error.response.status;
      const message = error.response.data?.error || error.response.statusText;

      switch (status) {
        case 401:
          throw new Error(`Authentication failed: ${message}. Check your APP_ID and APP_SECRET.`);
        case 404:
          throw new Error(`Resource not found: ${message}`);
        case 500:
          throw new Error(`Server error: ${message}. Please try again later.`);
        default:
          throw new Error(`API error (${status}): ${message}`);
      }
    } else if (error.request) {
      // Request made but no response received
      throw new Error(`Network error: Could not reach ${config.baseUrl}. Is the server running?`);
    } else {
      // Something else happened
      throw new Error(`Request error: ${error.message}`);
    }
  }
}

/**
 * List all subscribers for this app
 * @returns {Promise<Array>} List of subscriber objects
 */
async function listSubscribers() {
  console.log('📋 Fetching subscribers...');
  const data = await makeApiRequest('GET', `/apps/${config.appId}/subscribers`);
  return data.subscribers || [];
}

/**
 * Get all conversation threads for a subscriber
 * @param {string} subscriberId - The subscriber's ID
 * @returns {Promise<Array>} List of thread objects
 */
async function getSubscriberThreads(subscriberId) {
  console.log(`💬 Fetching threads for subscriber ${subscriberId}...`);
  const data = await makeApiRequest('GET', `/apps/${config.appId}/subscribers/${subscriberId}/threads`);
  return data.threads || [];
}

/**
 * Send a proactive message to a thread
 * @param {string} threadId - The thread ID to send the message to
 * @param {object} message - Message object with role and content
 * @returns {Promise<object>} Created message object
 */
async function sendMessage(threadId, message) {
  console.log(`📤 Sending message to thread ${threadId}...`);
  return await makeApiRequest('POST', `/apps/${config.appId}/threads/${threadId}/messages`, message);
}

/**
 * Main example: Send an order shipping notification
 */
async function main() {
  console.log('🚀 Nexo Partner API - Proactive Messaging Example\n');

  try {
    // Step 1: List subscribers (or use provided SUBSCRIBER_ID)
    let targetSubscriberId = config.subscriberId;

    if (!targetSubscriberId) {
      const subscribers = await listSubscribers();
      console.log(`✅ Found ${subscribers.length} subscriber(s)\n`);

      if (subscribers.length === 0) {
        console.log('⚠️  No subscribers found. Users need to authorize your app first.');
        return;
      }

      // Use the first subscriber for this example
      targetSubscriberId = subscribers[0].id;
      console.log(`📌 Using subscriber: ${targetSubscriberId}\n`);
    }

    // Step 2: Get subscriber's threads (or use provided THREAD_ID)
    let targetThreadId = config.threadId;

    if (!targetThreadId) {
      const threads = await getSubscriberThreads(targetSubscriberId);
      console.log(`✅ Found ${threads.length} thread(s)\n`);

      if (threads.length === 0) {
        console.log('⚠️  No active threads found. The subscriber needs to have an existing conversation.');
        return;
      }

      // Use the first thread for this example
      targetThreadId = threads[0].id;
      console.log(`📌 Using thread: ${targetThreadId}\n`);
    }

    // Step 3: Send a proactive message
    // Use case: E-commerce order shipping notification
    const orderNumber = '12345';
    const trackingUrl = 'https://tracking.example.com/12345';

    const message = {
      role: 'assistant',
      content: `📦 Great news! Your order #${orderNumber} has shipped and is on its way!\n\n` +
               `Track your package: ${trackingUrl}\n\n` +
               `Estimated delivery: 2-3 business days.\n\n` +
               `Questions? Just ask me anytime!`,
    };

    const sentMessage = await sendMessage(targetThreadId, message);
    console.log('✅ Message sent successfully!\n');
    console.log('Message details:');
    console.log(`  ID: ${sentMessage.id}`);
    console.log(`  Thread: ${sentMessage.thread_id}`);
    console.log(`  Content: ${sentMessage.content.substring(0, 50)}...`);
    console.log(`  Created: ${sentMessage.created_at}\n`);

    console.log('🎉 Example completed successfully!');

  } catch (error) {
    console.error('\n❌ Error:', error.message);
    process.exit(1);
  }
}

// Run the example
main();
