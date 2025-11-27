"""
Prospector MCP Server.

This MCP server translates MCP tool calls to REST API calls
for the Prospector web scraping service.

Port: 5007
Target: http://prospector-orchestrator:8081
"""

import logging
from typing import Any

import httpx

from src.mcps.base import BaseMCPServer
from src.mcps.registry import MCP_REGISTRY

logger = logging.getLogger(__name__)


class ProspectorMCP(BaseMCPServer):
    """
    MCP Server for Prospector web scraping service.

    Translates MCP tool calls to Prospector REST API:
    - fetch_page → POST /scrape {action: "fetch"}
    - search_site → POST /scrape {action: "search"}
    - extract_contacts → POST /scrape {action: "extract"}
    - get_health → GET /health
    - get_metrics → GET /metrics
    """

    def __init__(self, port: int | None = None):
        config = MCP_REGISTRY["prospector"]
        self.target_url = config["target_url"]
        super().__init__(
            name="prospector",
            port=port or config["port"],
        )

    def _register_tools(self) -> None:
        """Register Prospector tools."""

        @self.mcp.tool(
            name="fetch_page",
            description="""Fetch and scrape a web page using Prospector's scraping engines.
            Returns structured data extracted from the page.

            Parameters:
            - url: The URL of the page to fetch (required)
            - wait_for: CSS selector to wait for before extracting data (optional)

            Returns the page content and extracted data.""",
        )
        async def fetch_page(url: str, wait_for: str | None = None) -> dict[str, Any]:
            return await self._call_scrape({
                "action": "fetch",
                "url": url,
                "wait_for": wait_for,
            })

        @self.mcp.tool(
            name="search_site",
            description="""Search data from a configured site.
            Supported sites: google, github, linkedin, crunchbase.

            Parameters:
            - site: Site identifier (required)
            - query: Search query (required)
            - filters: Optional filters for the search (site-specific)
            - limit: Maximum number of results to return

            Returns search results from the specified site.""",
        )
        async def search_site(
            site: str,
            query: str,
            filters: dict | None = None,
            limit: int | None = None,
        ) -> dict[str, Any]:
            return await self._call_scrape({
                "action": "search",
                "site": site,
                "query": query,
                "filters": filters or {},
                "limit": limit,
            })

        @self.mcp.tool(
            name="extract_contacts",
            description="""Extract contact information from a web page.
            Extracts emails, phone numbers, and social media links.

            Parameters:
            - url: The URL to extract contacts from (required)
            - data_types: Types of contact data to extract (default: all)
                          Options: email, phone, social, all

            Returns extracted contact information.""",
        )
        async def extract_contacts(
            url: str,
            data_types: list[str] | None = None,
        ) -> dict[str, Any]:
            return await self._call_scrape({
                "action": "extract",
                "url": url,
                "data_types": data_types or ["email", "phone", "social"],
            })

        @self.mcp.tool(
            name="get_prospector_health",
            description="""Check the health status of the Prospector service.
            Returns status of scraping engines and overall service health.""",
        )
        async def get_prospector_health() -> dict[str, Any]:
            return await self._call_api("/health", method="GET")

        @self.mcp.tool(
            name="get_prospector_metrics",
            description="""Get performance metrics from the Prospector service.
            Returns statistics about scraping operations.""",
        )
        async def get_prospector_metrics() -> dict[str, Any]:
            return await self._call_api("/metrics", method="GET")

        logger.info("Prospector MCP tools registered")

    async def _call_scrape(self, data: dict) -> dict[str, Any]:
        """Call the Prospector /scrape endpoint."""
        return await self._call_api("/scrape", method="POST", data=data)

    async def _call_api(
        self,
        endpoint: str,
        method: str = "POST",
        data: dict | None = None,
    ) -> dict[str, Any]:
        """Make an async request to the Prospector API."""
        url = f"{self.target_url}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info(f"Calling Prospector API: {method} {url}")

                if method == "POST":
                    response = await client.post(url, json=data)
                elif method == "GET":
                    response = await client.get(url)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                result = response.json()

                logger.info(f"Prospector API response: {response.status_code}")
                return result

        except httpx.HTTPStatusError as e:
            error_msg = f"Prospector API error: {e.response.status_code}"
            try:
                error_data = e.response.json()
                error_msg = error_data.get("error", {}).get("message", error_msg)
            except Exception:
                error_msg = e.response.text or error_msg

            logger.error(f"Prospector API error: {error_msg}")
            return {"error": error_msg, "status_code": e.response.status_code}

        except httpx.RequestError as e:
            error_msg = f"Failed to connect to Prospector: {e}"
            logger.error(error_msg)
            return {"error": error_msg}


# Allow running standalone for testing or future container extraction
if __name__ == "__main__":
    server = ProspectorMCP()
    server.run()
