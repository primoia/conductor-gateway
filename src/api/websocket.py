"""
WebSocket Connection Manager for Gamification Events

Manages WebSocket connections for real-time gamification events
including councilor executions, agent metrics, and system alerts.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Set, Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class GamificationConnectionManager:
    """Manages WebSocket connections for gamification events"""

    def __init__(self):
        # Map of client_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # Subscriptions per client (client_id -> set of event types)
        self.subscriptions: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """Connect a new client"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.subscriptions[client_id] = {"all"}  # Subscribe to all by default
        logger.info(f"🔌 Client {client_id} connected to gamification WebSocket")
        logger.info(f"   Total active connections: {len(self.active_connections)}")

    def disconnect(self, client_id: str):
        """Disconnect a client"""
        self.active_connections.pop(client_id, None)
        self.subscriptions.pop(client_id, None)
        logger.info(f"🔌 Client {client_id} disconnected from WebSocket")
        logger.info(f"   Total active connections: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: dict):
        """
        Send event to all subscribed clients

        Args:
            event_type: Type of event (e.g., "councilor_started", "councilor_completed")
            data: Event data payload
        """
        if not self.active_connections:
            logger.debug(f"No active connections to broadcast {event_type}")
            return

        dead_clients = []
        sent_count = 0

        for client_id, websocket in self.active_connections.items():
            # Check if client is subscribed to this event type
            subs = self.subscriptions.get(client_id, set())
            if "all" not in subs and event_type not in subs:
                continue

            try:
                await websocket.send_json({
                    "type": event_type,
                    "data": data,
                    "timestamp": time.time()
                })
                sent_count += 1
            except Exception as e:
                logger.error(f"❌ Error sending to client {client_id}: {e}")
                dead_clients.append(client_id)

        # Clean up dead connections
        for client_id in dead_clients:
            self.disconnect(client_id)

        logger.debug(f"📤 Broadcasted {event_type} to {sent_count} clients")

    async def send_to(self, client_id: str, event_type: str, data: dict):
        """
        Send event to a specific client

        Args:
            client_id: Target client ID
            event_type: Type of event
            data: Event data payload
        """
        websocket = self.active_connections.get(client_id)
        if websocket:
            try:
                await websocket.send_json({
                    "type": event_type,
                    "data": data,
                    "timestamp": time.time()
                })
                logger.debug(f"📤 Sent {event_type} to client {client_id}")
            except Exception as e:
                logger.error(f"❌ Error sending to client {client_id}: {e}")
                self.disconnect(client_id)
        else:
            logger.warning(f"⚠️ Client {client_id} not found in active connections")

    def update_subscriptions(self, client_id: str, topics: list):
        """
        Update subscriptions for a specific client

        Args:
            client_id: Client ID
            topics: List of event types to subscribe to (or ["all"])
        """
        if client_id in self.active_connections:
            self.subscriptions[client_id] = set(topics)
            logger.info(f"📋 Client {client_id} subscribed to: {topics}")

    def get_stats(self) -> dict:
        """Get connection statistics"""
        return {
            "active_connections": len(self.active_connections),
            "clients": list(self.active_connections.keys()),
            "subscriptions": {
                client_id: list(subs)
                for client_id, subs in self.subscriptions.items()
            }
        }


# Global instance
gamification_manager = GamificationConnectionManager()
