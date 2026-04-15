"""Web tools: fetch and search."""

from __future__ import annotations

import json
import re
from typing import Any

from opencode_agent.base_types import ToolCall, ToolInfo, ToolResponse
from opencode_agent.tools.base import BaseTool, ToolContext


class WebFetchTool(BaseTool):
    """Fetch and convert web page content."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="web_fetch",
            description=(
                "Fetch content from a URL and convert to readable format.\n"
                "Supports markdown, text, and HTML output formats.\n"
                "Good for reading documentation, blog posts, and API docs.\n"
                "Set appropriate timeouts for potentially slow websites."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch."},
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "text", "html"],
                        "description": "Output format. Default: markdown.",
                        "default": "markdown",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds. Default: 30.",
                        "default": 30,
                    },
                },
                "required": ["url"],
            },
            required=["url"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        url = data.get("url", "")
        fmt = data.get("format", "markdown")
        timeout = int(data.get("timeout", 30))

        if not url:
            return ToolResponse.error("URL is required")

        # Basic URL validation
        if not re.match(r"^https?://", url):
            url = "https://" + url

        # Check permission
        if ctx.permissions:
            from opencode_agent.base_types import PermissionAction, PermissionRequest
            granted = await ctx.permissions.request(
                PermissionRequest(
                    tool_name="web_fetch",
                    action=PermissionAction.NETWORK,
                    params={"url": url},
                    description=f"Fetch URL: {url}",
                ),
                session_id=ctx.session_id,
            )
            if not granted:
                return ToolResponse.error("Permission denied for web fetch")

        try:
            import httpx

            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(timeout),
                headers={"User-Agent": "OpenCodeAgent/1.0"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

            html_content = response.text

            if fmt == "html":
                return ToolResponse.json_response({
                    "success": True,
                    "content": html_content,
                    "url": response.url,
                    "title": self._extract_title(html_content),
                })

            # Convert HTML to text/markdown
            text_content = self._html_to_text(html_content)

            # Truncate large content
            max_chars = 50000
            if len(text_content) > max_chars:
                text_content = text_content[:max_chars] + "\n\n... (truncated)"

            return ToolResponse.json_response({
                "success": True,
                "content": text_content,
                "url": str(response.url),
                "title": self._extract_title(html_content),
            })

        except httpx.TimeoutException:
            return ToolResponse.error(f"Request timed out after {timeout}s")
        except httpx.HTTPStatusError as e:
            return ToolResponse.error(f"HTTP error {e.response.status_code}: {e.response.reason_phrase}")
        except Exception as e:
            return ToolResponse.error(f"Fetch error: {e}")

    @staticmethod
    def _extract_title(html: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Simple HTML to text conversion (strip tags, clean whitespace)."""
        # Remove script and style elements
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
        # Convert common block elements to newlines
        text = re.sub(r"<(br|p|div|li|h[1-6]|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
        # Remove all remaining tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode HTML entities
        text = (
            text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&nbsp;", " ")
        )
        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" +", " ", text)
        return text.strip()


class WebSearchTool(BaseTool):
    """Web search placeholder (requires external API key)."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="web_search",
            description=(
                "Search the web for information. Returns results with titles, URLs, and snippets.\n"
                "Useful for finding documentation, API references, and solutions.\n"
                "Requires a search API to be configured."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results. Default: 8.",
                        "default": 8,
                    },
                },
                "required": ["query"],
            },
            required=["query"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        query = data.get("query", "")
        num_results = int(data.get("num_results", 8))

        if not query:
            return ToolResponse.error("Query is required")

        # Check permission
        if ctx.permissions:
            from opencode_agent.base_types import PermissionAction, PermissionRequest
            granted = await ctx.permissions.request(
                PermissionRequest(
                    tool_name="web_search",
                    action=PermissionAction.NETWORK,
                    params={"query": query},
                    description=f"Web search: {query}",
                ),
                session_id=ctx.session_id,
            )
            if not granted:
                return ToolResponse.error("Permission denied for web search")

        try:
            import httpx

            # Use DuckDuckGo HTML search as a free fallback
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=15, headers={"User-Agent": "OpenCodeAgent/1.0"}
            ) as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                )
                response.raise_for_status()

            results = self._parse_ddg_results(response.text, num_results)

            if not results:
                return ToolResponse.text(
                    "No results found. Note: Using DuckDuckGo HTML search. "
                    "For better results, configure a dedicated search API."
                )

            output_parts: list[str] = []
            for i, r in enumerate(results, 1):
                output_parts.append(f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}")

            return ToolResponse.text("\n\n".join(output_parts))

        except Exception as e:
            return ToolResponse.error(f"Search error: {e}")

    @staticmethod
    def _parse_ddg_results(html: str, max_results: int) -> list[dict[str, str]]:
        """Parse DuckDuckGo HTML results."""
        import re

        results: list[dict[str, str]] = []
        # Extract result blocks
        blocks = re.findall(r'<a rel="nofollow" class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        urls = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)"', html, re.DOTALL)

        for i in range(min(len(blocks), max_results)):
            title = re.sub(r"<[^>]+>", "", blocks[i]).strip()
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
            url = urls[i] if i < len(urls) else ""
            if title:
                results.append({"title": title, "url": url, "snippet": snippet})

        return results


def get_web_tools() -> list[BaseTool]:
    return [WebFetchTool(), WebSearchTool()]