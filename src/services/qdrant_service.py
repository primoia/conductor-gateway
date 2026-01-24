"""
Qdrant Vector Database Service

Provides semantic search capabilities for agent matching.
Uses sentence-transformers for embedding generation.
"""

import logging
import os
from typing import List, Optional, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)

logger = logging.getLogger(__name__)

# Qdrant configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "primoia-shared-qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_URL = os.getenv("QDRANT_URL", f"http://{QDRANT_HOST}:{QDRANT_PORT}")

# Collection names
AGENTS_COLLECTION = "conductor_agents_capabilities"

# Embedding model - multilingual for Portuguese support
# paraphrase-multilingual-MiniLM-L12-v2 supports 50+ languages including Portuguese
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSION = 384  # Dimension for paraphrase-multilingual-MiniLM-L12-v2


class QdrantService:
    """
    Service for vector-based semantic search using Qdrant.
    """

    _instance: Optional["QdrantService"] = None
    _initialized: bool = False

    def __new__(cls):
        """Singleton pattern for QdrantService."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize Qdrant client and embedding model."""
        if self._initialized:
            return

        self.client: Optional[QdrantClient] = None
        self.model = None
        self._initialized = True

    def _ensure_client(self) -> bool:
        """Ensure Qdrant client is connected."""
        if self.client is not None:
            return True

        try:
            logger.info(f"🔌 Connecting to Qdrant at {QDRANT_URL}")
            self.client = QdrantClient(url=QDRANT_URL, timeout=10)

            # Test connection
            collections = self.client.get_collections()
            logger.info(f"✅ Connected to Qdrant. Collections: {len(collections.collections)}")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Could not connect to Qdrant: {e}")
            self.client = None
            return False

    def _ensure_model(self) -> bool:
        """Ensure embedding model is loaded."""
        if self.model is not None:
            return True

        try:
            logger.info(f"🧠 Loading embedding model: {EMBEDDING_MODEL}")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info(f"✅ Embedding model loaded")
            return True

        except Exception as e:
            logger.error(f"❌ Could not load embedding model: {e}")
            self.model = None
            return False

    def is_available(self) -> bool:
        """Check if Qdrant service is available."""
        return self._ensure_client() and self._ensure_model()

    def create_agents_collection(self) -> bool:
        """Create the agents collection if it doesn't exist."""
        if not self._ensure_client():
            return False

        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if AGENTS_COLLECTION in collection_names:
                logger.info(f"📦 Collection '{AGENTS_COLLECTION}' already exists")
                return True

            # Create collection
            self.client.create_collection(
                collection_name=AGENTS_COLLECTION,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"✅ Created collection '{AGENTS_COLLECTION}'")
            return True

        except Exception as e:
            logger.error(f"❌ Error creating collection: {e}")
            return False

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a text string."""
        if not self._ensure_model():
            return None

        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"❌ Error generating embedding: {e}")
            return None

    def index_agent(self, agent_data: Dict[str, Any]) -> bool:
        """
        Index a single agent in Qdrant.

        Args:
            agent_data: Dict with agent_id, name, description, emoji, tags, persona_content
        """
        if not self.is_available():
            return False

        try:
            agent_id = agent_data.get("agent_id", "")
            name = agent_data.get("name", "")
            description = agent_data.get("description", "")
            emoji = agent_data.get("emoji", "🤖")
            tags = agent_data.get("tags", [])
            persona_content = agent_data.get("persona_content", "")

            # Build rich searchable text with all available content
            tags_text = " ".join(tags) if tags else ""

            # Extract key capabilities from persona (first 1500 chars for embedding)
            persona_excerpt = ""
            if persona_content:
                # Remove markdown formatting for cleaner embedding
                clean_persona = persona_content.replace("#", "").replace("*", "").replace("-", "")
                persona_excerpt = clean_persona[:1500]

            # Combine all searchable content
            # Structure: tags first (most specific), then name, description, persona
            # Putting tags first gives them more weight in the embedding
            searchable_text = (
                f"Keywords: {tags_text}. "
                f"Agent: {name}. "
                f"Description: {description}. "
                f"Capabilities: {persona_excerpt}"
            )

            # Generate embedding
            embedding = self.generate_embedding(searchable_text)
            if embedding is None:
                return False

            # Create deterministic point ID from agent_id using hashlib
            import hashlib
            point_id = int(hashlib.sha256(agent_id.encode()).hexdigest()[:15], 16)

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=AGENTS_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "agent_id": agent_id,
                            "name": name,
                            "description": description,
                            "emoji": emoji,
                            "tags": tags,
                            "searchable_text": searchable_text[:1000]  # Store preview for debugging
                        }
                    )
                ]
            )

            logger.debug(f"✅ Indexed agent: {emoji} {name}")
            return True

        except Exception as e:
            logger.error(f"❌ Error indexing agent {agent_data.get('agent_id')}: {e}")
            return False

    def index_agents_batch(self, agents: List[Dict[str, Any]]) -> int:
        """
        Index multiple agents in batch.

        Returns:
            Number of successfully indexed agents
        """
        if not self.is_available():
            return 0

        # Ensure collection exists
        if not self.create_agents_collection():
            return 0

        success_count = 0
        for agent in agents:
            if self.index_agent(agent):
                success_count += 1

        logger.info(f"✅ Indexed {success_count}/{len(agents)} agents")
        return success_count

    def _extract_keywords(self, text: str) -> set:
        """Extract meaningful keywords from text for hybrid matching."""
        import re
        # Normalize and split
        words = re.findall(r'\b[a-záàâãéèêíïóôõöúüç]{3,}\b', text.lower())
        # Filter common stop words (Portuguese and English)
        stop_words = {
            'para', 'com', 'uma', 'que', 'por', 'não', 'como', 'mais', 'mas',
            'foi', 'são', 'tem', 'seu', 'sua', 'isso', 'este', 'esta', 'esse',
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
            'her', 'was', 'one', 'our', 'out', 'with', 'have', 'this', 'from'
        }
        return set(w for w in words if w not in stop_words and len(w) >= 3)

    def search_agents(
        self,
        query: str,
        current_agent_id: Optional[str] = None,
        limit: int = 5,
        score_threshold: float = 0.25
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search for agents matching a query.

        Combines:
        1. Semantic search via Qdrant embeddings
        2. Keyword boost for agents with matching tags

        Args:
            query: User message to match
            current_agent_id: Currently selected agent (for comparison)
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of matching agents with scores
        """
        if not self.is_available():
            logger.warning("⚠️ Qdrant not available, returning empty results")
            return []

        try:
            # Extract keywords from query for hybrid matching
            query_keywords = self._extract_keywords(query)
            logger.debug(f"🔍 Query keywords: {query_keywords}")

            # Generate query embedding
            query_embedding = self.generate_embedding(query)
            if query_embedding is None:
                return []

            # Search in Qdrant - get more results for reranking
            results = self.client.query_points(
                collection_name=AGENTS_COLLECTION,
                query=query_embedding,
                limit=limit * 3,  # Get more for hybrid reranking
                score_threshold=score_threshold * 0.7  # Lower threshold, will filter after boost
            )

            # Apply hybrid scoring: semantic score + keyword boost
            matches = []
            for result in results.points:
                payload = result.payload
                semantic_score = result.score

                # Calculate keyword boost based on tag matches
                agent_tags = set(t.lower() for t in (payload.get("tags", []) or []))
                tag_matches = query_keywords & agent_tags
                keyword_boost = len(tag_matches) * 0.08  # 8% boost per matching tag

                # Also check description for keyword matches
                description = (payload.get("description", "") or "").lower()
                desc_matches = sum(1 for kw in query_keywords if kw in description)
                keyword_boost += desc_matches * 0.03  # 3% boost per description match

                # Final hybrid score (capped at 1.0)
                final_score = min(semantic_score + keyword_boost, 1.0)

                # Only include if above threshold after boost
                if final_score >= score_threshold:
                    # Build reason with boost info if applicable
                    if keyword_boost > 0:
                        reason = f"Hybrid match ({int(final_score * 100)}%)"
                    else:
                        reason = f"Semantic match ({int(final_score * 100)}%)"

                    matches.append({
                        "agent_id": payload.get("agent_id"),
                        "name": payload.get("name"),
                        "emoji": payload.get("emoji", "🤖"),
                        "description": payload.get("description"),
                        "tags": payload.get("tags", []),
                        "score": round(final_score, 3),
                        "reason": reason
                    })

            # Sort by score (descending) and limit results
            matches.sort(key=lambda x: x["score"], reverse=True)
            matches = matches[:limit]

            logger.info(f"🔍 Found {len(matches)} matches for query: {query[:50]}...")
            return matches

        except Exception as e:
            logger.error(f"❌ Error searching agents: {e}")
            return []

    def get_collection_stats(self) -> Optional[Dict[str, Any]]:
        """Get statistics about the agents collection."""
        if not self._ensure_client():
            return None

        try:
            info = self.client.get_collection(AGENTS_COLLECTION)
            return {
                "name": AGENTS_COLLECTION,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status.value
            }
        except Exception as e:
            logger.warning(f"⚠️ Could not get collection stats: {e}")
            return None

    def delete_collection(self) -> bool:
        """Delete the agents collection (for reindexing)."""
        if not self._ensure_client():
            return False

        try:
            self.client.delete_collection(AGENTS_COLLECTION)
            logger.info(f"🗑️ Deleted collection '{AGENTS_COLLECTION}'")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Could not delete collection: {e}")
            return False


# Global instance
qdrant_service = QdrantService()
